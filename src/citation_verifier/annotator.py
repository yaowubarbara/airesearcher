"""Annotate manuscript text with [VERIFY] tags for unverifiable citations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.citation_verifier.engine import CitationVerification


# Tag suffixes for each verification status
_TAGS = {
    "work_not_found": "[VERIFY:work]",
    "page_out_of_range": "[VERIFY:page-range]",
    # page_unverifiable is intentionally omitted — book page numbers
    # can't be checked without PDFs and are too common to flag.
}


def annotate_manuscript(
    text: str,
    verifications: list[CitationVerification],
) -> str:
    """Insert [VERIFY] tags after unverifiable citations.

    Processes citations from end-to-start to preserve character positions.
    Verified citations are left unchanged.
    """
    # Sort by end position descending so insertions don't shift earlier positions
    sorted_verifs = sorted(verifications, key=lambda v: v.citation.end_pos, reverse=True)

    result = text
    for v in sorted_verifs:
        tag = _TAGS.get(v.status)
        if tag:
            pos = v.citation.end_pos
            result = result[:pos] + " " + tag + result[pos:]

    return result


@dataclass
class VerificationReport:
    """Summary report of citation verification results."""

    total: int = 0
    verified: int = 0
    work_not_found: int = 0
    page_unverifiable: int = 0
    page_out_of_range: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_verifications(
        cls, verifications: list[CitationVerification]
    ) -> VerificationReport:
        report = cls(total=len(verifications))
        for v in verifications:
            if v.status == "verified":
                report.verified += 1
            elif v.status == "work_not_found":
                report.work_not_found += 1
            elif v.status == "page_unverifiable":
                report.page_unverifiable += 1
            elif v.status == "page_out_of_range":
                report.page_out_of_range += 1

            detail: dict[str, Any] = {
                "raw": v.citation.raw,
                "author": v.citation.author,
                "title": v.citation.title,
                "pages": v.citation.pages,
                "status": v.status,
                "confidence": v.confidence,
                "notes": v.notes,
            }
            if v.matched_work:
                detail["matched_title"] = v.matched_work.get("title", "")
                detail["matched_doi"] = v.matched_work.get("doi", "")
                detail["matched_pages"] = v.matched_work.get("pages", "")
            report.details.append(detail)

        return report

    def summary(self) -> str:
        """Human-readable one-line summary."""
        if self.total == 0:
            return "No citations found to verify."
        pct = self.verified / self.total * 100
        return (
            f"Verified {self.verified}/{self.total} citations ({pct:.0f}%). "
            f"Not found: {self.work_not_found}. "
            f"Page unverifiable: {self.page_unverifiable}. "
            f"Page out of range: {self.page_out_of_range}."
        )

    def to_markdown(self) -> str:
        """Full Markdown report."""
        lines = [
            "# Citation Verification Report",
            "",
            f"**Total citations**: {self.total}",
            f"**Verified**: {self.verified}",
            f"**Work not found**: {self.work_not_found}",
            f"**Page unverifiable**: {self.page_unverifiable}",
            f"**Page out of range**: {self.page_out_of_range}",
            "",
        ]

        if self.verified == self.total:
            lines.append("All citations verified successfully.")
            return "\n".join(lines)

        # Issues table
        issues = [d for d in self.details if d["status"] != "verified"]
        if issues:
            lines.append("## Issues")
            lines.append("")
            lines.append("| Citation | Status | Notes |")
            lines.append("|----------|--------|-------|")
            for d in issues:
                raw = d["raw"].replace("|", "\\|")
                status = d["status"].replace("_", " ")
                notes = d.get("notes", "").replace("|", "\\|")
                lines.append(f"| `{raw}` | {status} | {notes} |")
            lines.append("")

        # Verified table
        verified = [d for d in self.details if d["status"] == "verified"]
        if verified:
            lines.append("## Verified")
            lines.append("")
            lines.append("| Citation | Matched Work | DOI |")
            lines.append("|----------|-------------|-----|")
            for d in verified:
                raw = d["raw"].replace("|", "\\|")
                matched = d.get("matched_title", "").replace("|", "\\|")
                doi = d.get("matched_doi", "") or ""
                lines.append(f"| `{raw}` | {matched} | {doi} |")

        return "\n".join(lines)
