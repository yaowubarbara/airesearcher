"""Shared API client wrappers for external services."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

# Rate limit defaults (requests per second)
RATE_LIMITS = {
    "semantic_scholar": 3,
    "openalex": 10,
    "crossref": 5,
    "cnki": 1,
}

# Common headers
USER_AGENT = "AIResearcher/0.1 (academic-research-tool; mailto:researcher@example.com)"


class APIClient:
    """Base async HTTP client with rate limiting and retries."""

    def __init__(
        self,
        base_url: str,
        rate_limit: float = 5.0,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.rate_limit = rate_limit
        self.api_key = api_key
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(int(rate_limit))
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"User-Agent": USER_AGENT}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def get(
        self,
        path: str,
        params: Optional[dict] = None,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Make a GET request with rate limiting and retries."""
        client = await self._get_client()
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            async with self._semaphore:
                try:
                    response = await client.get(path, params=params)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        # Rate limited - wait and retry
                        wait_time = 2 ** (attempt + 1)
                        await asyncio.sleep(wait_time)
                        last_error = e
                        continue
                    raise
                except (httpx.ConnectError, httpx.ReadTimeout) as e:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    last_error = e
                    continue

        raise last_error or RuntimeError("Request failed after retries")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class SemanticScholarClient(APIClient):
    """Client for the Semantic Scholar API."""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            base_url="https://api.semanticscholar.org/graph/v1",
            rate_limit=RATE_LIMITS["semantic_scholar"],
            api_key=api_key,
        )
        # S2 uses x-api-key header instead of Bearer
        self._api_key_header = api_key

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"User-Agent": USER_AGENT}
            if self._api_key_header:
                headers["x-api-key"] = self._api_key_header
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def search_papers(
        self,
        query: str,
        venue: Optional[str] = None,
        year: Optional[str] = None,
        limit: int = 20,
        fields: str = "title,authors,abstract,year,venue,externalIds,publicationDate,openAccessPdf",
    ) -> dict:
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "fields": fields,
        }
        if venue:
            params["venue"] = venue
        if year:
            params["year"] = year
        return await self.get("/paper/search", params=params)

    async def get_paper(self, paper_id: str) -> dict:
        fields = "title,authors,abstract,year,venue,externalIds,references,citations,publicationDate,journal"
        return await self.get(f"/paper/{paper_id}", params={"fields": fields})


class OpenAlexClient(APIClient):
    """Client for the OpenAlex API."""

    def __init__(self, email: Optional[str] = None):
        super().__init__(
            base_url="https://api.openalex.org",
            rate_limit=RATE_LIMITS["openalex"],
        )
        self.email = email

    async def search_works(
        self,
        source_id: Optional[str] = None,
        from_date: Optional[str] = None,
        search: Optional[str] = None,
        per_page: int = 25,
        page: int = 1,
    ) -> dict:
        params: dict[str, Any] = {
            "per_page": per_page,
            "page": page,
        }
        if self.email:
            params["mailto"] = self.email

        filters = []
        if source_id:
            filters.append(f"primary_location.source.id:{source_id}")
        if from_date:
            filters.append(f"from_publication_date:{from_date}")
        if filters:
            params["filter"] = ",".join(filters)
        if search:
            params["search"] = search

        return await self.get("/works", params=params)

    async def get_work(self, work_id: str) -> dict:
        return await self.get(f"/works/{work_id}")

    async def get_work_references(self, work_id: str, limit: int = 50) -> list[dict]:
        """Get works referenced by this work (backward citations).

        Fetches the work, extracts referenced_works IDs, batch-fetches metadata.
        """
        work = await self.get_work(work_id)
        ref_ids = work.get("referenced_works", [])[:limit]
        if not ref_ids:
            return []
        # Batch fetch: filter=openalex_id:W123|W456|W789
        id_filter = "|".join(ref_ids)
        result = await self.get("/works", params={
            "filter": f"openalex_id:{id_filter}",
            "per_page": limit,
            "select": "id,title,authorships,publication_year,primary_location,doi,cited_by_count",
        })
        return result.get("results", [])

    async def get_citing_works(self, work_id: str, limit: int = 30) -> list[dict]:
        """Get works that cite this work (forward citations), sorted by citation count."""
        result = await self.get("/works", params={
            "filter": f"cites:{work_id}",
            "sort": "cited_by_count:desc",
            "per_page": limit,
            "select": "id,title,authorships,publication_year,primary_location,doi,cited_by_count",
        })
        return result.get("results", [])

    async def search_author(self, name: str) -> Optional[str]:
        """Search for an author, return their OpenAlex ID."""
        result = await self.get("/authors", params={"search": name, "per_page": 1})
        results = result.get("results", [])
        return results[0]["id"] if results else None

    async def get_author_works(self, author_id: str, limit: int = 20) -> list[dict]:
        """Get works by a specific author, sorted by citation count."""
        result = await self.get("/works", params={
            "filter": f"authorships.author.id:{author_id}",
            "sort": "cited_by_count:desc",
            "per_page": limit,
            "select": "id,title,authorships,publication_year,primary_location,doi,cited_by_count",
        })
        return result.get("results", [])

    async def search_works_in_journal(self, query: str, journal_name: str, limit: int = 20) -> list[dict]:
        """Search within a specific journal."""
        result = await self.get("/works", params={
            "search": query,
            "filter": f"primary_location.source.display_name.search:{journal_name}",
            "per_page": limit,
            "select": "id,title,authorships,publication_year,primary_location,doi,cited_by_count",
        })
        return result.get("results", [])


