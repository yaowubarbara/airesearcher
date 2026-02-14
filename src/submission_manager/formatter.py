"""Manuscript formatter - prepares submission-ready documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

from src.knowledge_base.db import Database
from src.knowledge_base.models import Language, Manuscript
from src.reference_verifier.format_checker import FormatChecker


class ManuscriptFormatter:
    """Formats manuscripts according to target journal specifications."""

    def __init__(self, db: Database):
        self.db = db
        self.format_checker = FormatChecker()

    def format_manuscript(
        self,
        manuscript: Manuscript,
        journal_profile: Optional[dict] = None,
    ) -> str:
        """Format a manuscript for submission.

        Applies journal-specific formatting:
        - Title page
        - Abstract
        - Section headings
        - Citation formatting
        - Bibliography/Works Cited
        - Footnotes/endnotes
        """
        profile = journal_profile or {}
        formatting = profile.get("formatting", {})
        citation_style = formatting.get("citation_style", "MLA")

        parts: list[str] = []

        # Title page
        parts.append(self._format_title_page(manuscript, formatting))
        parts.append("")

        # Abstract
        if formatting.get("abstract", {}).get("required", True):
            parts.append(self._format_abstract(manuscript, formatting))
            parts.append("")

        # Keywords
        if manuscript.keywords:
            keyword_str = ", ".join(manuscript.keywords)
            if manuscript.language == Language.ZH:
                parts.append(f"关键词：{keyword_str}")
            elif manuscript.language == Language.FR:
                parts.append(f"Mots-clés : {keyword_str}")
            else:
                parts.append(f"Keywords: {keyword_str}")
            parts.append("")

        # Main body
        for section_name, content in manuscript.sections.items():
            heading = self._format_heading(section_name, formatting)
            parts.append(heading)
            parts.append("")
            parts.append(content)
            parts.append("")

        # Or use full_text if sections not available
        if not manuscript.sections and manuscript.full_text:
            parts.append(manuscript.full_text)
            parts.append("")

        # Bibliography
        bibliography = self._generate_bibliography(
            manuscript.reference_ids, citation_style
        )
        bib_title = formatting.get("bibliography_title", "Works Cited")
        if manuscript.language == Language.ZH:
            bib_title = "参考文献"
        elif manuscript.language == Language.FR:
            bib_title = "Bibliographie"
        parts.append(f"\n{bib_title}\n")
        parts.append(bibliography)

        return "\n".join(parts)

    def _format_title_page(self, manuscript: Manuscript, formatting: dict) -> str:
        """Format the title page."""
        lines = []
        lines.append(manuscript.title)
        lines.append("")
        # Note: Author info is typically added by the author, not the agent
        lines.append("[Author Name]")
        lines.append("[Institutional Affiliation]")
        return "\n".join(lines)

    def _format_abstract(self, manuscript: Manuscript, formatting: dict) -> str:
        """Format the abstract according to journal requirements."""
        abstract_config = formatting.get("abstract", {})
        max_words = abstract_config.get("max_words", 200)

        label = "Abstract"
        if manuscript.language == Language.ZH:
            label = "摘要"
        elif manuscript.language == Language.FR:
            label = "Résumé"

        abstract = manuscript.abstract or ""

        # Truncate if needed
        words = abstract.split()
        if len(words) > max_words:
            abstract = " ".join(words[:max_words]) + "..."

        return f"{label}\n\n{abstract}"

    def _format_heading(self, title: str, formatting: dict) -> str:
        """Format a section heading."""
        heading_style = formatting.get("sections", {}).get("heading_style", "bold")

        if heading_style == "centered_bold":
            return f"**{title}**"
        elif heading_style == "numbered":
            return title  # Numbering handled elsewhere
        else:
            return f"**{title}**"

    def _generate_bibliography(
        self, reference_ids: list[str], style: str
    ) -> str:
        """Generate a formatted bibliography from reference IDs."""
        entries: list[str] = []

        for ref_id in reference_ids:
            # Try to find in references table
            row = self.db.conn.execute(
                "SELECT * FROM references_ WHERE id = ? OR paper_id = ?",
                (ref_id, ref_id),
            ).fetchone()

            if row:
                # Use pre-formatted version if available
                if style == "MLA" and row["formatted_mla"]:
                    entries.append(row["formatted_mla"])
                elif style == "Chicago" and row["formatted_chicago"]:
                    entries.append(row["formatted_chicago"])
                elif style == "GB/T 7714" and row["formatted_gb"]:
                    entries.append(row["formatted_gb"])
                else:
                    # Format from raw data
                    import json
                    from src.knowledge_base.models import Reference
                    ref = Reference(
                        id=row["id"],
                        title=row["title"],
                        authors=json.loads(row["authors"]),
                        year=row["year"],
                        journal=row["journal"],
                        volume=row["volume"],
                        pages=row["pages"],
                        doi=row["doi"],
                        publisher=row["publisher"],
                    )
                    entries.append(self.format_checker.format_reference(ref, style))
            else:
                # Try papers table
                paper = self.db.get_paper(ref_id)
                if paper:
                    from src.knowledge_base.models import Reference
                    ref = Reference(
                        title=paper.title,
                        authors=paper.authors,
                        year=paper.year,
                        journal=paper.journal,
                        volume=paper.volume,
                        pages=paper.pages,
                        doi=paper.doi,
                    )
                    entries.append(self.format_checker.format_reference(ref, style))

        # Sort alphabetically by first author
        entries.sort(key=str.lower)
        return "\n\n".join(entries)

    def export_to_file(
        self,
        manuscript: Manuscript,
        output_path: str | Path,
        journal_profile: Optional[dict] = None,
    ) -> Path:
        """Export formatted manuscript to a file."""
        formatted = self.format_manuscript(manuscript, journal_profile)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(formatted, encoding="utf-8")
        return output
