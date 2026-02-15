"""Verification engine: checks citations against CrossRef and OpenAlex."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.citation_verifier.parser import ParsedCitation
from src.utils.api_clients import CrossRefClient, OpenAlexClient


@dataclass
class CitationVerification:
    """Result of verifying a single citation."""

    citation: ParsedCitation
    status: str  # "verified", "work_not_found", "page_unverifiable", "page_out_of_range"
    confidence: float = 0.0
    matched_work: Optional[dict[str, Any]] = None
    page_range: Optional[str] = None  # e.g. "276-311" from CrossRef
    page_in_range: Optional[bool] = None
    notes: str = ""
    source: Optional[str] = None  # "crossref", "openalex"


def _is_title_match(query_title: str, candidate_titles: list[str]) -> bool:
    """Check if titles match (fuzzy, case-insensitive).

    Replicates the logic from reference_verifier/doi_resolver.py.
    """
    query_clean = query_title.lower().strip().rstrip(".")
    for candidate in candidate_titles:
        if not candidate:
            continue
        candidate_clean = candidate.lower().strip().rstrip(".")
        if query_clean == candidate_clean:
            return True
        if query_clean in candidate_clean or candidate_clean in query_clean:
            return True
        q_words = set(query_clean.split())
        c_words = set(candidate_clean.split())
        if q_words and c_words:
            overlap = len(q_words & c_words) / max(len(q_words), len(c_words))
            if overlap > 0.8:
                return True
    return False


def _normalize_crossref(item: dict) -> dict[str, Any]:
    """Normalize a CrossRef work item to a standard dict."""
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
        "type": item.get("type", ""),
    }


class CitationVerificationEngine:
    """Verifies inline citations against CrossRef and OpenAlex APIs."""

    def __init__(
        self,
        crossref_email: Optional[str] = None,
        openalex_email: Optional[str] = None,
    ):
        self.crossref = CrossRefClient(email=crossref_email)
        self.openalex = OpenAlexClient(email=openalex_email)
        self._cache: dict[str, Optional[dict[str, Any]]] = {}

    async def verify_all(
        self,
        citations: list[ParsedCitation],
        manuscript_text: str,
    ) -> list[CitationVerification]:
        """Verify all parsed citations.

        Returns a CitationVerification for each input citation.
        """
        results: list[CitationVerification] = []
        semaphore = asyncio.Semaphore(5)

        async def _verify_one(c: ParsedCitation) -> CitationVerification:
            async with semaphore:
                return await self._verify_citation(c, manuscript_text)

        tasks = [_verify_one(c) for c in citations]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for i, outcome in enumerate(outcomes):
            if isinstance(outcome, CitationVerification):
                results.append(outcome)
            else:
                results.append(CitationVerification(
                    citation=citations[i],
                    status="work_not_found",
                    confidence=0.0,
                    notes=f"Error during verification: {outcome}",
                ))

        return results

    async def _verify_citation(
        self,
        citation: ParsedCitation,
        manuscript_text: str,
    ) -> CitationVerification:
        """Verify a single citation."""
        # Determine search terms
        author = citation.author or citation.mediating_author
        title_hint = citation.title

        # If no title in citation, try to extract from surrounding text
        if not title_hint and author:
            title_hint = self._extract_context_title(
                author, manuscript_text, citation.start_pos
            )

        if not author and not title_hint:
            return CitationVerification(
                citation=citation,
                status="work_not_found",
                confidence=0.0,
                notes="No author or title to search",
            )

        # Search for the work
        work = await self._search_by_author_title(author, title_hint)

        if not work:
            return CitationVerification(
                citation=citation,
                status="work_not_found",
                confidence=0.0,
                notes=f"No match found for {author or ''} / {title_hint or ''}",
            )

        # Check page range
        if citation.pages:
            page_ok, page_note = self._check_page_range(
                citation.pages, work.get("pages"), work.get("type", "")
            )
            if page_ok is True:
                return CitationVerification(
                    citation=citation,
                    status="verified",
                    confidence=1.0,
                    matched_work=work,
                    page_range=work.get("pages"),
                    page_in_range=True,
                    source=work.get("_source", "crossref"),
                )
            elif page_ok is False:
                return CitationVerification(
                    citation=citation,
                    status="page_out_of_range",
                    confidence=0.5,
                    matched_work=work,
                    page_range=work.get("pages"),
                    page_in_range=False,
                    notes=page_note,
                    source=work.get("_source", "crossref"),
                )
            else:
                # page_ok is None — cannot verify (book, no page field)
                return CitationVerification(
                    citation=citation,
                    status="page_unverifiable",
                    confidence=0.7,
                    matched_work=work,
                    page_range=work.get("pages"),
                    page_in_range=None,
                    notes=page_note,
                    source=work.get("_source", "crossref"),
                )
        else:
            # No page cited — work found is enough
            return CitationVerification(
                citation=citation,
                status="verified",
                confidence=0.9,
                matched_work=work,
                source=work.get("_source", "crossref"),
                notes="Work found, no page to verify",
            )

    async def _search_by_author_title(
        self,
        author: Optional[str],
        title_hint: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Search CrossRef and OpenAlex for a work by author and/or title."""
        cache_key = f"{(author or '').lower()}|{(title_hint or '').lower()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        query_parts = []
        if author:
            query_parts.append(author)
        if title_hint:
            query_parts.append(title_hint)
        query = " ".join(query_parts)

        if not query.strip():
            self._cache[cache_key] = None
            return None

        # Try CrossRef first
        work = await self._search_crossref(query, author, title_hint)
        if work:
            work["_source"] = "crossref"
            self._cache[cache_key] = work
            return work

        # Fall back to OpenAlex
        work = await self._search_openalex(query, author, title_hint)
        if work:
            work["_source"] = "openalex"
            self._cache[cache_key] = work
            return work

        self._cache[cache_key] = None
        return None

    async def _search_crossref(
        self,
        query: str,
        author: Optional[str],
        title_hint: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Search CrossRef for a matching work."""
        try:
            result = await self.crossref.search_works(
                query_bibliographic=query, rows=5
            )
            if not result or "message" not in result:
                return None
            items = result["message"].get("items", [])
            for item in items:
                normalized = _normalize_crossref(item)
                if self._matches(normalized, author, title_hint):
                    return normalized
        except Exception:
            pass
        return None

    async def _search_openalex(
        self,
        query: str,
        author: Optional[str],
        title_hint: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Search OpenAlex for a matching work."""
        try:
            result = await self.openalex.search_works(search=query, per_page=5)
            if not result or "results" not in result:
                return None
            for work in result["results"]:
                work_title = work.get("title", "")
                authorships = work.get("authorships", [])
                author_names = [
                    a.get("author", {}).get("display_name", "")
                    for a in authorships
                ]
                normalized = {
                    "title": work_title,
                    "authors": author_names,
                    "year": work.get("publication_year"),
                    "doi": (work.get("doi") or "").replace(
                        "https://doi.org/", ""
                    ),
                    "type": work.get("type", ""),
                    "pages": None,  # OpenAlex doesn't reliably have page info
                }
                if self._matches(normalized, author, title_hint):
                    return normalized
        except Exception:
            pass
        return None

    def _matches(
        self,
        work: dict[str, Any],
        author: Optional[str],
        title_hint: Optional[str],
    ) -> bool:
        """Check if a work matches the author and/or title hint."""
        if title_hint:
            work_titles = [work.get("title", "")]
            if _is_title_match(title_hint, work_titles):
                return True

        if author:
            work_authors = work.get("authors", [])
            author_lower = author.lower()
            for wa in work_authors:
                if author_lower in wa.lower():
                    return True
                # Check surname match
                parts = wa.split()
                if parts and parts[-1].lower() == author_lower:
                    return True

        return False

    @staticmethod
    def _extract_context_title(
        author: str,
        text: str,
        citation_pos: int,
    ) -> Optional[str]:
        """Scan text before citation for a title associated with the author.

        Looks for patterns like: Author's *Title* or Author, *Title*
        within 500 chars before the citation.
        """
        start = max(0, citation_pos - 500)
        context = text[start:citation_pos]

        # Look for Author's *Title* or Author ... *Title*
        author_esc = re.escape(author)
        patterns = [
            # Author's *Title*
            rf"{author_esc}(?:'s|s')?\s+\*([^*]+)\*",
            # Author, *Title*
            rf"{author_esc},?\s+\*([^*]+)\*",
            # in *Title* ... by Author (reverse order)
            rf"\*([^*]+)\*[^*]{{0,100}}{author_esc}",
        ]

        for pat in patterns:
            m = re.search(pat, context, re.IGNORECASE)
            if m:
                return m.group(1)

        return None

    @staticmethod
    def _check_page_range(
        cited_page: str,
        work_pages: Optional[str],
        work_type: str,
    ) -> tuple[Optional[bool], str]:
        """Check if cited page falls within the work's page range.

        Returns:
            (True, note) — page is within range (journal article)
            (False, note) — page is outside range
            (None, note) — cannot verify (book, no page field, etc.)
        """
        # Book types — cannot verify internal page numbers
        book_types = {
            "book", "monograph", "book-chapter", "edited-book",
            "reference-book", "book-section",
        }
        if work_type in book_types:
            return None, "Book page numbers cannot be verified without PDF"

        if not work_pages:
            return None, "No page range available from metadata"

        # Parse the work's page range
        range_match = re.match(
            r"(\d+)\s*[-\u2013]\s*(\d+)", work_pages
        )
        if not range_match:
            return None, f"Cannot parse page range: {work_pages}"

        range_start = int(range_match.group(1))
        range_end = int(range_match.group(2))

        # Parse cited page(s)
        cited_match = re.match(
            r"(\d+)(?:\s*[-\u2013]\s*(\d+))?", cited_page
        )
        if not cited_match:
            return None, f"Cannot parse cited page: {cited_page}"

        cited_start = int(cited_match.group(1))
        cited_end = int(cited_match.group(2)) if cited_match.group(2) else cited_start

        if range_start <= cited_start <= range_end and range_start <= cited_end <= range_end:
            return True, f"Page {cited_page} within {work_pages}"
        else:
            return False, f"Page {cited_page} outside range {work_pages}"

    async def close(self) -> None:
        """Clean up HTTP clients."""
        await asyncio.gather(
            self.crossref.close(),
            self.openalex.close(),
        )
