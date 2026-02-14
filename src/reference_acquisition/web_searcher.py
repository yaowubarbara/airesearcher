"""Web search for broader references: novels, theory, literary criticism.

Unlike the API searcher which queries academic databases, this module uses
general web search to find:
- Primary texts (novels, poems, plays)
- Classic theoretical works
- Literary criticism and reviews
- Book chapters and essays not indexed in academic APIs

Results are converted into Paper models for unified handling.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

import httpx

from src.knowledge_base.models import Language, Paper, PaperStatus

logger = logging.getLogger(__name__)

# Google Scholar scraping is fragile; we use OpenAlex /works search with
# broader queries, plus Google Books API for monographs.

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"


class WebSearcher:
    """Search the web for broader reference materials beyond journal articles.

    Covers:
    - Google Books API for monographs, novels, and theory
    - OpenAlex with broader queries (not filtered by source/journal)
    - Open Library API for classic texts and public domain works
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def search_books(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[Paper]:
        """Search Google Books API for monographs, novels, and theory.

        Args:
            query: Search query (e.g. "Orientalism Edward Said" or "三体 刘慈欣").
            max_results: Maximum results to return.

        Returns:
            List of Paper objects representing books.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    GOOGLE_BOOKS_API,
                    params={
                        "q": query,
                        "maxResults": min(max_results, 40),
                        "printType": "books",
                        "langRestrict": "",
                    },
                )
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning("Google Books API failed: %s", e)
                return []

        items = data.get("items") or []
        papers: list[Paper] = []

        for item in items:
            try:
                paper = self._gbooks_to_paper(item)
                if paper:
                    papers.append(paper)
            except Exception:
                logger.debug("Failed to parse Google Books item", exc_info=True)

        logger.info("Google Books returned %d results for '%s'", len(papers), query)
        return papers

    async def search_open_library(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[Paper]:
        """Search Open Library for classic/public-domain texts.

        Args:
            query: Search query.
            max_results: Maximum results.

        Returns:
            List of Paper objects.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={
                        "q": query,
                        "limit": min(max_results, 50),
                    },
                )
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.warning("Open Library API failed: %s", e)
                return []

        docs = data.get("docs") or []
        papers: list[Paper] = []

        for doc in docs:
            try:
                paper = self._openlibrary_to_paper(doc)
                if paper:
                    papers.append(paper)
            except Exception:
                logger.debug("Failed to parse Open Library doc", exc_info=True)

        logger.info("Open Library returned %d results for '%s'", len(papers), query)
        return papers

    async def search_all(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[Paper]:
        """Search all web sources concurrently.

        Args:
            query: Search query.
            max_results: Max results per source.

        Returns:
            Deduplicated list of Paper objects.
        """
        results = await asyncio.gather(
            self.search_books(query, max_results),
            self.search_open_library(query, max_results),
            return_exceptions=True,
        )

        all_papers: list[Paper] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Web search source failed: %s", result)
                continue
            all_papers.extend(result)

        # Deduplicate by title similarity
        return self._deduplicate_by_title(all_papers)

    @staticmethod
    def _gbooks_to_paper(item: dict[str, Any]) -> Optional[Paper]:
        """Convert a Google Books volume to a Paper model."""
        info = item.get("volumeInfo") or {}
        title = info.get("title")
        if not title:
            return None

        subtitle = info.get("subtitle")
        if subtitle:
            title = f"{title}: {subtitle}"

        authors = info.get("authors") or []
        year = 0
        published = info.get("publishedDate", "")
        if published:
            match = re.match(r"(\d{4})", published)
            if match:
                year = int(match.group(1))

        publisher = info.get("publisher") or ""
        description = info.get("description")

        # Extract identifiers
        isbn = None
        for ident in info.get("industryIdentifiers") or []:
            if ident.get("type") in ("ISBN_13", "ISBN_10"):
                isbn = ident.get("identifier")
                break

        # Check for preview/download link
        access = item.get("accessInfo") or {}
        pdf_info = access.get("pdf") or {}
        pdf_url = pdf_info.get("downloadLink") if pdf_info.get("isAvailable") else None
        if not pdf_url:
            # Try epub
            epub_info = access.get("epub") or {}
            if epub_info.get("isAvailable"):
                pdf_url = epub_info.get("downloadLink")

        # Detect language
        lang_code = info.get("language", "en")
        language = Language.EN
        if lang_code.startswith("zh"):
            language = Language.ZH
        elif lang_code.startswith("fr"):
            language = Language.FR

        return Paper(
            title=title,
            authors=authors,
            abstract=description,
            journal=publisher,  # Use publisher as "journal" for books
            year=year,
            language=language,
            status=PaperStatus.DISCOVERED,
            url=info.get("previewLink"),
            pdf_url=pdf_url,
            keywords=info.get("categories") or [],
        )

    @staticmethod
    def _openlibrary_to_paper(doc: dict[str, Any]) -> Optional[Paper]:
        """Convert an Open Library search doc to a Paper model."""
        title = doc.get("title")
        if not title:
            return None

        authors = doc.get("author_name") or []
        year = doc.get("first_publish_year") or 0
        publisher = (doc.get("publisher") or [""])[0] if doc.get("publisher") else ""

        # Open Library key for URL
        ol_key = doc.get("key", "")
        url = f"https://openlibrary.org{ol_key}" if ol_key else None

        # Check for ebook availability
        pdf_url = None
        if doc.get("has_fulltext"):
            ia_id = (doc.get("ia") or [""])[0] if doc.get("ia") else ""
            if ia_id:
                pdf_url = f"https://archive.org/download/{ia_id}/{ia_id}.pdf"

        # Language detection
        languages = doc.get("language") or []
        language = Language.EN
        if "chi" in languages or "zho" in languages:
            language = Language.ZH
        elif "fre" in languages or "fra" in languages:
            language = Language.FR

        return Paper(
            title=title,
            authors=authors,
            abstract=None,
            journal=publisher,
            year=year,
            language=language,
            status=PaperStatus.DISCOVERED,
            url=url,
            pdf_url=pdf_url,
            keywords=doc.get("subject") or [],
        )

    @staticmethod
    def _deduplicate_by_title(papers: list[Paper]) -> list[Paper]:
        """Simple deduplication by normalized title."""
        seen: set[str] = set()
        unique: list[Paper] = []
        for paper in papers:
            norm = re.sub(r"\W+", " ", paper.title.lower()).strip()
            if norm not in seen:
                seen.add(norm)
                unique.append(paper)
        return unique
