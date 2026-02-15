"""Search for papers across multiple APIs by research topic keywords.

Supports LLM-powered multi-language query expansion: user input in any
language is expanded into multiple search queries in English, Chinese,
and the original language, maximising coverage across APIs that have
different language strengths.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from src.journal_monitor.sources.crossref import _crossref_item_to_paper
from src.journal_monitor.sources.openalex import _openalex_work_to_paper
from src.journal_monitor.sources.semantic_scholar import _s2_paper_to_paper
from src.knowledge_base.db import Database
from src.knowledge_base.models import Paper
from src.knowledge_base.vector_store import VectorStore
from src.literature_indexer.embeddings import generate_embedding
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

_QUERY_EXPANSION_PROMPT = """\
You are an academic research assistant. The user has provided a search query \
for finding academic papers. Your task is to expand this query into multiple \
search strings that will maximize coverage across academic databases \
(Semantic Scholar, OpenAlex, CrossRef).

Rules:
1. Always produce queries in BOTH English AND Chinese, regardless of the input language.
2. If the input is in another language (French, German, etc.), also include queries in that language.
3. Generate 4-6 search query strings total.
4. Each query should be a concise keyword phrase (3-8 words), NOT a full sentence.
5. Include both literal translations and conceptual expansions (related terms, synonyms, broader/narrower concepts).
6. Return ONLY a JSON array of strings, no explanation.

Example input: "中国 南斯拉夫 红色歌曲"
Example output: ["China Yugoslavia red songs", "Chinese Yugoslav revolutionary music cultural exchange", "中国南斯拉夫革命歌曲", "红色音乐 中南文化交流", "socialist revolutionary songs China Yugoslavia", "中南关系 红色文化"]

User query: "{query}"
"""


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful lowercase keywords from a search query."""
    import re

    tokens = re.split(r"\W+", query.lower())
    return [t for t in tokens if t and t not in _STOPWORDS and len(t) > 2]


