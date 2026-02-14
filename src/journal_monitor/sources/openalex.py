"""Fetch recent papers from the OpenAlex API."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.knowledge_base.models import Language, Paper, PaperStatus
from src.utils.api_clients import OpenAlexClient

logger = logging.getLogger(__name__)


def _extract_authors(authorships: list[dict[str, Any]]) -> list[str]:
    """Extract author display names from OpenAlex authorships."""
    names: list[str] = []
    for authorship in authorships:
        author = authorship.get("author", {})
        name = author.get("display_name")
        if name:
            names.append(name)
    return names


def _extract_doi(work: dict[str, Any]) -> Optional[str]:
    """Extract clean DOI string from an OpenAlex work."""
    doi_url = work.get("doi")
    if doi_url and isinstance(doi_url, str):
        # OpenAlex returns DOIs as full URLs: "https://doi.org/10.xxx/yyy"
        return doi_url.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return None


def _extract_openalex_id(work: dict[str, Any]) -> Optional[str]:
    """Extract the short OpenAlex ID from the full URL."""
    oa_id = work.get("id", "")
    if isinstance(oa_id, str) and "/" in oa_id:
        return oa_id.rsplit("/", 1)[-1]
    return oa_id or None


def _detect_language(work: dict[str, Any]) -> Language:
    """Detect paper language from OpenAlex metadata."""
    lang = work.get("language")
    if lang == "zh":
        return Language.ZH
    if lang == "fr":
        return Language.FR
    return Language.EN


def _extract_journal_name(work: dict[str, Any], fallback: str) -> str:
    """Get the journal/source name from an OpenAlex work."""
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    return source.get("display_name") or fallback


def _extract_volume_issue(work: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Extract volume and issue from biblio fields."""
    biblio = work.get("biblio") or {}
    return biblio.get("volume"), biblio.get("issue")


def _extract_pages(work: dict[str, Any]) -> Optional[str]:
    """Extract page range from biblio fields."""
    biblio = work.get("biblio") or {}
    first_page = biblio.get("first_page")
    last_page = biblio.get("last_page")
    if first_page and last_page and first_page != last_page:
        return f"{first_page}-{last_page}"
    return first_page


def _extract_keywords(work: dict[str, Any]) -> list[str]:
    """Extract keyword strings from OpenAlex concepts/keywords."""
    keywords: list[str] = []
    for kw in work.get("keywords") or []:
        if isinstance(kw, dict):
            keyword = kw.get("display_name") or kw.get("keyword")
            if keyword:
                keywords.append(keyword)
        elif isinstance(kw, str):
            keywords.append(kw)
    return keywords


def _extract_pdf_url(work: dict[str, Any]) -> Optional[str]:
    """Extract OA PDF URL from OpenAlex work."""
    oa = work.get("open_access") or {}
    oa_url = oa.get("oa_url")
    if oa_url and isinstance(oa_url, str) and oa_url.endswith(".pdf"):
        return oa_url
    location = work.get("primary_location") or {}
    pdf_url = location.get("pdf_url")
    if pdf_url:
        return pdf_url
    # Fall back to oa_url even if not .pdf
    return oa_url


def _openalex_work_to_paper(work: dict[str, Any], journal_name: str) -> Paper:
    """Convert an OpenAlex work dict to a Paper model."""
    volume, issue = _extract_volume_issue(work)

    return Paper(
        title=work.get("display_name") or work.get("title") or "Untitled",
        authors=_extract_authors(work.get("authorships") or []),
        abstract=work.get("abstract") or _reconstruct_abstract(work),
        journal=_extract_journal_name(work, journal_name),
        year=work.get("publication_year") or 0,
        volume=volume,
        issue=issue,
        pages=_extract_pages(work),
        doi=_extract_doi(work),
        openalex_id=_extract_openalex_id(work),
        language=_detect_language(work),
        keywords=_extract_keywords(work),
        status=PaperStatus.DISCOVERED,
        url=work.get("primary_location", {}).get("landing_page_url"),
        pdf_url=_extract_pdf_url(work),
    )


def _reconstruct_abstract(work: dict[str, Any]) -> Optional[str]:
    """Reconstruct abstract text from OpenAlex inverted index if available."""
    inverted = work.get("abstract_inverted_index")
    if not inverted or not isinstance(inverted, dict):
        return None
    try:
        # Build word-position pairs, then sort by position
        word_positions: list[tuple[int, str]] = []
        for word, positions in inverted.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in word_positions)
    except Exception:
        return None


async def fetch_recent_papers(
    journal_config: dict[str, Any],
    since_date: str,
    client: OpenAlexClient | None = None,
) -> list[Paper]:
    """Fetch recent papers for a journal from OpenAlex.

    Args:
        journal_config: Journal configuration dict from journals.yaml.
        since_date: ISO date string (YYYY-MM-DD) for the earliest publication date.
        client: Optional pre-configured client instance.

    Returns:
        List of Paper objects discovered from OpenAlex.
    """
    source_id = journal_config.get("openalex_source_id")
    if not source_id:
        logger.debug(
            "No openalex_source_id for %s, skipping OpenAlex",
            journal_config.get("name", "unknown"),
        )
        return []

    own_client = client is None
    if own_client:
        client = OpenAlexClient()

    try:
        papers: list[Paper] = []
        page = 1
        max_pages = 5  # Safety cap to avoid runaway pagination

        while page <= max_pages:
            data = await client.search_works(
                source_id=source_id,
                from_date=since_date,
                per_page=50,
                page=page,
            )

            results = data.get("results") or []
            if not results:
                break

            logger.info(
                "OpenAlex page %d returned %d works for source=%s",
                page,
                len(results),
                source_id,
            )

            for work in results:
                try:
                    paper = _openalex_work_to_paper(
                        work, journal_config.get("name", "Unknown")
                    )
                    papers.append(paper)
                except Exception:
                    logger.warning(
                        "Failed to parse OpenAlex work: %s",
                        work.get("display_name", "?"),
                        exc_info=True,
                    )

            # Check if there are more pages
            meta = data.get("meta", {})
            total_count = meta.get("count", 0)
            if page * 50 >= total_count:
                break
            page += 1

        return papers

    finally:
        if own_client and client is not None:
            await client.close()
