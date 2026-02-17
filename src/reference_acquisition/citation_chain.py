"""Mine citation chains from seed papers via OpenAlex.

Given a set of verified seed papers, expands the reference pool by:
1. Backward chain — papers cited BY each seed (referenced_works)
2. Forward chain — papers that CITE each seed (cites: filter)
3. Author chain — other works by key authors
4. Journal search — topic-specific search within key journals

All results are deduplicated by DOI and returned as a flat candidate pool.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from src.knowledge_base.db import Database
from src.utils.api_clients import OpenAlexClient

logger = logging.getLogger(__name__)


def _extract_work_metadata(work: dict) -> dict:
    """Extract a flat metadata dict from an OpenAlex work object."""
    authorships = work.get("authorships") or []
    authors = []
    for a in authorships:
        name = a.get("author", {}).get("display_name", "")
        if name:
            authors.append(name)

    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    journal = source.get("display_name", "")

    doi_raw = work.get("doi") or ""
    doi = doi_raw.replace("https://doi.org/", "") if doi_raw else ""

    return {
        "openalex_id": work.get("id", ""),
        "title": work.get("title") or "",
        "authors": authors,
        "year": work.get("publication_year") or 0,
        "journal": journal,
        "doi": doi,
        "cited_by_count": work.get("cited_by_count") or 0,
    }


class CitationChainMiner:
    """Mine citation chains from seed papers via OpenAlex."""

    def __init__(self, openalex: Optional[OpenAlexClient] = None, db: Optional[Database] = None):
        self.oa = openalex or OpenAlexClient()
        self.db = db
        self._owns_client = openalex is None

    async def close(self) -> None:
        if self._owns_client:
            await self.oa.close()

    async def get_references_of(self, openalex_id: str, limit: int = 50) -> list[dict]:
        """Get works cited BY this paper (backward chain).

        Uses the referenced_works field from the OpenAlex work object.
        """
        try:
            works = await self.oa.get_work_references(openalex_id, limit=limit)
            return [_extract_work_metadata(w) for w in works]
        except Exception:
            logger.warning("Failed to get references of %s", openalex_id, exc_info=True)
            return []

    async def get_citing_works(self, openalex_id: str, limit: int = 30) -> list[dict]:
        """Get works that CITE this paper (forward chain)."""
        try:
            works = await self.oa.get_citing_works(openalex_id, limit=limit)
            return [_extract_work_metadata(w) for w in works]
        except Exception:
            logger.warning("Failed to get citing works for %s", openalex_id, exc_info=True)
            return []

    async def get_author_works(self, author_name: str, limit: int = 20) -> list[dict]:
        """Get other works by the same author."""
        try:
            author_id = await self.oa.search_author(author_name)
            if not author_id:
                logger.debug("Author not found on OpenAlex: %s", author_name)
                return []
            works = await self.oa.get_author_works(author_id, limit=limit)
            return [_extract_work_metadata(w) for w in works]
        except Exception:
            logger.warning("Failed to get works for author %s", author_name, exc_info=True)
            return []

    async def search_in_journal(self, query: str, journal_name: str, limit: int = 20) -> list[dict]:
        """Search within a specific journal."""
        try:
            works = await self.oa.search_works_in_journal(query, journal_name, limit=limit)
            return [_extract_work_metadata(w) for w in works]
        except Exception:
            logger.warning(
                "Failed journal search: %s in %s", query[:40], journal_name, exc_info=True
            )
            return []

    async def expand_from_seeds(
        self,
        seed_papers: list[dict],
        key_authors: list[str],
        key_journals: list[str],
        topic_query: str,
        max_total: int = 200,
        progress_callback: Optional[Callable] = None,
    ) -> list[dict]:
        """Full expansion: backward + forward + author + journal search.

        Deduplicates by DOI across all sources.
        Returns candidate pool with source attribution.
        """
        candidates: list[dict] = []
        seen_dois: set[str] = set()
        # Track seed DOIs to avoid re-adding
        for s in seed_papers:
            doi = (s.get("doi") or "").lower()
            if doi:
                seen_dois.add(doi)

        def _add_candidates(works: list[dict], source: str) -> int:
            added = 0
            for w in works:
                if len(candidates) >= max_total:
                    break
                doi = (w.get("doi") or "").lower()
                if doi and doi in seen_dois:
                    continue
                if doi:
                    seen_dois.add(doi)
                w["source_phase"] = source
                candidates.append(w)
                added += 1
            return added

        total_steps = len(seed_papers) * 2 + len(key_authors) + len(key_journals)
        step = 0

        # 1. Backward chain for each seed
        sem = asyncio.Semaphore(3)  # limit concurrency

        async def _backward(paper: dict) -> list[dict]:
            oa_id = paper.get("openalex_id", "")
            if not oa_id:
                return []
            async with sem:
                return await self.get_references_of(oa_id, limit=30)

        async def _forward(paper: dict) -> list[dict]:
            oa_id = paper.get("openalex_id", "")
            if not oa_id:
                return []
            async with sem:
                return await self.get_citing_works(oa_id, limit=20)

        # Run backward chains
        for paper in seed_papers:
            if len(candidates) >= max_total:
                break
            refs = await _backward(paper)
            added = _add_candidates(refs, "citation_chain")
            step += 1
            if progress_callback:
                await progress_callback(step / max(total_steps, 1))
            logger.debug(
                "Backward chain for %s: %d refs, %d new",
                paper.get("title", "")[:40], len(refs), added,
            )

        # 2. Forward chain for each seed
        for paper in seed_papers:
            if len(candidates) >= max_total:
                break
            citing = await _forward(paper)
            added = _add_candidates(citing, "citation_chain")
            step += 1
            if progress_callback:
                await progress_callback(step / max(total_steps, 1))

        # 3. Author chain
        for author in key_authors:
            if len(candidates) >= max_total:
                break
            async with sem:
                works = await self.get_author_works(author, limit=15)
            added = _add_candidates(works, "author_chain")
            step += 1
            if progress_callback:
                await progress_callback(step / max(total_steps, 1))
            logger.debug("Author chain for %s: %d works, %d new", author, len(works), added)

        # 4. Journal search
        for journal in key_journals:
            if len(candidates) >= max_total:
                break
            async with sem:
                works = await self.search_in_journal(topic_query, journal, limit=15)
            added = _add_candidates(works, "journal_search")
            step += 1
            if progress_callback:
                await progress_callback(step / max(total_steps, 1))
            logger.debug("Journal search in %s: %d works, %d new", journal, len(works), added)

        logger.info(
            "Citation chain expansion: %d candidates from %d seeds, %d authors, %d journals",
            len(candidates), len(seed_papers), len(key_authors), len(key_journals),
        )
        return candidates
