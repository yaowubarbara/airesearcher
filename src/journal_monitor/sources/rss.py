"""Fetch recent papers from journal RSS feeds using feedparser."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src.knowledge_base.models import Language, Paper, PaperStatus

logger = logging.getLogger(__name__)


def _parse_pub_date(entry: dict[str, Any]) -> Optional[datetime]:
    """Parse publication date from an RSS entry."""
    # feedparser normalizes dates into published_parsed (time.struct_time)
    parsed = entry.get("published_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6])
        except (TypeError, ValueError):
            pass

    # Fallback: try updated_parsed
    parsed = entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6])
        except (TypeError, ValueError):
            pass

    return None


def _extract_authors(entry: dict[str, Any]) -> list[str]:
    """Extract author names from an RSS entry."""
    # feedparser may provide 'authors' list or single 'author' string
    authors_list = entry.get("authors") or []
    if authors_list:
        return [a.get("name", str(a)) for a in authors_list if a]

    author = entry.get("author")
    if author and isinstance(author, str):
        # Split on common delimiters
        if ";" in author:
            return [a.strip() for a in author.split(";") if a.strip()]
        if " and " in author:
            return [a.strip() for a in author.split(" and ") if a.strip()]
        return [author.strip()]

    return []


def _extract_doi(entry: dict[str, Any]) -> Optional[str]:
    """Try to extract a DOI from the RSS entry link or id."""
    # Check prism:doi or dc:identifier tags (feedparser puts these in the entry)
    doi = entry.get("prism_doi") or entry.get("doi")
    if doi:
        return doi

    # Try to extract from the link URL
    link = entry.get("link", "")
    if "doi.org/" in link:
        return link.split("doi.org/", 1)[1]

    # Some feeds put DOI in the id field
    entry_id = entry.get("id", "")
    if "doi.org/" in entry_id:
        return entry_id.split("doi.org/", 1)[1]

    return None


def _extract_abstract(entry: dict[str, Any]) -> Optional[str]:
    """Extract abstract/summary from RSS entry."""
    summary = entry.get("summary")
    if summary and isinstance(summary, str):
        # Strip HTML tags if present
        import re
        clean = re.sub(r"<[^>]+>", "", summary).strip()
        if clean and len(clean) > 20:
            return clean
    return None


def _detect_language(journal_config: dict[str, Any]) -> Language:
    """Detect language from journal config."""
    lang = journal_config.get("language", "en")
    if lang == "zh":
        return Language.ZH
    if lang == "fr":
        return Language.FR
    return Language.EN


def _entry_to_paper(
    entry: dict[str, Any],
    journal_name: str,
    language: Language,
) -> Paper:
    """Convert a feedparser entry to a Paper model."""
    pub_date = _parse_pub_date(entry)
    year = pub_date.year if pub_date else datetime.utcnow().year

    return Paper(
        title=entry.get("title", "Untitled").strip(),
        authors=_extract_authors(entry),
        abstract=_extract_abstract(entry),
        journal=journal_name,
        year=year,
        doi=_extract_doi(entry),
        language=language,
        status=PaperStatus.DISCOVERED,
        url=entry.get("link"),
    )


async def fetch_recent_papers(
    journal_config: dict[str, Any],
    since_date: str,
) -> list[Paper]:
    """Fetch recent papers from a journal's RSS feed.

    Args:
        journal_config: Journal configuration dict from journals.yaml.
            Expected key: rss_url.
        since_date: ISO date string (YYYY-MM-DD) for the earliest publication date.

    Returns:
        List of Paper objects parsed from the RSS feed.
    """
    rss_url = journal_config.get("rss_url")
    if not rss_url:
        logger.debug(
            "No rss_url for %s, skipping RSS",
            journal_config.get("name", "unknown"),
        )
        return []

    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed. Run: pip install feedparser")
        return []

    journal_name = journal_config.get("name", "Unknown")
    language = _detect_language(journal_config)
    since_dt = datetime.fromisoformat(since_date)

    logger.info("Fetching RSS feed for %s: %s", journal_name, rss_url)

    # feedparser is synchronous; run it in the default executor to avoid blocking
    import asyncio
    loop = asyncio.get_event_loop()
    feed = await loop.run_in_executor(None, feedparser.parse, rss_url)

    if feed.bozo and not feed.entries:
        logger.warning(
            "RSS feed error for %s: %s", journal_name, feed.get("bozo_exception", "unknown")
        )
        return []

    logger.info(
        "RSS feed for %s returned %d entries", journal_name, len(feed.entries)
    )

    papers: list[Paper] = []
    for entry in feed.entries:
        try:
            pub_date = _parse_pub_date(entry)
            # Filter by date if we can determine the publication date
            if pub_date and pub_date < since_dt:
                continue

            paper = _entry_to_paper(entry, journal_name, language)
            papers.append(paper)
        except Exception:
            logger.warning(
                "Failed to parse RSS entry: %s",
                entry.get("title", "?"),
                exc_info=True,
            )

    return papers
