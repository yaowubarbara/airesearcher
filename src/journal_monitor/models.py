"""Data models for the journal monitor module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.knowledge_base.models import Paper


@dataclass
class ScanResult:
    """Summary of a single journal monitoring scan."""

    journal_name: str
    scan_time: datetime
    papers_found: int = 0
    papers_new: int = 0
    papers_duplicate: int = 0
    sources_queried: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    papers: list[Paper] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def __str__(self) -> str:
        status = "OK" if self.success else f"ERRORS({len(self.errors)})"
        return (
            f"[{status}] {self.journal_name}: "
            f"{self.papers_new} new / {self.papers_found} found "
            f"(sources: {', '.join(self.sources_queried)})"
        )


@dataclass
class MonitorRunSummary:
    """Summary of a full monitoring run across all journals."""

    started_at: datetime
    finished_at: datetime | None = None
    journal_results: list[ScanResult] = field(default_factory=list)

    @property
    def total_new(self) -> int:
        return sum(r.papers_new for r in self.journal_results)

    @property
    def total_found(self) -> int:
        return sum(r.papers_found for r in self.journal_results)

    @property
    def journals_scanned(self) -> int:
        return len(self.journal_results)

    @property
    def journals_with_errors(self) -> int:
        return sum(1 for r in self.journal_results if not r.success)

    def __str__(self) -> str:
        duration = ""
        if self.finished_at:
            elapsed = (self.finished_at - self.started_at).total_seconds()
            duration = f" in {elapsed:.1f}s"
        return (
            f"Monitor run{duration}: "
            f"{self.journals_scanned} journals, "
            f"{self.total_new} new papers / {self.total_found} total found, "
            f"{self.journals_with_errors} errors"
        )
