"""Fetch recent papers from the CrossRef API."""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.knowledge_base.models import Language, Paper, PaperStatus
from src.utils.api_clients import CrossRefClient

logger = logging.getLogger(__name__)


def _extract_authors(author_list: list[dict[str, Any]]) -> list[str]:
    """Format author names from CrossRef author objects."""
    names: list[str] = []
    for author in author_list:
        given = author.get("given", "")
        family = author.get("family", "")
        if given and family:
            names.append(f"{given} {family}")
        elif family:
            names.append(family)
        elif given:
            names.append(given)
    return names


def _extract_year(item: dict[str, Any]) -> int:
    """Extract publication year from CrossRef date fields."""
    # Try published-print first, then published-online, then issued
    for date_field in ("published-print", "published-online", "issued", "created"):
        date_obj = item.get(date_field)
        if date_obj and "date-parts" in date_obj:
            parts = date_obj["date-parts"]
            if parts and parts[0] and parts[0][0]:
                return int(parts[0][0])
    return 0


def _extract_pub_date(item: dict[str, Any]) -> Optional[str]:
    """Extract publication date as YYYY-MM-DD string for filtering."""
    for date_field in ("published-print", "published-online", "issued", "created"):
        date_obj = item.get(date_field)
        if date_obj and "date-parts" in date_obj:
            parts = date_obj["date-parts"]
            if parts and parts[0]:
                date_parts = parts[0]
                year = date_parts[0] if len(date_parts) > 0 else None
                month = date_parts[1] if len(date_parts) > 1 else 1
                day = date_parts[2] if len(date_parts) > 2 else 1
                if year:
                    return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _extract_abstract(item: dict[str, Any]) -> Optional[str]:
    """Extract and clean abstract text from CrossRef."""
    abstract = item.get("abstract")
    if not abstract:
        return None
    # CrossRef abstracts sometimes contain JATS XML tags
    import re
    clean = re.sub(r"<[^>]+>", "", abstract)
    return clean.strip() or None


def _extract_pages(item: dict[str, Any]) -> Optional[str]:
    """Extract page range from CrossRef item."""
    return item.get("page")


def _extract_volume_issue(item: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Extract volume and issue number."""
    return item.get("volume"), item.get("issue")


def _detect_language(item: dict[str, Any]) -> Language:
    """Detect paper language from CrossRef metadata."""
    lang = item.get("language")
    if lang and lang.startswith("zh"):
        return Language.ZH
    if lang and lang.startswith("fr"):
        return Language.FR
    return Language.EN


def _extract_journal_name(item: dict[str, Any], fallback: str) -> str:
    """Get the journal title from CrossRef item."""
    container = item.get("container-title")
    if container and isinstance(container, list) and container[0]:
        return container[0]
    return fallback


def _extract_pdf_url(item: dict[str, Any]) -> Optional[str]:
    """Extract PDF URL from CrossRef link array."""
    links = item.get("link") or []
    for link in links:
        content_type = link.get("content-type", "")
        if "pdf" in content_type.lower():
            return link.get("URL")
    return None


def _crossref_item_to_paper(item: dict[str, Any], journal_name: str) -> Paper:
    """Convert a CrossRef work item to a Paper model."""
    title_list = item.get("title") or []
    title = title_list[0] if title_list else "Untitled"
    volume, issue = _extract_volume_issue(item)

    doi = item.get("DOI")
    url = item.get("URL")
    if not url and doi:
        url = f"https://doi.org/{doi}"

    return Paper(
        title=title,
        authors=_extract_authors(item.get("author") or []),
        abstract=_extract_abstract(item),
        journal=_extract_journal_name(item, journal_name),
        year=_extract_year(item),
        volume=volume,
        issue=issue,
        pages=_extract_pages(item),
        doi=doi,
        language=_detect_language(item),
        status=PaperStatus.DISCOVERED,
        url=url,
        pdf_url=_extract_pdf_url(item),
    )


async def fetch_recent_papers(
    journal_config: dict[str, Any],
    since_date: str,
    client: CrossRefClient | None = None,
) -> list[Paper]:
    """Fetch recent papers for a journal from CrossRef.

    Args:
        journal_config: Journal configuration dict from journals.yaml.
        since_date: ISO date string (YYYY-MM-DD) for the earliest publication date.
        client: Optional pre-configured client instance.

    Returns:
        List of Paper objects discovered from CrossRef.
    """
    issn = journal_config.get("issn")
    if not issn:
        logger.debug(
            "No ISSN for %s, skipping CrossRef",
            journal_config.get("name", "unknown"),
        )
        return []

    own_client = client is None
    if own_client:
        client = CrossRefClient()

    try:
        data = await client.search_works(
            issn=issn,
            from_date=since_date,
            rows=50,
        )

        message = data.get("message", {})
        items = message.get("items") or []

        logger.info(
            "CrossRef returned %d items for ISSN=%s since %s",
            len(items),
            issn,
            since_date,
        )

        papers: list[Paper] = []
        for item in items:
            try:
                paper = _crossref_item_to_paper(
                    item, journal_config.get("name", "Unknown")
                )
                # Additional date filter: CrossRef filter is approximate
                pub_date = _extract_pub_date(item)
                if pub_date and pub_date < since_date:
                    continue
                papers.append(paper)
            except Exception:
                title_list = item.get("title") or ["?"]
                logger.warning(
                    "Failed to parse CrossRef item: %s",
                    title_list[0] if title_list else "?",
                    exc_info=True,
                )

        return papers

    finally:
        if own_client and client is not None:
            await client.close()
