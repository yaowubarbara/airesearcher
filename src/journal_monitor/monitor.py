"""Main journal monitor that orchestrates all sources and stores results."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml

from src.knowledge_base.db import Database
from src.knowledge_base.models import Paper
from src.utils.api_clients import CrossRefClient, OpenAlexClient, SemanticScholarClient

from .models import MonitorRunSummary, ScanResult
from .sources import cnki, crossref, openalex, rss, semantic_scholar

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/journals.yaml")


def _load_journal_configs(config_path: Path = DEFAULT_CONFIG_PATH) -> tuple[list[dict], dict]:
    """Load journal configurations and schedule settings from YAML.

    Returns:
        Tuple of (journal_list, schedule_config).
    """
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    journals = data.get("journals", [])
    schedule = data.get("schedule", {})
    return journals, schedule


def _compute_since_date(schedule: dict[str, Any]) -> str:
    """Compute the since_date string based on schedule lookback_days."""
    lookback_days = schedule.get("lookback_days", 30)
    since = datetime.utcnow() - timedelta(days=lookback_days)
    return since.strftime("%Y-%m-%d")


def _applicable_sources(journal_config: dict[str, Any]) -> list[str]:
    """Determine which sources are applicable for a journal based on its config."""
    sources: list[str] = []

    if journal_config.get("openalex_source_id"):
        sources.append("openalex")
    if journal_config.get("semantic_scholar_venue"):
        sources.append("semantic_scholar")
    if journal_config.get("issn"):
        sources.append("crossref")
    if journal_config.get("cnki_journal_code"):
        sources.append("cnki")
    if journal_config.get("rss_url"):
        sources.append("rss")

    return sources


def _deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    """Deduplicate papers by DOI, keeping the first (richest) occurrence.

    Papers without a DOI are always kept since we cannot determine duplicates.
    """
    seen_dois: set[str] = set()
    unique: list[Paper] = []

    for paper in papers:
        if paper.doi:
            doi_lower = paper.doi.lower().strip()
            if doi_lower in seen_dois:
                continue
            seen_dois.add(doi_lower)
        unique.append(paper)

    return unique


def _merge_paper_metadata(existing: Paper, new: Paper) -> Paper:
    """Merge metadata from a new paper into an existing one, filling gaps."""
    updates: dict[str, Any] = {}

    if not existing.abstract and new.abstract:
        updates["abstract"] = new.abstract
    if not existing.semantic_scholar_id and new.semantic_scholar_id:
        updates["semantic_scholar_id"] = new.semantic_scholar_id
    if not existing.openalex_id and new.openalex_id:
        updates["openalex_id"] = new.openalex_id
    if not existing.url and new.url:
        updates["url"] = new.url
    if not existing.keywords and new.keywords:
        updates["keywords"] = new.keywords
    if not existing.volume and new.volume:
        updates["volume"] = new.volume
    if not existing.issue and new.issue:
        updates["issue"] = new.issue
    if not existing.pages and new.pages:
        updates["pages"] = new.pages

    if updates:
        return existing.model_copy(update=updates)
    return existing


async def _fetch_from_source(
    source_name: str,
    journal_config: dict[str, Any],
    since_date: str,
    clients: dict[str, Any],
) -> list[Paper]:
    """Fetch papers from a single source, handling errors gracefully."""
    try:
        if source_name == "openalex":
            return await openalex.fetch_recent_papers(
                journal_config, since_date, client=clients.get("openalex")
            )
        elif source_name == "semantic_scholar":
            return await semantic_scholar.fetch_recent_papers(
                journal_config, since_date, client=clients.get("semantic_scholar")
            )
        elif source_name == "crossref":
            return await crossref.fetch_recent_papers(
                journal_config, since_date, client=clients.get("crossref")
            )
        elif source_name == "cnki":
            return await cnki.fetch_recent_papers(journal_config, since_date)
        elif source_name == "rss":
            return await rss.fetch_recent_papers(journal_config, since_date)
        else:
            logger.warning("Unknown source: %s", source_name)
            return []
    except Exception as exc:
        logger.error(
            "Error fetching from %s for %s: %s",
            source_name,
            journal_config.get("name", "unknown"),
            exc,
            exc_info=True,
        )
        raise


async def scan_journal(
    journal_config: dict[str, Any],
    since_date: str,
    db: Database,
    clients: dict[str, Any],
) -> ScanResult:
    """Scan a single journal across all applicable sources.

    Args:
        journal_config: Journal configuration from journals.yaml.
        since_date: ISO date string for earliest papers to fetch.
        db: Database instance for checking/storing papers.
        clients: Dict of shared API client instances.

    Returns:
        ScanResult summarizing what was found.
    """
    journal_name = journal_config.get("name", "Unknown")
    result = ScanResult(
        journal_name=journal_name,
        scan_time=datetime.utcnow(),
    )

    sources = _applicable_sources(journal_config)
    if not sources:
        logger.warning("No applicable sources for journal: %s", journal_name)
        result.errors.append("No applicable sources configured")
        return result

    # Fetch from all applicable sources concurrently
    all_papers: list[Paper] = []
    tasks = {}
    for source_name in sources:
        tasks[source_name] = _fetch_from_source(
            source_name, journal_config, since_date, clients
        )

    source_results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for source_name, source_result in zip(tasks.keys(), source_results):
        if isinstance(source_result, Exception):
            error_msg = f"{source_name}: {source_result}"
            result.errors.append(error_msg)
            logger.error("Source %s failed for %s: %s", source_name, journal_name, source_result)
        else:
            result.sources_queried.append(source_name)
            all_papers.extend(source_result)

    # Deduplicate by DOI
    unique_papers = _deduplicate_papers(all_papers)
    result.papers_found = len(unique_papers)
    result.papers_duplicate = len(all_papers) - len(unique_papers)

    # Store new papers in the database
    new_count = 0
    for paper in unique_papers:
        if paper.doi:
            existing = db.get_paper_by_doi(paper.doi)
            if existing:
                # Merge any new metadata into the existing record
                merged = _merge_paper_metadata(existing, paper)
                if merged is not existing:
                    # Update in DB if metadata was enriched
                    # (The db module uses INSERT OR IGNORE, so we handle this manually)
                    pass
                continue

        db.insert_paper(paper)
        result.papers.append(paper)
        new_count += 1

    result.papers_new = new_count

    logger.info(
        "Journal %s: %d found, %d new, %d duplicate, sources=%s",
        journal_name,
        result.papers_found,
        result.papers_new,
        result.papers_duplicate,
        result.sources_queried,
    )

    return result


async def run_monitor(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db: Optional[Database] = None,
    since_date: Optional[str] = None,
) -> MonitorRunSummary:
    """Run the full journal monitoring pipeline.

    Loads journal configs, queries all applicable sources for each journal,
    deduplicates results by DOI, and stores new papers in the database.

    Args:
        config_path: Path to the journals.yaml configuration file.
        db: Optional Database instance (created if not provided).
        since_date: Optional override for the since_date (defaults to schedule config).

    Returns:
        MonitorRunSummary with per-journal results and overall statistics.
    """
    summary = MonitorRunSummary(started_at=datetime.utcnow())

    # Load configuration
    journals, schedule = _load_journal_configs(config_path)
    if not journals:
        logger.warning("No journals configured in %s", config_path)
        summary.finished_at = datetime.utcnow()
        return summary

    if since_date is None:
        since_date = _compute_since_date(schedule)

    logger.info(
        "Starting journal monitor: %d journals, since_date=%s",
        len(journals),
        since_date,
    )

    # Initialize database
    own_db = db is None
    if own_db:
        db = Database()
        db.initialize()

    # Create shared API clients (reused across journals to respect rate limits)
    clients: dict[str, Any] = {}
    s2_client = SemanticScholarClient()
    oa_client = OpenAlexClient()
    cr_client = CrossRefClient()
    clients["semantic_scholar"] = s2_client
    clients["openalex"] = oa_client
    clients["crossref"] = cr_client

    try:
        # Process journals sequentially to be polite to APIs
        # (each journal already fetches from multiple sources concurrently)
        for journal_config in journals:
            try:
                result = await scan_journal(journal_config, since_date, db, clients)
                summary.journal_results.append(result)
            except Exception as exc:
                logger.error(
                    "Unexpected error scanning %s: %s",
                    journal_config.get("name", "unknown"),
                    exc,
                    exc_info=True,
                )
                error_result = ScanResult(
                    journal_name=journal_config.get("name", "Unknown"),
                    scan_time=datetime.utcnow(),
                    errors=[f"Unexpected error: {exc}"],
                )
                summary.journal_results.append(error_result)

    finally:
        # Clean up shared clients
        await s2_client.close()
        await oa_client.close()
        await cr_client.close()

        if own_db and db is not None:
            db.close()

    summary.finished_at = datetime.utcnow()

    logger.info("Monitor run complete: %s", summary)

    return summary
