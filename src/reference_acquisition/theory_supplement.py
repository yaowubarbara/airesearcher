"""Theory supplement stage.

After plan creation, identifies canonical theory works missing from the
reference list and verifies them via CrossRef/OpenAlex before inserting
into the database as Reference objects with ref_type=THEORY.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.citation_verifier.engine import _is_title_match, _normalize_crossref
from src.knowledge_base.db import Database
from src.knowledge_base.models import Reference, ReferenceType
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter
from src.utils.api_clients import CrossRefClient, OpenAlexClient

logger = logging.getLogger(__name__)


@dataclass
class TheoryCandidate:
    """A theory work recommended by the LLM."""

    author: str
    title: str
    relevance: str
    year_hint: Optional[int] = None


@dataclass
class TheoryVerification:
    """Result of verifying a single theory candidate."""

    candidate: TheoryCandidate
    verified: bool = False
    source: str = "llm_only"  # "crossref", "openalex", "llm_only"
    reference: Optional[Reference] = None
    already_in_db: bool = False
    has_full_text: bool = False


@dataclass
class TheorySupplementReport:
    """Summary of the theory supplement operation."""

    plan_id: str
    total_recommended: int = 0
    verified: int = 0
    inserted: int = 0
    already_present: int = 0
    items: list[TheoryVerification] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Theory supplement: {self.total_recommended} recommended, "
            f"{self.verified} verified via API, "
            f"{self.inserted} inserted, "
            f"{self.already_present} already in DB"
        )


class TheorySupplement:
    """Identifies and verifies canonical theory works for a research plan."""

    def __init__(
        self,
        db: Database,
        vector_store: VectorStore,
        llm_router: LLMRouter,
    ):
        self.db = db
        self.vs = vector_store
        self.llm = llm_router

    async def supplement_plan(
        self,
        plan_id: str,
        thesis: str,
        outline_sections: list[dict],
        existing_reference_ids: list[str],
        progress_callback: Optional[Callable] = None,
    ) -> TheorySupplementReport:
        """Identify and verify canonical theory works for a research plan.

        Steps:
          1. Gather titles of existing refs
          2. LLM call: predict 8-15 canonical theory works
          3. Verify each via CrossRef/OpenAlex
          4. Dedup against existing references
          5. Insert as Reference(ref_type=THEORY)
          6. Check full text availability

        Args:
            plan_id: ID of the research plan.
            thesis: Thesis statement.
            outline_sections: List of outline section dicts.
            existing_reference_ids: IDs of references already in the plan.
            progress_callback: Optional async callback(progress, message).

        Returns:
            TheorySupplementReport with verification details.
        """
        report = TheorySupplementReport(plan_id=plan_id)

        # Step 1: gather existing reference titles
        existing_titles = self._gather_existing_titles(existing_reference_ids)

        if progress_callback:
            await progress_callback(0.1, "Predicting theory works...")

        # Step 2: LLM prediction
        candidates = await self._predict_theory_works(
            thesis, outline_sections, existing_titles
        )
        report.total_recommended = len(candidates)

        if not candidates:
            return report

        if progress_callback:
            await progress_callback(0.3, f"Verifying {len(candidates)} theory works...")

        # Step 3: verify via APIs
        verifications = await self._verify_candidates(candidates)

        if progress_callback:
            await progress_callback(0.7, "Inserting verified references...")

        # Step 4-6: dedup, insert, check availability
        for v in verifications:
            # Dedup check
            existing = self.db.search_references_by_title(v.candidate.title, limit=3)
            if existing:
                for ex in existing:
                    if _is_title_match(v.candidate.title, [ex.title]):
                        v.already_in_db = True
                        v.reference = ex
                        report.already_present += 1
                        break

            if v.verified:
                report.verified += 1

            # Insert if not already present
            if not v.already_in_db and v.reference:
                ref_id = self.db.insert_reference(v.reference)
                v.reference.id = ref_id
                report.inserted += 1

            # Check full text availability
            if v.reference and v.reference.title:
                papers = self.db.search_papers_by_title(v.reference.title, limit=3)
                from src.knowledge_base.models import PaperStatus
                for p in papers:
                    if p.status in (PaperStatus.INDEXED, PaperStatus.ANALYZED):
                        v.has_full_text = True
                        break

            report.items.append(v)

        if progress_callback:
            await progress_callback(1.0, report.summary())

        return report

    def _gather_existing_titles(self, reference_ids: list[str]) -> list[str]:
        """Get titles of existing references for dedup context."""
        titles = []
        for rid in reference_ids[:50]:
            paper = self.db.get_paper(rid)
            if paper and paper.title:
                titles.append(paper.title)
        return titles

    async def _predict_theory_works(
        self,
        thesis: str,
        outline_sections: list[dict],
        existing_titles: list[str],
    ) -> list[TheoryCandidate]:
        """Use LLM to predict canonical theory works needed."""
        # Build section summaries
        section_summaries = []
        for s in outline_sections[:8]:
            title = s.get("title", "")
            argument = s.get("argument", "")[:200]
            section_summaries.append(f"  - {title}: {argument}")
        sections_text = "\n".join(section_summaries) if section_summaries else "(no sections)"

        existing_text = ""
        if existing_titles:
            titles_str = "\n".join(f"  - {t}" for t in existing_titles[:30])
            existing_text = f"\n\nAlready in the reference list:\n{titles_str}"

        prompt = f"""You are a comparative literature scholar building a theoretical framework.

Thesis: {thesis}

Paper sections:
{sections_text}
{existing_text}

