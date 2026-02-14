"""DOI resolution and verification using multiple APIs."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.utils.api_clients import CrossRefClient, OpenAlexClient, SemanticScholarClient


class DOIResolver:
    """Resolves and verifies DOIs using CrossRef, Semantic Scholar, and OpenAlex."""

    def __init__(
        self,
        crossref_email: Optional[str] = None,
        s2_api_key: Optional[str] = None,
        openalex_email: Optional[str] = None,
    ):
        self.crossref = CrossRefClient(email=crossref_email)
        self.s2 = SemanticScholarClient(api_key=s2_api_key)
        self.openalex = OpenAlexClient(email=openalex_email)

    async def resolve_doi(self, doi: str) -> Optional[dict]:
        """Resolve a DOI to its metadata using CrossRef."""
        try:
            result = await self.crossref.get_work_by_doi(doi)
            if result and "message" in result:
                msg = result["message"]
                return self._normalize_crossref(msg)
        except Exception:
            pass
        return None

    async def verify_reference(
        self,
        title: str,
        authors: list[str],
        year: int,
        doi: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Triple-verify a reference across CrossRef, Semantic Scholar, and OpenAlex.

        Returns verified metadata dict or None if unverifiable.
        """
        results: list[Optional[dict]] = []

        # Strategy 1: DOI lookup (most reliable)
        if doi:
            cr_result = await self.resolve_doi(doi)
            if cr_result:
                return {**cr_result, "verification_source": "crossref_doi"}

        # Strategy 2: Title search across APIs (parallel)
        tasks = [
            self._search_crossref(title, authors, year),
            self._search_semantic_scholar(title, authors, year),
            self._search_openalex(title, authors, year),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict) and result:
                return result

        return None

    async def _search_crossref(
        self, title: str, authors: list[str], year: int
    ) -> Optional[dict]:
        """Search CrossRef for a reference by title."""
        try:
            query = title
            result = await self.crossref.search_works(query=query, rows=5)
            if result and "message" in result and "items" in result["message"]:
                for item in result["message"]["items"]:
                    if self._is_title_match(title, item.get("title", [""])):
                        return {
                            **self._normalize_crossref(item),
                            "verification_source": "crossref_search",
                        }
        except Exception:
            pass
        return None

    async def _search_semantic_scholar(
        self, title: str, authors: list[str], year: int
    ) -> Optional[dict]:
        """Search Semantic Scholar for a reference."""
        try:
            result = await self.s2.search_papers(query=title, limit=5)
            if result and "data" in result:
                for paper in result["data"]:
                    if self._is_title_match(title, [paper.get("title", "")]):
                        ext_ids = paper.get("externalIds", {})
                        return {
                            "title": paper["title"],
                            "authors": [
                                a.get("name", "") for a in paper.get("authors", [])
                            ],
                            "year": paper.get("year"),
                            "doi": ext_ids.get("DOI"),
                            "semantic_scholar_id": paper.get("paperId"),
                            "verification_source": "semantic_scholar",
                        }
        except Exception:
            pass
        return None

    async def _search_openalex(
        self, title: str, authors: list[str], year: int
    ) -> Optional[dict]:
        """Search OpenAlex for a reference."""
        try:
            result = await self.openalex.search_works(search=title, per_page=5)
            if result and "results" in result:
                for work in result["results"]:
                    work_title = work.get("title", "")
                    if self._is_title_match(title, [work_title]):
                        authorships = work.get("authorships", [])
                        author_names = [
                            a.get("author", {}).get("display_name", "")
                            for a in authorships
                        ]
                        return {
                            "title": work_title,
                            "authors": author_names,
                            "year": work.get("publication_year"),
                            "doi": work.get("doi", "").replace("https://doi.org/", "")
                            if work.get("doi")
                            else None,
                            "openalex_id": work.get("id"),
                            "verification_source": "openalex",
                        }
        except Exception:
            pass
        return None

    def _normalize_crossref(self, item: dict) -> dict:
        """Normalize a CrossRef item to a standard dict."""
        title_list = item.get("title", [])
        title = title_list[0] if title_list else ""

        authors = []
        for author in item.get("author", []):
            name = f"{author.get('given', '')} {author.get('family', '')}".strip()
            if name:
                authors.append(name)

        year = None
        date_parts = item.get("published-print", item.get("published-online", {}))
        if date_parts and "date-parts" in date_parts:
            parts = date_parts["date-parts"]
            if parts and parts[0]:
                year = parts[0][0]

        journal = ""
        container = item.get("container-title", [])
        if container:
            journal = container[0]

        return {
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "volume": item.get("volume"),
            "issue": item.get("issue"),
            "pages": item.get("page"),
            "doi": item.get("DOI"),
            "publisher": item.get("publisher"),
        }

    @staticmethod
    def _is_title_match(query_title: str, candidate_titles: list[str]) -> bool:
        """Check if titles match (fuzzy, case-insensitive)."""
        query_clean = query_title.lower().strip().rstrip(".")
        for candidate in candidate_titles:
            if not candidate:
                continue
            candidate_clean = candidate.lower().strip().rstrip(".")
            # Exact match
            if query_clean == candidate_clean:
                return True
            # One contains the other (for subtitle variations)
            if query_clean in candidate_clean or candidate_clean in query_clean:
                return True
            # Word overlap > 80%
            q_words = set(query_clean.split())
            c_words = set(candidate_clean.split())
            if q_words and c_words:
                overlap = len(q_words & c_words) / max(len(q_words), len(c_words))
                if overlap > 0.8:
                    return True
        return False

    async def close(self) -> None:
        await asyncio.gather(
            self.crossref.close(),
            self.s2.close(),
            self.openalex.close(),
        )
