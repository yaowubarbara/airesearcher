"""Fetch recent papers from the Semantic Scholar API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from src.knowledge_base.models import Language, Paper, PaperStatus
from src.utils.api_clients import SemanticScholarClient

logger = logging.getLogger(__name__)


def _parse_authors(author_list: list[dict[str, Any]]) -> list[str]:
    """Extract author names from S2 author objects."""
    names: list[str] = []
    for author in author_list:
        name = author.get("name")
        if name:
            names.append(name)
    return names


def _parse_doi(external_ids: dict[str, Any] | None) -> Optional[str]:
    """Extract DOI from S2 externalIds dict."""
    if not external_ids:
        return None
    return external_ids.get("DOI")


def _parse_s2_id(external_ids: dict[str, Any] | None) -> Optional[str]:
    """Extract the Semantic Scholar corpus ID."""
    if not external_ids:
        return None
    corpus_id = external_ids.get("CorpusId")
    return str(corpus_id) if corpus_id is not None else None


def _parse_year(paper: dict[str, Any]) -> int:
    """Extract year from paper data, falling back to current year."""
    year = paper.get("year")
    if year:
        return int(year)
    pub_date = paper.get("publicationDate")
    if pub_date:
        try:
            return datetime.fromisoformat(pub_date).year
        except (ValueError, TypeError):
            pass
    return datetime.utcnow().year


def _s2_paper_to_paper(raw: dict[str, Any], journal_name: str) -> Paper:
    """Convert a Semantic Scholar paper dict to a Paper model."""
    authors = _parse_authors(raw.get("authors") or [])
    external_ids = raw.get("externalIds") or {}
    doi = _parse_doi(external_ids)
    s2_id = _parse_s2_id(external_ids)

    venue = raw.get("venue") or journal_name

    # Extract open access PDF URL if available
    oa_pdf = raw.get("openAccessPdf") or {}
    pdf_url = oa_pdf.get("url") if isinstance(oa_pdf, dict) else None

    # Build external_ids dict from S2 externalIds
    ext_ids: dict[str, str] = {}
    for key in ("ArXiv", "PMID", "PMCID", "ACL", "DBLP", "MAG", "CorpusId"):
        val = external_ids.get(key)
        if val is not None:
            ext_ids[key] = str(val)

    return Paper(
        title=raw.get("title", "Untitled"),
        authors=authors,
        abstract=raw.get("abstract"),
        journal=venue,
        year=_parse_year(raw),
        doi=doi,
        semantic_scholar_id=s2_id,
        language=Language.EN,
        status=PaperStatus.DISCOVERED,
        url=f"https://www.semanticscholar.org/paper/{raw.get('paperId', '')}",
        pdf_url=pdf_url,
        external_ids=ext_ids,
    )


async def fetch_recent_papers(
    journal_config: dict[str, Any],
    since_date: str,
    client: SemanticScholarClient | None = None,
) -> list[Paper]:
    """Fetch recent papers for a journal from Semantic Scholar.

    Args:
        journal_config: Journal configuration dict from journals.yaml.
        since_date: ISO date string (YYYY-MM-DD) for the earliest publication date.
        client: Optional pre-configured client instance.

    Returns:
        List of Paper objects discovered from Semantic Scholar.
    """
    venue = journal_config.get("semantic_scholar_venue")
    if not venue:
        logger.debug(
            "No semantic_scholar_venue for %s, skipping S2",
            journal_config.get("name", "unknown"),
        )
        return []

    own_client = client is None
    if own_client:
        client = SemanticScholarClient()

    try:
        # Determine year range from since_date
        since_year = since_date[:4]
        current_year = str(datetime.utcnow().year)
        year_range = f"{since_year}-{current_year}" if since_year != current_year else current_year

        # S2 search API does not support filtering by exact date, only by year.
        # We search broadly by venue + year and then filter client-side.
        data = await client.search_papers(
            query="*",
            venue=venue,
            year=year_range,
            limit=50,
        )

        raw_papers = data.get("data") or []
        logger.info(
            "Semantic Scholar returned %d papers for venue=%s year=%s",
            len(raw_papers),
            venue,
            year_range,
        )

        papers: list[Paper] = []
        for raw in raw_papers:
            try:
                paper = _s2_paper_to_paper(raw, journal_config.get("name", venue))
                # Client-side date filter: keep only papers on or after since_date
                pub_date = raw.get("publicationDate")
                if pub_date and pub_date < since_date:
                    continue
                papers.append(paper)
            except Exception:
                logger.warning("Failed to parse S2 paper: %s", raw.get("title", "?"), exc_info=True)

        return papers

    finally:
        if own_client and client is not None:
            await client.close()