Identify 8-15 canonical THEORY works (not primary literary texts, not recent articles)
that a top-journal article with this thesis would cite. Focus on:
- Foundational theoretical texts (Derrida, Benjamin, Adorno, Foucault, Said, Spivak, etc.)
- Key methodological works in comparative literature
- Canonical critical frameworks relevant to the thesis

Return a JSON array of objects, each with:
- "author": full author name
- "title": exact work title (book or seminal article)
- "year": publication year (integer)
- "relevance": one sentence explaining why this work is needed

DO NOT include works already listed above.
Respond with ONLY the JSON array."""

        try:
            response = self.llm.complete(
                task_type="metadata_processing",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            text = self.llm.get_response_text(response).strip()

            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                logger.warning("LLM response did not contain a JSON array")
                return []

            data = json.loads(match.group())
            candidates = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                author = entry.get("author", "").strip()
                title = entry.get("title", "").strip()
                if not title:
                    continue
                year = entry.get("year")
                if isinstance(year, str):
                    try:
                        year = int(year)
                    except ValueError:
                        year = None
                candidates.append(TheoryCandidate(
                    author=author,
                    title=title,
                    relevance=entry.get("relevance", ""),
                    year_hint=year,
                ))
            return candidates
        except Exception:
            logger.warning("Failed to predict theory works", exc_info=True)
            return []

    async def _verify_candidates(
        self,
        candidates: list[TheoryCandidate],
    ) -> list[TheoryVerification]:
        """Verify candidates via CrossRef and OpenAlex."""
        semaphore = asyncio.Semaphore(5)
        crossref = CrossRefClient()
        openalex = OpenAlexClient()

        async def verify_one(candidate: TheoryCandidate) -> TheoryVerification:
            async with semaphore:
                return await self._verify_single(candidate, crossref, openalex)

        tasks = [verify_one(c) for c in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        verifications = []
        for i, result in enumerate(results):
            if isinstance(result, TheoryVerification):
                verifications.append(result)
            else:
                # Error: create an llm_only entry
                logger.debug("Verification error for %s: %s", candidates[i].title, result)
                verifications.append(self._make_llm_only(candidates[i]))

        await crossref.close()
        await openalex.close()

        return verifications

    async def _verify_single(
        self,
        candidate: TheoryCandidate,
        crossref: CrossRefClient,
        openalex: OpenAlexClient,
    ) -> TheoryVerification:
        """Verify a single candidate against CrossRef and OpenAlex."""
        query = f"{candidate.author} {candidate.title}"

        # Try CrossRef
        try:
            result = await crossref.search_works(
                query_bibliographic=query, rows=5
            )
            if result and "message" in result:
                items = result["message"].get("items", [])
                for item in items:
                    normalized = _normalize_crossref(item)
                    if _is_title_match(candidate.title, [normalized.get("title", "")]):
                        ref = self._normalized_to_reference(normalized, "crossref")
                        return TheoryVerification(
                            candidate=candidate,
                            verified=True,
                            source="crossref",
                            reference=ref,
                        )
        except Exception:
            logger.debug("CrossRef search failed for %s", candidate.title)

        # Try OpenAlex
        try:
            result = await openalex.search_works(search=query, per_page=5)
            if result and "results" in result:
                for work in result["results"]:
                    work_title = work.get("title", "")
                    if _is_title_match(candidate.title, [work_title]):
                        ref = self._openalex_to_reference(work)
                        return TheoryVerification(
                            candidate=candidate,
                            verified=True,
                            source="openalex",
                            reference=ref,
                        )
        except Exception:
            logger.debug("OpenAlex search failed for %s", candidate.title)

        # Fallback: LLM-only
        return self._make_llm_only(candidate)

    def _make_llm_only(self, candidate: TheoryCandidate) -> TheoryVerification:
        """Create an llm_only verification with a Reference from LLM data."""
        ref = Reference(
            id=str(uuid.uuid4()),
            title=candidate.title,
            authors=[candidate.author] if candidate.author else [],
            year=candidate.year_hint or 0,
            ref_type=ReferenceType.THEORY,
            verified=False,
            verification_source="llm_only",
        )
        return TheoryVerification(
            candidate=candidate,
            verified=False,
            source="llm_only",
            reference=ref,
        )

    @staticmethod
    def _normalized_to_reference(normalized: dict[str, Any], source: str) -> Reference:
        """Convert a normalized CrossRef dict to a Reference."""
        return Reference(
            id=str(uuid.uuid4()),
            title=normalized.get("title", ""),
            authors=normalized.get("authors", []),
            year=normalized.get("year") or 0,
            journal=normalized.get("journal"),
            volume=normalized.get("volume"),
            issue=normalized.get("issue"),
            pages=normalized.get("pages"),
            doi=normalized.get("doi"),
            publisher=normalized.get("publisher"),
            ref_type=ReferenceType.THEORY,
            verified=True,
            verification_source=source,
        )

    @staticmethod
    def _openalex_to_reference(work: dict[str, Any]) -> Reference:
        """Convert an OpenAlex work dict to a Reference."""
        authorships = work.get("authorships", [])
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in authorships
            if a.get("author", {}).get("display_name")
        ]
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        journal = ""
        source = work.get("primary_location", {})
        if source:
            src_obj = source.get("source") or {}
            journal = src_obj.get("display_name", "")

        return Reference(
            id=str(uuid.uuid4()),
            title=work.get("title", ""),
            authors=authors,
            year=work.get("publication_year") or 0,
            journal=journal or None,
            doi=doi or None,
            ref_type=ReferenceType.THEORY,
            verified=True,
            verification_source="openalex",
        )
