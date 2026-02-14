"""Citation format checker - validates citation formatting against style guides."""

from __future__ import annotations

import re
from typing import Optional

from src.knowledge_base.models import Reference


class FormatChecker:
    """Checks and formats references according to citation styles."""

    def format_reference(self, ref: Reference, style: str) -> str:
        """Format a reference according to the specified style."""
        formatters = {
            "MLA": self._format_mla,
            "Chicago": self._format_chicago,
            "GB/T 7714": self._format_gb,
            "French academic": self._format_french,
        }
        formatter = formatters.get(style, self._format_mla)
        return formatter(ref)

    def check_bibliography(
        self, bibliography: str, style: str
    ) -> list[dict[str, str]]:
        """Check a bibliography for format errors.

        Returns a list of issues found.
        """
        issues: list[dict[str, str]] = []
        entries = [e.strip() for e in bibliography.split("\n") if e.strip()]

        for i, entry in enumerate(entries):
            entry_issues = self._check_entry(entry, style, i + 1)
            issues.extend(entry_issues)

        # Check alphabetical ordering
        if style in ("MLA", "Chicago", "French academic"):
            for i in range(1, len(entries)):
                if entries[i].lower() < entries[i - 1].lower():
                    issues.append({
                        "line": i + 1,
                        "issue": "Entry may be out of alphabetical order",
                        "severity": "warning",
                    })

        return issues

    def _check_entry(
        self, entry: str, style: str, line_num: int
    ) -> list[dict[str, str]]:
        """Check a single bibliography entry."""
        issues = []

        if not entry.endswith("."):
            issues.append({
                "line": line_num,
                "issue": "Entry should end with a period",
                "severity": "error",
            })

        if style == "MLA":
            # Check for italicized titles (marked with * in plain text)
            if "*" not in entry and "_" not in entry:
                issues.append({
                    "line": line_num,
                    "issue": "MLA entries typically contain an italicized title",
                    "severity": "warning",
                })
        elif style == "Chicago":
            if not re.search(r"\d{4}", entry):
                issues.append({
                    "line": line_num,
                    "issue": "Chicago entries should include a publication year",
                    "severity": "error",
                })

        return issues

    def _format_mla(self, ref: Reference) -> str:
        """Format reference in MLA 9th edition style."""
        parts = []

        # Author(s)
        if ref.authors:
            if len(ref.authors) == 1:
                parts.append(f"{_last_first(ref.authors[0])}.")
            elif len(ref.authors) == 2:
                parts.append(
                    f"{_last_first(ref.authors[0])}, and {ref.authors[1]}."
                )
            else:
                parts.append(f"{_last_first(ref.authors[0])}, et al.")

        # Title
        if ref.journal:
            # Article in journal
            parts.append(f'"{ref.title}."')
            parts.append(f"*{ref.journal}*")
            vol_parts = []
            if ref.volume:
                vol_parts.append(ref.volume)
            if ref.issue:
                vol_parts.append(f".{ref.issue}")
            if vol_parts:
                parts.append("".join(vol_parts))
            if ref.year:
                parts.append(f"({ref.year}):")
            if ref.pages:
                parts.append(f"{ref.pages}.")
        else:
            # Book
            parts.append(f"*{ref.title}*.")
            if ref.publisher:
                parts.append(f"{ref.publisher},")
            parts.append(f"{ref.year}.")

        return " ".join(parts)

    def _format_chicago(self, ref: Reference) -> str:
        """Format reference in Chicago 17th edition style (notes-bibliography)."""
        parts = []

        # Author(s)
        if ref.authors:
            if len(ref.authors) == 1:
                parts.append(f"{_last_first(ref.authors[0])}.")
            elif len(ref.authors) <= 3:
                author_list = [_last_first(ref.authors[0])]
                author_list.extend(ref.authors[1:])
                parts.append(f"{', '.join(author_list[:-1])}, and {author_list[-1]}.")
            else:
                parts.append(f"{_last_first(ref.authors[0])}, et al.")

        # Title and publication info
        if ref.journal:
            parts.append(f'"{ref.title}."')
            parts.append(f"*{ref.journal}*")
            if ref.volume:
                parts.append(ref.volume)
            if ref.issue:
                parts.append(f", no. {ref.issue}")
            if ref.year:
                parts.append(f"({ref.year}):")
            if ref.pages:
                parts.append(f"{ref.pages}.")
        else:
            parts.append(f"*{ref.title}*.")
            if ref.publisher:
                parts.append(f"{ref.publisher},")
            parts.append(f"{ref.year}.")

        return " ".join(parts)

    def _format_gb(self, ref: Reference) -> str:
        """Format reference in GB/T 7714-2015 style (Chinese standard)."""
        parts = []

        # Authors (GB/T uses all authors, comma-separated)
        if ref.authors:
            author_str = ", ".join(ref.authors[:3])
            if len(ref.authors) > 3:
                author_str += ", 等"
            parts.append(f"{author_str}.")

        if ref.journal:
            # Journal article: [J]
            parts.append(f"{ref.title}[J].")
            parts.append(f"{ref.journal},")
            parts.append(f"{ref.year}")
            if ref.volume:
                parts.append(f",{ref.volume}")
            if ref.issue:
                parts.append(f"({ref.issue})")
            if ref.pages:
                parts.append(f":{ref.pages}")
            parts.append(".")
        else:
            # Book: [M]
            parts.append(f"{ref.title}[M].")
            if ref.publisher:
                parts.append(f"{ref.publisher},")
            parts.append(f"{ref.year}.")

        return " ".join(parts)

    def _format_french(self, ref: Reference) -> str:
        """Format reference in French academic style."""
        parts = []

        if ref.authors:
            if len(ref.authors) == 1:
                parts.append(f"{_last_first(ref.authors[0])},")
            else:
                author_list = [_last_first(ref.authors[0])]
                author_list.extend(ref.authors[1:])
                parts.append(f"{', '.join(author_list)},")

        if ref.journal:
            parts.append(f"\u00ab {ref.title} \u00bb,")
            parts.append(f"*{ref.journal}*,")
            if ref.volume:
                parts.append(f"vol. {ref.volume},")
            if ref.issue:
                parts.append(f"n\u00b0 {ref.issue},")
            parts.append(f"{ref.year},")
            if ref.pages:
                parts.append(f"p. {ref.pages}.")
            else:
                # Remove trailing comma and add period
                parts[-1] = parts[-1].rstrip(",") + "."
        else:
            parts.append(f"*{ref.title}*,")
            if ref.publisher:
                parts.append(f"{ref.publisher},")
            parts.append(f"{ref.year}.")

        return " ".join(parts)


def _last_first(name: str) -> str:
    """Convert 'First Last' to 'Last, First' format."""
    if "," in name:
        return name
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name
