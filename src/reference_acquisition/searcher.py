"""Search for papers across multiple APIs by research topic keywords."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from src.journal_monitor.sources.crossref import _crossref_item_to_paper
from src.journal_monitor.sources.openalex import _openalex_work_to_paper
from src.journal_monitor.sources.semantic_scholar import _s2_paper_to_paper
from src.knowledge_base.db import Database
from src.knowledge_base.models import Paper
from src.utils.api_clients import (
    CrossRefClient,
    OpenAlexClient,
    SemanticScholarClient,
)

logger = logging.getLogger(__name__)

# Short words that carry no topical signal — skip when filtering by keyword overlap.
_STOPWORDS = frozenset(
    "a an the of in on at to for and or but is are was were by with from as it"
    " its this that these those be been has have had do does did not no".split()
)


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful lowercase keywords from a search query."""
    import re

    tokens = re.split(r"\W+", query.lower())
    return [t for t in tokens if t and t not in _STOPWORDS and len(t) > 2]


class ReferenceSearcher:
    """Search for relevant papers across Semantic Scholar, OpenAlex, and CrossRef."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db

    async def search_topic(
        self,
        topic: str,
        max_results_per_source: int = 30,
    ) -> list[Paper]:
        """Search for papers related to a research topic.

        Queries all three API sources concurrently, deduplicates by DOI,
        and filters out papers already in the database.

        Args:
            topic: Research topic or keywords to search for.
            max_results_per_source: Maximum results to request from each API.

        Returns:
            Deduplicated list of Paper objects.
        """
        results = await asyncio.gather(
            self._search_semantic_scholar(topic, max_results_per_source),
            self._search_openalex(topic, max_results_per_source),
            self._search_crossref(topic, max_results_per_source),
            return_exceptions=True,
        )

        all_papers: list[Paper] = []
        source_names = ["Semantic Scholar", "OpenAlex", "CrossRef"]
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("Search failed for %s: %s", source_names[i], result)
                continue
            logger.info("%s returned %d papers", source_names[i], len(result))
            all_papers.extend(result)

        # Deduplicate by DOI
        deduplicated = self._deduplicate(all_papers)
        logger.info(
            "Total: %d papers found, %d after dedup",
            len(all_papers),
            len(deduplicated),
        )
        return deduplicated

    async def _search_semantic_scholar(
        self, query: str, limit: int
    ) -> list[Paper]:
        client = SemanticScholarClient()
        try:
            data = await client.search_papers(
                query=query,
                limit=min(limit, 100),
            )
            raw_papers = data.get("data") or []
            papers = []
            for raw in raw_papers:
                try:
                    paper = _s2_paper_to_paper(raw, "")
                    papers.append(paper)
                except Exception:
                    logger.debug("Failed to parse S2 result", exc_info=True)
            return papers
        finally:
            await client.close()

    async def _search_openalex(self, query: str, limit: int) -> list[Paper]:
        client = OpenAlexClient()
        try:
            data = await client.search_works(
                search=query,
                per_page=min(limit, 50),
            )
            works = data.get("results") or []
            papers = []
            for work in works:
                try:
                    paper = _openalex_work_to_paper(work, "")
                    papers.append(paper)
                except Exception:
                    logger.debug("Failed to parse OpenAlex result", exc_info=True)
            return papers
        finally:
            await client.close()

    async def _search_crossref(self, query: str, limit: int) -> list[Paper]:
        client = CrossRefClient()
        try:
            # Use query.bibliographic to search title/abstract only (less noise
            # than the generic query which matches against all metadata fields).
            data = await client.search_works(
                query_bibliographic=query,
                rows=min(limit, 50),
            )
            items = data.get("message", {}).get("items") or []
            query_keywords = _extract_keywords(query)
            papers = []
            for item in items:
                try:
                    # Filter out results whose title has zero keyword overlap
                    # with the search query — CrossRef is notoriously noisy.
                    title_list = item.get("title") or []
                    title = title_list[0].lower() if title_list else ""
                    if query_keywords and not any(kw in title for kw in query_keywords):
                        continue
                    paper = _crossref_item_to_paper(item, "")
                    papers.append(paper)
                except Exception:
                    logger.debug("Failed to parse CrossRef result", exc_info=True)
            logger.info(
                "CrossRef: %d items returned, %d after relevance filter",
                len(items),
                len(papers),
            )
            return papers
        finally:
            await client.close()

    def _deduplicate(self, papers: list[Paper]) -> list[Paper]:
        """Deduplicate papers by DOI and filter out those already in DB."""
        seen_dois: set[str] = set()
        unique: list[Paper] = []

        for paper in papers:
            doi = paper.doi
            if doi:
                doi_lower = doi.lower()
                if doi_lower in seen_dois:
                    continue
                seen_dois.add(doi_lower)
                # Check database for existing paper
                if self.db:
                    existing = self.db.get_paper_by_doi(doi)
                    if existing:
                        continue
            unique.append(paper)

        return unique
