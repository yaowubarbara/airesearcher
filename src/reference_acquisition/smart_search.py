"""Smart Reference Pipeline: LLM blueprint -> API verify -> citation chain -> LLM curate.

Combines LLM domain knowledge (canonical scholars and works) with API verification
and citation chain mining to build a bibliography like a real scholar.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import Paper, PaperStatus
from src.knowledge_base.vector_store import VectorStore
from src.utils.api_clients import CrossRefClient, OpenAlexClient

from .citation_chain import CitationChainMiner, _extract_work_metadata
from .searcher import _normalize_title

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


# ── Data classes ──────────────────────────────────────────────────────


@dataclass
class BlueprintCategory:
    name: str
    description: str
    suggested_refs: list[dict] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    key_authors: list[str] = field(default_factory=list)
    key_journals: list[str] = field(default_factory=list)


@dataclass
class BlueprintResult:
    categories: list[BlueprintCategory] = field(default_factory=list)

    @property
    def total_suggested(self) -> int:
        return sum(len(c.suggested_refs) for c in self.categories)

    @property
    def all_key_authors(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for c in self.categories:
            for a in c.key_authors:
                if a.lower() not in seen:
                    seen.add(a.lower())
                    result.append(a)
        return result

    @property
    def all_key_journals(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for c in self.categories:
            for j in c.key_journals:
                if j.lower() not in seen:
                    seen.add(j.lower())
                    result.append(j)
        return result


@dataclass
class VerifiedRef:
    original: dict
    verified: bool
    paper: Optional[Paper] = None
    openalex_id: str = ""
    source: str = "unverified"
    match_confidence: float = 0.0


@dataclass
class CuratedRef:
    paper: Paper
    category: str = ""
    tier: int = 3
    usage_note: str = ""
    source_phase: str = "blueprint"


@dataclass
class SmartSearchReport:
    topic: str = ""
    blueprint_suggested: int = 0
    verified: int = 0
    hallucinated: int = 0
    expanded_pool: int = 0
    final_selected: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    tier_counts: dict[int, int] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    references: list[CuratedRef] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Smart Search: '{self.topic}'\n"
            f"  Blueprint suggested: {self.blueprint_suggested}\n"
            f"  Verified: {self.verified} | Hallucinated: {self.hallucinated}\n"
            f"  Expanded pool: {self.expanded_pool}\n"
            f"  Final selected: {self.final_selected}\n"
            f"  Categories: {self.categories}\n"
            f"  Tiers: {self.tier_counts}\n"
            f"  Gaps: {self.gaps}"
        )


# ── Helpers ───────────────────────────────────────────────────────────


def _jaccard_word_overlap(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _parse_json_from_llm(text: str) -> Any:
    """Extract and parse JSON from an LLM response (handles markdown fences)."""
    t = text.strip()
    if t.startswith("```"):
        # Remove opening fence (```json or ```)
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
    if t.endswith("```"):
        t = t.rsplit("```", 1)[0]
    return json.loads(t.strip())


def _candidate_to_paper(c: dict) -> Paper:
    """Convert a candidate dict (from OpenAlex metadata) to a Paper."""
    authors = c.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",") if a.strip()]
    return Paper(
        title=c.get("title") or "Untitled",
        authors=authors,
        year=c.get("year") or 0,
        journal=c.get("journal") or "",
        doi=c.get("doi") or None,
        openalex_id=c.get("openalex_id") or None,
        status=PaperStatus.METADATA_ONLY,
    )


# ── Main pipeline ────────────────────────────────────────────────────


class SmartReferencePipeline:
    """4-phase smart reference search pipeline."""

    def __init__(
        self,
        db: Database,
        vector_store: VectorStore,
        llm_router: Any,
        download_dir: str = "data/papers",
    ):
        self.db = db
        self.vs = vector_store
        self.llm = llm_router
        self.oa = OpenAlexClient()
        self.crossref = CrossRefClient()
        self.chain_miner = CitationChainMiner(openalex=self.oa, db=db)

    async def close(self) -> None:
        await self.oa.close()
        await self.crossref.close()

    async def smart_search(
        self,
        title: str,
        research_question: str,
        gap_description: str,
        target_count: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> SmartSearchReport:
        """Full 4-phase smart reference search."""
        self._topic_title = title
        self._topic_rq = research_question
        self._gaps: list[str] = []
        report = SmartSearchReport(topic=title)

        async def _progress(frac: float, msg: str) -> None:
            if progress_callback:
                await progress_callback(frac, msg)

        try:
            # Phase 1: LLM Blueprint (0.00 -> 0.15)
            await _progress(0.02, "Generating bibliography blueprint...")
            blueprint = await self._generate_blueprint(title, research_question, gap_description)
            report.blueprint_suggested = blueprint.total_suggested
            await _progress(0.15, f"Blueprint: {blueprint.total_suggested} suggestions in {len(blueprint.categories)} categories")

            # Phase 2: API Verification (0.15 -> 0.40)
            await _progress(0.16, "Verifying suggested references via CrossRef/OpenAlex...")
            verified = await self._verify_references(blueprint, _progress)
            verified_refs = [v for v in verified if v.verified]
            report.verified = len(verified_refs)
            report.hallucinated = len(verified) - len(verified_refs)
            await _progress(0.40, f"Verified {report.verified}/{len(verified)} references")

            # Phase 3: Citation Chain Expansion (0.40 -> 0.75)
            await _progress(0.41, "Expanding via citation chains...")
            candidates = await self._expand_citations(
                verified_refs, blueprint, title, _progress,
            )
            report.expanded_pool = len(candidates)
            await _progress(0.75, f"Expanded pool: {report.expanded_pool} candidates")

            # Phase 4: LLM Curation (0.75 -> 0.90)
            await _progress(0.76, "Curating final reference list...")
            curated = await self._curate_references(
                candidates, verified_refs, blueprint, target_count,
            )
            report.references = curated
            report.final_selected = len(curated)

            # Compute category and tier counts
            for c in curated:
                report.categories[c.category] = report.categories.get(c.category, 0) + 1
                report.tier_counts[c.tier] = report.tier_counts.get(c.tier, 0) + 1
            report.gaps = self._gaps

            await _progress(0.90, f"Selected {report.final_selected} references")

            # Phase 5: Persist (0.90 -> 1.0)
            await _progress(0.91, "Saving to database...")
            await self._persist_results(curated)
            await _progress(1.0, "Smart search complete")

            logger.info(report.summary())

        finally:
            await self.close()

        return report

    # ── Phase 1: Blueprint ────────────────────────────────────────────

    async def _generate_blueprint(
        self, title: str, rq: str, gap: str,
    ) -> BlueprintResult:
        """Phase 1: LLM generates bibliography blueprint."""
        template = _load_prompt("reference_blueprint.md")
        prompt = template.format(
            title=title,
            research_question=rq,
            gap_description=gap,
        )

        response = await asyncio.to_thread(
            self.llm.complete,
            task_type="reference_blueprint",
            messages=[{"role": "user", "content": prompt}],
        )
        text = self.llm.get_response_text(response)

        try:
            data = _parse_json_from_llm(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Blueprint LLM response not valid JSON, returning empty")
            return BlueprintResult()

        categories = []
        for cat_data in data.get("categories", []):
            categories.append(BlueprintCategory(
                name=cat_data.get("name", ""),
                description=cat_data.get("description", ""),
                suggested_refs=cat_data.get("suggested_refs", []),
                search_queries=cat_data.get("search_queries", []),
                key_authors=cat_data.get("key_authors", []),
                key_journals=cat_data.get("key_journals", []),
            ))

        result = BlueprintResult(categories=categories)
        logger.info(
            "Blueprint: %d categories, %d total suggestions",
            len(categories), result.total_suggested,
        )
        return result

    # ── Phase 2: Verification ─────────────────────────────────────────

    async def _verify_references(
        self, blueprint: BlueprintResult, progress_cb: Callable,
    ) -> list[VerifiedRef]:
        """Phase 2: Verify each suggested ref via CrossRef + OpenAlex."""
        all_suggestions: list[dict] = []
        for cat in blueprint.categories:
            for ref in cat.suggested_refs:
                ref["_category"] = cat.name
                all_suggestions.append(ref)

        if not all_suggestions:
            return []

        results: list[VerifiedRef] = []
        sem = asyncio.Semaphore(5)

        async def verify_one(ref: dict) -> VerifiedRef:
            async with sem:
                return await self._verify_single_ref(ref)

        # Run verifications with progress
        tasks = [verify_one(ref) for ref in all_suggestions]
        total = len(tasks)
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            result = await coro
            results.append(result)
            if i % 5 == 0:
                frac = 0.15 + 0.25 * ((i + 1) / total)
                await progress_cb(frac, f"Verifying {i+1}/{total}...")

        return results

    async def _verify_single_ref(self, ref: dict) -> VerifiedRef:
        """Verify a single suggested reference against CrossRef and OpenAlex."""
        title = ref.get("title", "")
        author = ref.get("author", "")
        year = ref.get("year", 0)

        if not title:
            return VerifiedRef(original=ref, verified=False)

        # 1. Try CrossRef: query.bibliographic with title + author
        search_query = f"{author} {title}" if author else title
        try:
            cr_result = await self.crossref.search_works(
                query_bibliographic=search_query, rows=5,
            )
            items = cr_result.get("message", {}).get("items", [])
            for item in items:
                item_titles = item.get("title", [])
                if not item_titles:
                    continue
                item_title = item_titles[0]
                sim = _jaccard_word_overlap(
                    _normalize_title(title), _normalize_title(item_title),
                )
                if sim >= 0.5:
                    paper = self._crossref_item_to_paper(item)
                    return VerifiedRef(
                        original=ref, verified=True, paper=paper,
                        source="crossref", match_confidence=sim,
                    )
        except Exception:
            logger.debug("CrossRef verification failed for: %s", title[:60], exc_info=True)

        # 2. Try OpenAlex search
        try:
            oa_result = await self.oa.search_works(search=search_query, per_page=5)
            for work in oa_result.get("results", []):
                work_title = work.get("title") or work.get("display_name") or ""
                sim = _jaccard_word_overlap(
                    _normalize_title(title), _normalize_title(work_title),
                )
                if sim >= 0.5:
                    meta = _extract_work_metadata(work)
                    paper = _candidate_to_paper(meta)
                    oa_id = work.get("id", "")
                    return VerifiedRef(
                        original=ref, verified=True, paper=paper,
                        openalex_id=oa_id,
                        source="openalex", match_confidence=sim,
                    )
        except Exception:
            logger.debug("OpenAlex verification failed for: %s", title[:60], exc_info=True)

        return VerifiedRef(original=ref, verified=False)

    def _crossref_item_to_paper(self, item: dict) -> Paper:
        """Convert a CrossRef work item to a Paper object."""
        title_list = item.get("title", [])
        title = title_list[0] if title_list else "Untitled"

        authors_raw = item.get("author", [])
        authors = []
        for a in authors_raw:
            given = a.get("given", "")
            family = a.get("family", "")
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)

        date_parts = (
            item.get("published-print") or item.get("published-online") or {}
        ).get("date-parts", [[]])
        year = date_parts[0][0] if date_parts and date_parts[0] else 0

        journal_names = item.get("container-title", [])
        journal = journal_names[0] if journal_names else ""

        return Paper(
            title=title,
            authors=authors,
            year=year or 0,
            journal=journal,
            doi=item.get("DOI"),
            volume=item.get("volume"),
            issue=item.get("issue"),
            pages=item.get("page"),
            status=PaperStatus.METADATA_ONLY,
        )

    # ── Phase 3: Citation Chain Expansion ─────────────────────────────

    async def _expand_citations(
        self,
        verified_refs: list[VerifiedRef],
        blueprint: BlueprintResult,
        topic_query: str,
        progress_cb: Callable,
    ) -> list[dict]:
        """Phase 3: Citation chain expansion from verified seeds."""
        # Build seed list from verified refs that have OpenAlex IDs
        seed_papers: list[dict] = []
        for v in verified_refs:
            if v.openalex_id:
                seed_papers.append({
                    "openalex_id": v.openalex_id,
                    "title": v.paper.title if v.paper else "",
                    "doi": v.paper.doi if v.paper else "",
                })
            elif v.paper and v.paper.openalex_id:
                seed_papers.append({
                    "openalex_id": v.paper.openalex_id,
                    "title": v.paper.title,
                    "doi": v.paper.doi or "",
                })

        # If we have no seeds with OpenAlex IDs, try to look them up
        if not seed_papers:
            for v in verified_refs[:10]:
                if not v.paper:
                    continue
                try:
                    result = await self.oa.search_works(
                        search=v.paper.title, per_page=1,
                    )
                    works = result.get("results", [])
                    if works:
                        oa_id = works[0].get("id", "")
                        if oa_id:
                            seed_papers.append({
                                "openalex_id": oa_id,
                                "title": v.paper.title,
                                "doi": v.paper.doi or "",
                            })
                except Exception:
                    pass

        key_authors = blueprint.all_key_authors
        key_journals = blueprint.all_key_journals

        async def chain_progress(frac: float) -> None:
            # Map chain progress (0-1) to overall progress (0.40-0.75)
            await progress_cb(0.40 + 0.35 * frac, f"Expanding citations... ({int(frac*100)}%)")

        candidates = await self.chain_miner.expand_from_seeds(
            seed_papers=seed_papers,
            key_authors=key_authors,
            key_journals=key_journals,
            topic_query=topic_query,
            max_total=200,
            progress_callback=chain_progress,
        )

        return candidates

    # ── Phase 4: LLM Curation ────────────────────────────────────────

    async def _curate_references(
        self,
        candidates: list[dict],
        verified_refs: list[VerifiedRef],
        blueprint: BlueprintResult,
        target_count: int,
    ) -> list[CuratedRef]:
        """Phase 4: LLM selects and categorizes from candidate pool."""
        # Build combined pool: verified refs + chain candidates
        pool: list[dict] = []
        pool_source: list[str] = []

        # Add verified refs first
        for v in verified_refs:
            if v.paper:
                pool.append({
                    "title": v.paper.title,
                    "authors": ", ".join(v.paper.authors[:3]),
                    "year": v.paper.year,
                    "journal": v.paper.journal or "",
                    "doi": v.paper.doi or "",
                })
                pool_source.append("blueprint")

        # Add chain candidates (dedup against verified)
        verified_dois = {
            v.paper.doi.lower()
            for v in verified_refs
            if v.paper and v.paper.doi
        }
        for c in candidates:
            doi = (c.get("doi") or "").lower()
            if doi and doi in verified_dois:
                continue
            if doi:
                verified_dois.add(doi)
            authors = c.get("authors", [])
            if isinstance(authors, list):
                authors = ", ".join(authors[:3])
            pool.append({
                "title": c.get("title", ""),
                "authors": authors,
                "year": c.get("year", 0),
                "journal": c.get("journal", ""),
                "doi": c.get("doi", ""),
            })
            pool_source.append(c.get("source_phase", "citation_chain"))

        if not pool:
            return []

        # Prepare categories description
        cat_desc = "\n".join(
            f"- **{cat.name}**: {cat.description}" for cat in blueprint.categories
        )

        # Build candidates JSON (compact)
        candidates_lines = []
        for i, p in enumerate(pool):
            line = f'{i}. {p["authors"]} ({p["year"]}). "{p["title"]}". {p["journal"]}'
            candidates_lines.append(line)
        candidates_text = "\n".join(candidates_lines)

        # Adjust target count to pool size
        actual_target = min(target_count, len(pool))

        template = _load_prompt("reference_curation.md")
        prompt = template.format(
            title=self._topic_title,
            research_question=self._topic_rq,
            target_count=actual_target,
            categories_description=cat_desc,
            candidate_count=len(pool),
            candidates_json=candidates_text,
        )

        response = await asyncio.to_thread(
            self.llm.complete,
            task_type="reference_curation",
            messages=[{"role": "user", "content": prompt}],
        )
        text = self.llm.get_response_text(response)

        try:
            data = _parse_json_from_llm(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Curation LLM response not valid JSON, selecting all verified")
            # Fallback: return all verified refs
            return [
                CuratedRef(
                    paper=v.paper,
                    category=v.original.get("_category", ""),
                    tier=2,
                    usage_note="",
                    source_phase="blueprint",
                )
                for v in verified_refs if v.paper
            ]

        selected = data.get("selected", [])
        gaps = data.get("gaps", [])

        curated: list[CuratedRef] = []
        for sel in selected:
            idx = sel.get("index", -1)
            if not (0 <= idx < len(pool)):
                continue

            p_data = pool[idx]
            paper = _candidate_to_paper(p_data)
            curated.append(CuratedRef(
                paper=paper,
                category=sel.get("category", ""),
                tier=sel.get("tier", 3),
                usage_note=sel.get("usage", ""),
                source_phase=pool_source[idx] if idx < len(pool_source) else "unknown",
            ))

        # Store gaps in report
        self._gaps = gaps

        return curated

    # ── Phase 5: Persist ──────────────────────────────────────────────

    async def _persist_results(self, curated: list[CuratedRef]) -> None:
        """Insert curated papers into DB."""
        for c in curated:
            try:
                # Check if paper already exists by DOI
                existing = None
                if c.paper.doi:
                    existing = self.db.get_paper_by_doi(c.paper.doi)

                if existing:
                    c.paper.id = existing.id
                else:
                    paper_id = self.db.insert_paper(c.paper)
                    c.paper.id = paper_id
            except Exception:
                logger.debug(
                    "Failed to persist paper: %s", c.paper.title[:60], exc_info=True,
                )

    # ── Top-level wrapper that stores topic info ──────────────────────

    async def run(
        self,
        title: str,
        research_question: str,
        gap_description: str,
        target_count: int = 50,
        progress_callback: Optional[Callable] = None,
    ) -> SmartSearchReport:
        """Public entry point — delegates to smart_search."""
        return await self.smart_search(
            title=title,
            research_question=research_question,
            gap_description=gap_description,
            target_count=target_count,
            progress_callback=progress_callback,
        )
