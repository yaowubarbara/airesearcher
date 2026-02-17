"""Multi-source Open Access resolver for finding full-text PDF URLs."""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

from src.knowledge_base.models import Paper
from src.utils.api_clients import COREClient, UnpaywallClient

logger = logging.getLogger(__name__)


def _jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two title strings."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _extract_arxiv_id(paper: Paper) -> Optional[str]:
    """Extract arXiv ID from paper's external_ids, DOI, or openalex_id."""
    # From external_ids (Semantic Scholar stores as "ArXiv")
    if paper.external_ids:
        arxiv_id = paper.external_ids.get("ArXiv")
        if arxiv_id:
            return arxiv_id

    # From DOI like "10.48550/arXiv.2301.12345"
    if paper.doi:
        m = re.search(r"arXiv\.(\d{4}\.\d{4,5}(?:v\d+)?)", paper.doi, re.IGNORECASE)
        if m:
            return m.group(1)

    # From openalex_id — OpenAlex sometimes stores arXiv as alternate location
    # Pattern: openalex_id won't contain arXiv info, but url might
    if paper.url and "arxiv.org" in paper.url:
        m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", paper.url)
        if m:
            return m.group(1)

    return None


class OAResolver:
    """Resolve open-access PDF URLs by trying multiple sources in priority order.

    Sources tried (stops at first success):
    1. Unpaywall — best_oa_location, then oa_locations[]
    2. CORE — DOI search, then title search with Jaccard > 0.8
    3. arXiv — direct URL construction from arXiv ID
    4. Europe PMC — PMCID lookup for free full text
    5. DOI content negotiation — HEAD request with Accept: application/pdf
    """

    def __init__(self):
        self._unpaywall: Optional[UnpaywallClient] = None
        self._core: Optional[COREClient] = None

    @property
    def unpaywall(self) -> UnpaywallClient:
        if self._unpaywall is None:
            self._unpaywall = UnpaywallClient()
        return self._unpaywall

    @property
    def core(self) -> COREClient:
        if self._core is None:
            self._core = COREClient()
        return self._core

    async def resolve_pdf_url(self, paper: Paper) -> Optional[str]:
        """Try multiple OA sources to find a PDF URL for the paper.

        Returns the first successful URL, or None if all sources fail.
        """
        # 1. Unpaywall (DOI required)
        if paper.doi:
            url = await self._try_unpaywall(paper.doi)
            if url:
                logger.info("Unpaywall resolved: %s -> %s", paper.doi, url)
                return url

        # 2. CORE
        url = await self._try_core(paper)
        if url:
            logger.info("CORE resolved: %s -> %s", paper.title[:50], url)
            return url

        # 3. arXiv direct
        url = self._try_arxiv(paper)
        if url:
            logger.info("arXiv resolved: %s -> %s", paper.title[:50], url)
            return url

        # 4. Europe PMC
        if paper.doi or (paper.external_ids and paper.external_ids.get("PMID")):
            url = await self._try_europepmc(paper)
            if url:
                logger.info("Europe PMC resolved: %s -> %s", paper.title[:50], url)
                return url

        # 5. DOI content negotiation
        if paper.doi:
            url = await self._try_doi_negotiation(paper.doi)
            if url:
                logger.info("DOI negotiation resolved: %s -> %s", paper.doi, url)
                return url

        return None

    async def resolve_many(self, papers: list[Paper]) -> dict[str, Optional[str]]:
        """Resolve PDF URLs for multiple papers concurrently.

        Returns dict mapping paper ID (or title) to resolved URL (or None).
        """
        import asyncio
        sem = asyncio.Semaphore(10)

        async def _resolve_one(paper: Paper):
            async with sem:
                key = paper.id or paper.title
                url = await self.resolve_pdf_url(paper)
                return key, url

        results_list = await asyncio.gather(
            *[_resolve_one(p) for p in papers],
            return_exceptions=True,
        )
        results: dict[str, Optional[str]] = {}
        for r in results_list:
            if isinstance(r, Exception):
                continue
            results[r[0]] = r[1]
        return results

    async def _try_unpaywall(self, doi: str) -> Optional[str]:
        """Query Unpaywall for OA PDF URLs."""
        try:
            urls = await self.unpaywall.get_oa_urls(doi)
            return urls[0] if urls else None
        except Exception:
            logger.debug("Unpaywall lookup failed for DOI %s", doi, exc_info=True)
            return None

    async def _try_core(self, paper: Paper) -> Optional[str]:
        """Search CORE by DOI, then by title with similarity check."""
        # Try DOI first
        if paper.doi:
            try:
                url = await self.core.search_by_doi(paper.doi)
                if url:
                    return url
            except Exception:
                logger.debug("CORE DOI search failed for %s", paper.doi, exc_info=True)

        # Try title search with similarity threshold
        try:
            results = await self.core.search_by_title(paper.title)
            for result in results:
                sim = _jaccard_similarity(paper.title, result["title"])
                if sim > 0.8 and result.get("downloadUrl"):
                    return result["downloadUrl"]
        except Exception:
            logger.debug("CORE title search failed for %s", paper.title[:50], exc_info=True)

        return None

    def _try_arxiv(self, paper: Paper) -> Optional[str]:
        """Construct arXiv PDF URL from arXiv ID if available."""
        arxiv_id = _extract_arxiv_id(paper)
        if arxiv_id:
            return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        return None

    async def _try_europepmc(self, paper: Paper) -> Optional[str]:
        """Query Europe PMC for free full-text PDF via PMCID."""
        try:
            # Build query — prefer DOI, fall back to PMID
            if paper.doi:
                query = f"DOI:{paper.doi}"
            elif paper.external_ids and paper.external_ids.get("PMID"):
                query = f"EXT_ID:{paper.external_ids['PMID']}"
            else:
                return None

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                    params={
                        "query": query,
                        "format": "json",
                        "resultType": "core",
                        "pageSize": 1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("resultList", {}).get("result", [])
            if not results:
                return None

            result = results[0]
            pmcid = result.get("pmcid")
            if pmcid:
                return f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"

        except Exception:
            logger.debug("Europe PMC lookup failed", exc_info=True)

        return None

    async def _try_doi_negotiation(self, doi: str) -> Optional[str]:
        """Try DOI content negotiation — HEAD request with Accept: application/pdf."""
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={
                    "Accept": "application/pdf",
                    "User-Agent": "AIResearcher/0.1 (mailto:researcher@example.com)",
                },
            ) as client:
                resp = await client.head(f"https://doi.org/{doi}")
                content_type = resp.headers.get("content-type", "")
                if "application/pdf" in content_type and resp.status_code == 200:
                    return str(resp.url)
        except Exception:
            logger.debug("DOI content negotiation failed for %s", doi, exc_info=True)

        return None

    async def close(self) -> None:
        """Close underlying HTTP clients."""
        if self._unpaywall:
            await self._unpaywall.close()
        if self._core:
            await self._core.close()