class CrossRefClient(APIClient):
    """Client for the CrossRef API."""

    def __init__(self, email: Optional[str] = None):
        super().__init__(
            base_url="https://api.crossref.org",
            rate_limit=RATE_LIMITS["crossref"],
        )
        self.email = email

    async def search_works(
        self,
        query: Optional[str] = None,
        query_bibliographic: Optional[str] = None,
        issn: Optional[str] = None,
        from_date: Optional[str] = None,
        rows: int = 20,
    ) -> dict:
        params: dict[str, Any] = {"rows": rows}
        if self.email:
            params["mailto"] = self.email
        if query_bibliographic:
            params["query.bibliographic"] = query_bibliographic
        elif query:
            params["query"] = query

        filters = []
        if issn:
            filters.append(f"issn:{issn}")
        if from_date:
            filters.append(f"from-pub-date:{from_date}")
        if filters:
            params["filter"] = ",".join(filters)

        return await self.get("/works", params=params)

    async def get_work_by_doi(self, doi: str) -> dict:
        return await self.get(f"/works/{doi}")

    async def verify_doi(self, doi: str) -> Optional[dict]:
        """Verify a DOI exists and return its metadata."""
        try:
            result = await self.get_work_by_doi(doi)
            if result and "message" in result:
                return result["message"]
        except Exception:
            pass
        return None


class UnpaywallClient(APIClient):
    """Client for the Unpaywall API (free, DOI-based OA lookup)."""

    def __init__(self, email: Optional[str] = None):
        import os

        self.email = email or os.environ.get("UNPAYWALL_EMAIL", "researcher@example.com")
        super().__init__(
            base_url="https://api.unpaywall.org/v2",
            rate_limit=10.0,
        )

    async def get_oa_urls(self, doi: str) -> list[str]:
        """Return list of OA PDF URLs for a DOI, best first.

        Tries best_oa_location first, then iterates oa_locations[].
        Returns empty list if no OA URLs found.
        """
        try:
            data = await self.get(f"/{doi}", params={"email": self.email})
        except Exception:
            return []

        urls: list[str] = []
        # Best OA location first
        best = data.get("best_oa_location") or {}
        if best.get("url_for_pdf"):
            urls.append(best["url_for_pdf"])

        # Iterate other locations
        for loc in data.get("oa_locations") or []:
            pdf_url = loc.get("url_for_pdf")
            if pdf_url and pdf_url not in urls:
                urls.append(pdf_url)

        return urls


class COREClient(APIClient):
    """Client for the CORE API (200M+ OA papers from institutional repos)."""

    def __init__(self, api_key: Optional[str] = None):
        import os

        key = api_key or os.environ.get("CORE_API_KEY")
        super().__init__(
            base_url="https://api.core.ac.uk/v3",
            rate_limit=5.0,
            api_key=key,
        )

    async def search_by_doi(self, doi: str) -> Optional[str]:
        """Search CORE by DOI, return download URL if found."""
        try:
            data = await self.get(
                "/search/works",
                params={"q": f'doi:"{doi}"', "limit": 1},
            )
            results = data.get("results") or []
            if results:
                return results[0].get("downloadUrl")
        except Exception:
            pass
        return None

    async def search_by_title(self, title: str) -> list[dict[str, Any]]:
        """Search CORE by title, return list of {title, downloadUrl} dicts."""
        try:
            data = await self.get(
                "/search/works",
                params={"q": f'title:"{title}"', "limit": 5},
            )
            results = data.get("results") or []
            return [
                {
                    "title": r.get("title", ""),
                    "downloadUrl": r.get("downloadUrl"),
                }
                for r in results
                if r.get("downloadUrl")
            ]
        except Exception:
            return []