def expand_query_with_llm(query: str, llm_router: Any) -> list[str]:
    """Use LLM to expand a search query into multilingual keyword phrases.

    Args:
        query: User's original search query in any language.
        llm_router: An LLMRouter instance.

    Returns:
        List of expanded search query strings. Falls back to [query] on error.
    """
    try:
        prompt = _QUERY_EXPANSION_PROMPT.format(query=query)
        response = llm_router.complete(
            task_type="query_expansion",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        text = llm_router.get_response_text(response).strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        queries = json.loads(text)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            # Always include the original query
            if query not in queries:
                queries.insert(0, query)
            logger.info("Query expansion: %r -> %d queries", query, len(queries))
            return queries
    except Exception:
        logger.warning("LLM query expansion failed, using original query", exc_info=True)
    return [query]


_RELEVANCE_FILTER_PROMPT = """\
You are an academic research assistant. The user searched for: "{query}"

Below is a numbered list of paper titles found. Select the {limit} MOST relevant \
papers for this research topic. Return ONLY a JSON array of the numbers (1-indexed), \
ordered by relevance (most relevant first). No explanation.

{paper_list}
"""


def filter_papers_by_relevance(
    query: str,
    papers: list[Paper],
    llm_router: Any,
    limit: int = 50,
) -> list[Paper]:
    """Use LLM to select the most relevant papers from a larger set.

    Args:
        query: Original user search query.
        papers: All candidate papers.
        llm_router: LLMRouter instance.
        limit: Max papers to keep.

    Returns:
        Filtered list of papers, ordered by relevance.
    """
    if len(papers) <= limit:
        return papers

    # Build numbered list of titles for the LLM
    lines = []
    for i, p in enumerate(papers, 1):
        title = (p.title or "Untitled")[:120]
        year = f" ({p.year})" if p.year else ""
        journal = f" — {p.journal}" if p.journal else ""
        lines.append(f"{i}. {title}{year}{journal}")
    paper_list = "\n".join(lines)

    try:
        prompt = _RELEVANCE_FILTER_PROMPT.format(
            query=query, limit=limit, paper_list=paper_list
        )
        response = llm_router.complete(
            task_type="query_expansion",  # lightweight, same route
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=1000,
        )
        text = llm_router.get_response_text(response).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        indices = json.loads(text)
        if isinstance(indices, list):
            selected = []
            seen = set()
            for idx in indices:
                i = int(idx) - 1  # convert to 0-indexed
                if 0 <= i < len(papers) and i not in seen:
                    selected.append(papers[i])
                    seen.add(i)
                if len(selected) >= limit:
                    break
            logger.info(
                "LLM relevance filter: %d -> %d papers", len(papers), len(selected)
            )
            return selected
    except Exception:
        logger.warning("LLM relevance filter failed, truncating", exc_info=True)

    # Fallback: just return first N
    return papers[:limit]


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

    async def search_topic_expanded(
        self,
        topic: str,
        llm_router: Any,
        max_results_per_source: int = 30,
        max_download: int = 50,
        progress_callback: Any = None,
    ) -> tuple[list[Paper], list[Paper]]:
        """Search with LLM-powered multi-language query expansion.

        Expands the user query into multiple languages/variants via LLM,
        then searches all API sources with each variant. Returns ALL
        deduplicated papers (for metadata storage) plus an LLM-filtered
        subset of the most relevant ones (for download/indexing).

        Args:
            topic: User's search query in any language.
            llm_router: LLMRouter for query expansion.
            max_results_per_source: Max results per API per query variant.
            max_download: Max papers to select for download/indexing.
            progress_callback: Optional async callable(progress, message).

        Returns:
            Tuple of (all_papers, top_papers):
              - all_papers: every deduplicated result (store metadata for all)
              - top_papers: LLM-selected most relevant subset (download these)
        """
        # Step 1: Expand query
        if progress_callback:
            await progress_callback(0.05, "Expanding search query with LLM...")
        queries = await asyncio.to_thread(expand_query_with_llm, topic, llm_router)

        if progress_callback:
            await progress_callback(0.10, f"Searching with {len(queries)} query variants...")

        # Step 2: Search with each query variant (limit per-query to avoid flooding)
        per_query_limit = max(10, max_results_per_source // len(queries))
        all_papers: list[Paper] = []

        for i, query in enumerate(queries):
            if progress_callback:
                frac = 0.10 + 0.45 * (i / len(queries))
                await progress_callback(frac, f"Searching: {query[:50]}...")

            try:
                papers = await self.search_topic(query, per_query_limit)
                all_papers.extend(papers)
                logger.info("Query %d/%d '%s': %d papers", i + 1, len(queries), query[:40], len(papers))
            except Exception:
                logger.warning("Search failed for query variant: %s", query[:40], exc_info=True)

        # Deduplicate across all query variants
        deduplicated = self._deduplicate(all_papers)
        logger.info(
            "Expanded search total: %d papers found, %d after dedup",
            len(all_papers),
            len(deduplicated),
        )

        # Step 3: LLM relevance filtering to select top papers for download
        if len(deduplicated) > max_download:
            if progress_callback:
                await progress_callback(
                    0.55, f"LLM selecting top {max_download} from {len(deduplicated)} papers..."
                )
            top_papers = await asyncio.to_thread(
                filter_papers_by_relevance, topic, deduplicated, llm_router, max_download
            )
        else:
            top_papers = deduplicated

        return deduplicated, top_papers

    async def search_local(
        self,
        query: str,
        vector_store: VectorStore,
        n_results: int = 20,
    ) -> list[dict]:
        """Search locally indexed papers in ChromaDB via semantic similarity.

        Args:
            query: Search query text.
            vector_store: VectorStore instance with indexed papers.
            n_results: Number of results to return.

        Returns:
            List of dicts with keys: paper_id, document, distance, metadata.
        """
        try:
            embedding = await asyncio.to_thread(
                generate_embedding, query, is_query=True
            )
            results = vector_store.search_papers(
                query_embedding=embedding,
                n_results=n_results,
            )
            hits = []
            ids = results.get("ids", [[]])[0]
            docs = results.get("documents", [[]])[0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            for j in range(len(ids)):
                hits.append({
                    "chunk_id": ids[j],
                    "paper_id": ids[j].rsplit("_chunk_", 1)[0] if "_chunk_" in ids[j] else ids[j],
                    "document": docs[j][:200] if docs[j] else "",
                    "distance": distances[j],
                    "metadata": metadatas[j] if j < len(metadatas) else {},
                })
            logger.info("Local semantic search for '%s': %d hits", query[:40], len(hits))
            return hits
        except Exception:
            logger.warning("Local semantic search failed", exc_info=True)
            return []

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
