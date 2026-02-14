"""APScheduler-based periodic job scheduler for the AI Research Agent.

Runs journal monitoring on a configurable interval (default: weekly).
Can be started as a standalone daemon or integrated into the CLI.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.knowledge_base.db import Database
from src.journal_monitor.monitor import run_monitor

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/journals.yaml")


def _load_schedule_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load the schedule section from journals.yaml."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("schedule", {})


def _run_monitor_job(config_path: Path, db_path: Optional[str] = None) -> None:
    """Synchronous wrapper that runs the async monitor in a new event loop."""
    logger.info("Scheduled monitor job starting...")
    db = Database(db_path) if db_path else Database()
    db.initialize()
    try:
        summary = asyncio.run(run_monitor(config_path=config_path, db=db))
        total_new = sum(r.papers_new for r in summary.journal_results)
        total_found = sum(r.papers_found for r in summary.journal_results)
        errors = sum(len(r.errors) for r in summary.journal_results)
        logger.info(
            "Monitor job complete: %d journals scanned, %d papers found, %d new, %d errors",
            len(summary.journal_results),
            total_found,
            total_new,
            errors,
        )
    except Exception:
        logger.exception("Monitor job failed")
    finally:
        db.close()


def create_scheduler(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Optional[str] = None,
    run_immediately: bool = True,
) -> BackgroundScheduler:
    """Create and configure an APScheduler BackgroundScheduler.

    Args:
        config_path: Path to journals.yaml for schedule config and journal list.
        db_path: Optional custom database path.
        run_immediately: If True, run the monitor once before starting the schedule.

    Returns:
        Configured (but not started) BackgroundScheduler.
    """
    schedule_config = _load_schedule_config(config_path)
    interval_hours = schedule_config.get("scan_interval_hours", 168)  # default weekly

    scheduler = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1}
    )

    scheduler.add_job(
        _run_monitor_job,
        trigger=IntervalTrigger(hours=interval_hours),
        args=[config_path, db_path],
        id="journal_monitor",
        name="Periodic Journal Monitor",
        replace_existing=True,
    )

    if run_immediately:
        scheduler.add_job(
            _run_monitor_job,
            args=[config_path, db_path],
            id="journal_monitor_initial",
            name="Initial Journal Monitor Run",
        )

    logger.info("Scheduler configured: monitor every %d hours", interval_hours)
    return scheduler


def run_scheduler_blocking(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Optional[str] = None,
) -> None:
    """Start the scheduler and block until interrupted (Ctrl+C / SIGTERM).

    Suitable for running as a daemon or background process.
    """
    scheduler = create_scheduler(config_path=config_path, db_path=db_path)
    scheduler.start()

    stop_event = asyncio.Event()

    def _handle_signal(sig, frame):
        logger.info("Received signal %s, shutting down scheduler...", sig)
        scheduler.shutdown(wait=False)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        # Block main thread
        while not stop_event.is_set():
            signal.pause()
    except (KeyboardInterrupt, AttributeError):
        # AttributeError: signal.pause not available on Windows
        pass
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
