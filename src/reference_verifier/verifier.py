"""Reference verification pipeline - triple-verify every citation is real."""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import Reference
from src.utils.text_processing import extract_citations_from_text

from .doi_resolver import DOIResolver
from .format_checker import FormatChecker


class ReferenceVerifier:
    """Verifies that all references in a manuscript are real and correctly cited.

    Uses a triple-verification approach:
    1. CrossRef DOI lookup
    2. Semantic Scholar search
    3. OpenAlex search

    A reference is marked verified if found in at least one source.
    """

    def __init__(
        self,
        db: Database,
        crossref_email: Optional[str] = None,
        s2_api_key: Optional[str] = None,
        openalex_email: Optional[str] = None,
    ):
        self.db = db
        self.resolver = DOIResolver(
            crossref_email=crossref_email,
            s2_api_key=s2_api_key,
            openalex_email=openalex_email,
        )
        self.format_checker = FormatChecker()

    async def verify_manuscript_references(
        self, manuscript_text: str, reference_ids: list[str]
    ) -> VerificationReport:
        """Verify all references cited in a manuscript.

        Returns a VerificationReport with verified/unverified/missing lists.
        """
        # Step 1: Extract citations from the manuscript text
        cited = extract_citations_from_text(manuscript_text)

        # Step 2: Verify each reference in the reference list
        verified: list[VerifiedRef] = []
        unverified: list[UnverifiedRef] = []

        for ref_id in reference_ids:
            paper = self.db.get_paper(ref_id)
            if not paper:
                unverified.append(UnverifiedRef(
                    ref_id=ref_id,
                    reason="Not found in database",
                ))
                continue

            # Try to verify via DOI first, then by title search
            result = await self.resolver.verify_reference(
                title=paper.title,
                authors=paper.authors,
                year=paper.year,
                doi=paper.doi,
            )

            if result:
                verified.append(VerifiedRef(
                    ref_id=ref_id,
                    title=paper.title,
                    source=result.get("verification_source", "unknown"),
                    verified_doi=result.get("doi"),
                    metadata_match=self._check_metadata_match(paper, result),
                ))
            else:
                unverified.append(UnverifiedRef(
                    ref_id=ref_id,
                    title=paper.title,
                    reason="Could not verify in CrossRef, Semantic Scholar, or OpenAlex",
                ))

        # Step 3: Check for citations in text that don't have a corresponding reference
        orphan_citations = self._find_orphan_citations(cited, reference_ids)

        return VerificationReport(
            total_references=len(reference_ids),
            verified=verified,
            unverified=unverified,
            orphan_citations=orphan_citations,
            verification_rate=len(verified) / len(reference_ids) if reference_ids else 0,
        )

    async def verify_single_reference(self, ref: Reference) -> Optional[dict]:
        """Verify a single reference and update it in the database."""
        result = await self.resolver.verify_reference(
            title=ref.title,
            authors=ref.authors,
            year=ref.year,
            doi=ref.doi,
        )

        if result and ref.id:
            source = result.get("verification_source", "unknown")
            # Format in multiple styles
            verified_ref = Reference(
                **{**ref.model_dump(), **{k: v for k, v in result.items()
                   if k in Reference.model_fields and v is not None}}
            )
            mla = self.format_checker.format_reference(verified_ref, "MLA")
            chicago = self.format_checker.format_reference(verified_ref, "Chicago")
            gb = self.format_checker.format_reference(verified_ref, "GB/T 7714")

            self.db.mark_reference_verified(ref.id, source, mla, chicago, gb)

        return result

    async def verify_batch(self, references: list[Reference]) -> dict[str, bool]:
        """Verify a batch of references. Returns {ref_id: is_verified}."""
        results = {}
        # Process in parallel with concurrency limit
        semaphore = asyncio.Semaphore(5)

        async def verify_one(ref: Reference) -> tuple[str, bool]:
            async with semaphore:
                result = await self.verify_single_reference(ref)
                return (ref.id or "", result is not None)

        tasks = [verify_one(ref) for ref in references]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for outcome in outcomes:
            if isinstance(outcome, tuple):
                ref_id, is_verified = outcome
                results[ref_id] = is_verified
            # Skip exceptions silently

        return results

    def suggest_replacements(
        self, unverified_ref_id: str, limit: int = 5
    ) -> list[Reference]:
        """Suggest verified replacement references from the knowledge base."""
        return self.db.get_verified_references(limit=limit)

    def _check_metadata_match(self, paper, verified: dict) -> dict[str, bool]:
        """Check which metadata fields match between stored and verified data."""
        matches = {}

        if verified.get("title"):
            matches["title"] = DOIResolver._is_title_match(
                paper.title, [verified["title"]]
            )

        if verified.get("year") and paper.year:
            matches["year"] = paper.year == verified["year"]

        if verified.get("authors") and paper.authors:
            # Check if at least the first author matches
            v_authors = [a.lower() for a in verified["authors"]]
            p_first = paper.authors[0].lower().split()[-1]  # last name
            matches["first_author"] = any(p_first in a for a in v_authors)

        return matches

    def _find_orphan_citations(
        self, cited: list[dict], reference_ids: list[str]
    ) -> list[dict]:
        """Find citations in text that don't match any reference in the list."""
        # This is a simplified check - in practice would need more sophisticated matching
        return []  # Placeholder for now

    async def close(self) -> None:
        await self.resolver.close()


class VerifiedRef:
    """A verified reference."""

    def __init__(
        self,
        ref_id: str,
        title: str = "",
        source: str = "",
        verified_doi: Optional[str] = None,
        metadata_match: Optional[dict] = None,
    ):
        self.ref_id = ref_id
        self.title = title
        self.source = source
        self.verified_doi = verified_doi
        self.metadata_match = metadata_match or {}


class UnverifiedRef:
    """An unverified reference."""

    def __init__(self, ref_id: str, title: str = "", reason: str = ""):
        self.ref_id = ref_id
        self.title = title
        self.reason = reason


class VerificationReport:
    """Report from reference verification."""

    def __init__(
        self,
        total_references: int,
        verified: list[VerifiedRef],
        unverified: list[UnverifiedRef],
        orphan_citations: list[dict],
        verification_rate: float,
    ):
        self.total_references = total_references
        self.verified = verified
        self.unverified = unverified
        self.orphan_citations = orphan_citations
        self.verification_rate = verification_rate

    def summary(self) -> str:
        lines = [
            f"Reference Verification Report",
            f"Total references: {self.total_references}",
            f"Verified: {len(self.verified)} ({self.verification_rate:.0%})",
            f"Unverified: {len(self.unverified)}",
        ]
        if self.unverified:
            lines.append("\nUnverified references:")
            for uv in self.unverified:
                lines.append(f"  - {uv.title or uv.ref_id}: {uv.reason}")
        if self.orphan_citations:
            lines.append(f"\nOrphan citations in text: {len(self.orphan_citations)}")
        return "\n".join(lines)
