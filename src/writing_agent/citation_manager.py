"""Citation management: formatting, verification, and bibliography generation."""

from __future__ import annotations

import re
from typing import Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import Reference


class CitationManager:
    """Manages inline citations, bibliography entries, and citation verification.

    Supports MLA (9th ed.), Chicago (17th ed. notes-bibliography), and
    GB/T 7714-2015 citation styles.
    """

    # ------------------------------------------------------------------ #
    #  Inline citation formatting
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_citation(ref: Reference, style: str) -> str:
        """Format an inline (in-text) citation for a reference.

        Args:
            ref: The Reference object to cite.
            style: Citation style - one of "MLA", "Chicago", or "GB/T 7714".

        Returns:
            A formatted inline citation string.
        """
        style_upper = style.upper().replace(" ", "")
        if style_upper in ("MLA", "MLA9"):
            return _format_inline_mla(ref)
        elif style_upper in ("CHICAGO", "CHICAGO17"):
            return _format_inline_chicago(ref)
        elif style_upper in ("GB/T7714", "GBT7714", "GB"):
            return _format_inline_gb(ref)
        else:
            return _format_inline_mla(ref)

    # ------------------------------------------------------------------ #
    #  Bibliography entry formatting
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_bibliography_entry(ref: Reference, style: str) -> str:
        """Format a full bibliography / works-cited entry for a reference.

        If the Reference already carries a pre-formatted string for the
        requested style (formatted_mla, formatted_chicago, formatted_gb),
        that cached version is returned directly.

        Args:
            ref: The Reference object.
            style: Citation style - one of "MLA", "Chicago", or "GB/T 7714".

        Returns:
            A formatted bibliography entry string.
        """
        style_upper = style.upper().replace(" ", "")

        # Use pre-formatted strings when available
        if style_upper in ("MLA", "MLA9") and ref.formatted_mla:
            return ref.formatted_mla
        if style_upper in ("CHICAGO", "CHICAGO17") and ref.formatted_chicago:
            return ref.formatted_chicago
        if style_upper in ("GB/T7714", "GBT7714", "GB") and ref.formatted_gb:
            return ref.formatted_gb

        # Generate on the fly
        if style_upper in ("MLA", "MLA9"):
            return _format_bib_mla(ref)
        elif style_upper in ("CHICAGO", "CHICAGO17"):
            return _format_bib_chicago(ref)
        elif style_upper in ("GB/T7714", "GBT7714", "GB"):
            return _format_bib_gb(ref)
        else:
            return _format_bib_mla(ref)

    # ------------------------------------------------------------------ #
    #  Citation verification
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify_all_citations(
        text: str, known_refs: dict[str, Reference]
    ) -> tuple[list[str], list[str]]:
        """Verify all citations found in a text against known references.

        Scans the text for parenthetical citations (e.g. ``(Author Year)``,
        ``(Author, p. 42)``, ``[1]``, etc.) and checks whether each one can
        be matched to an entry in *known_refs*.

        Args:
            text: The manuscript text to scan.
            known_refs: Mapping of reference id -> Reference for all known refs.

        Returns:
            A tuple of (verified, unverified) where each element is a list of
            citation strings found in the text.
        """
        # Build lookup helpers: surname -> ref_id, year -> set[ref_id]
        surname_year: dict[str, str] = {}  # "surname_year" -> ref_id
        for ref_id, ref in known_refs.items():
            for author in ref.authors:
                surname = _extract_surname(author)
                key = f"{surname.lower()}_{ref.year}"
                surname_year[key] = ref_id

        # Extract parenthetical citations from text
        # Patterns: (Author Year), (Author, Year), (Author Year, p. 23)
        citation_pattern = re.compile(
            r"\(([A-Z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\-'\s]*?)"
            r"[,\s]+(\d{4})"
            r"[^)]*\)"
        )
        # Also match numeric bracket citations [1], [1, 2]
        bracket_pattern = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

        verified: list[str] = []
        unverified: list[str] = []

        for match in citation_pattern.finditer(text):
            full = match.group(0)
            cited_name = match.group(1).strip()
            cited_year = match.group(2).strip()
            surname = _extract_surname(cited_name)
            key = f"{surname.lower()}_{cited_year}"
            if key in surname_year:
                verified.append(full)
            else:
                unverified.append(full)

        for match in bracket_pattern.finditer(text):
            full = match.group(0)
            # Numeric citations are hard to verify without a numbering scheme;
            # mark as unverified unless the number maps to a ref id.
            nums = [n.strip() for n in match.group(1).split(",")]
            all_found = all(n in known_refs for n in nums)
            if all_found:
                verified.append(full)
            else:
                unverified.append(full)

        return verified, unverified

    # ------------------------------------------------------------------ #
    #  Bibliography generation
    # ------------------------------------------------------------------ #

    @staticmethod
    def generate_bibliography(
        ref_ids: list[str],
        db: Database,
        style: str,
    ) -> str:
        """Generate a full bibliography section from a list of reference IDs.

        Retrieves each reference from the database and formats it according
        to the requested citation style.  Entries are sorted alphabetically
        by the first author's surname (MLA/Chicago) or by appearance order
        (GB/T 7714).

        Args:
            ref_ids: List of reference IDs to include.
            db: The Database instance for looking up references.
            style: Citation style - one of "MLA", "Chicago", or "GB/T 7714".

        Returns:
            A formatted bibliography as a single string, entries separated
            by blank lines.
        """
        refs: list[Reference] = []
        for ref_id in ref_ids:
            row = db.conn.execute(
                "SELECT * FROM references_ WHERE id = ?", (ref_id,)
            ).fetchone()
            if row is not None:
                import json as _json
                ref = Reference(
                    id=row["id"],
                    paper_id=row["paper_id"],
                    title=row["title"],
                    authors=_json.loads(row["authors"]),
                    year=row["year"],
                    journal=row["journal"],
                    volume=row["volume"],
                    issue=row["issue"],
                    pages=row["pages"],
                    doi=row["doi"],
                    publisher=row["publisher"],
                    verified=bool(row["verified"]),
                    verification_source=row["verification_source"],
                    formatted_mla=row["formatted_mla"],
                    formatted_chicago=row["formatted_chicago"],
                    formatted_gb=row["formatted_gb"],
                )
                refs.append(ref)

        style_upper = style.upper().replace(" ", "")
        if style_upper in ("GB/T7714", "GBT7714", "GB"):
            # GB/T 7714 uses appearance order; keep the ref_ids order
            pass
        else:
            # MLA & Chicago: alphabetical by first author surname
            refs.sort(key=lambda r: _extract_surname(r.authors[0]).lower() if r.authors else "")

        entries = [
            CitationManager.format_bibliography_entry(ref, style) for ref in refs
        ]
        return "\n\n".join(entries)


# ====================================================================== #
#  Private helpers
# ====================================================================== #


def _extract_surname(name: str) -> str:
    """Extract the surname from an author name string.

    Handles both 'First Last' and 'Last, First' formats, as well as
    single-word Chinese names.
    """
    name = name.strip()
    if not name:
        return ""
    if "," in name:
        return name.split(",")[0].strip()
    parts = name.split()
    return parts[-1] if parts else name


def _author_last_first(name: str) -> str:
    """Convert 'First Last' to 'Last, First'."""
    name = name.strip()
    if "," in name:
        return name  # already Last, First
    parts = name.split()
    if len(parts) <= 1:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


# ---- MLA 9th edition ------------------------------------------------ #

def _format_inline_mla(ref: Reference) -> str:
    surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
    if ref.pages:
        return f"({surname} {ref.pages})"
    return f"({surname})"


def _format_bib_mla(ref: Reference) -> str:
    # First author Last, First. Additional authors First Last.
    if not ref.authors:
        author_str = "Unknown Author"
    elif len(ref.authors) == 1:
        author_str = _author_last_first(ref.authors[0])
    elif len(ref.authors) == 2:
        author_str = (
            f"{_author_last_first(ref.authors[0])}, "
            f"and {ref.authors[1]}"
        )
    else:
        author_str = f"{_author_last_first(ref.authors[0])}, et al."

    title_part = f"\"{ref.title}.\""
    journal_part = ""
    if ref.journal:
        journal_part = f" *{ref.journal}*"
        if ref.volume:
            journal_part += f", vol. {ref.volume}"
        if ref.issue:
            journal_part += f", no. {ref.issue}"
        journal_part += f", {ref.year}"
        if ref.pages:
            journal_part += f", pp. {ref.pages}"
        journal_part += "."

    doi_part = ""
    if ref.doi:
        doi_part = f" https://doi.org/{ref.doi}."

    return f"{author_str}. {title_part}{journal_part}{doi_part}"


# ---- Chicago 17th ed. (notes-bibliography) -------------------------- #

def _format_inline_chicago(ref: Reference) -> str:
    surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
    return f"({surname} {ref.year})"


def _format_bib_chicago(ref: Reference) -> str:
    if not ref.authors:
        author_str = "Unknown Author"
    elif len(ref.authors) == 1:
        author_str = _author_last_first(ref.authors[0])
    else:
        others = ", ".join(ref.authors[1:])
        author_str = f"{_author_last_first(ref.authors[0])}, {others}"

    title_part = f"\"{ref.title}.\""
    journal_part = ""
    if ref.journal:
        journal_part = f" *{ref.journal}*"
        if ref.volume:
            journal_part += f" {ref.volume}"
        if ref.issue:
            journal_part += f", no. {ref.issue}"
        journal_part += f" ({ref.year})"
        if ref.pages:
            journal_part += f": {ref.pages}"
        journal_part += "."

    doi_part = ""
    if ref.doi:
        doi_part = f" https://doi.org/{ref.doi}."

    return f"{author_str}. {title_part}{journal_part}{doi_part}"


# ---- GB/T 7714-2015 ------------------------------------------------ #

def _format_inline_gb(ref: Reference) -> str:
    surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
    return f"({surname}, {ref.year})"


def _format_bib_gb(ref: Reference) -> str:
    # GB/T 7714 format: Authors. Title[J]. Journal, Year, Volume(Issue): Pages.
    if not ref.authors:
        author_str = "Unknown Author"
    elif len(ref.authors) <= 3:
        author_str = ", ".join(ref.authors)
    else:
        author_str = ", ".join(ref.authors[:3]) + ", et al"

    title_part = f"{ref.title}[J]"
    journal_part = ""
    if ref.journal:
        journal_part = f". {ref.journal}, {ref.year}"
        if ref.volume:
            journal_part += f", {ref.volume}"
        if ref.issue:
            journal_part += f"({ref.issue})"
        if ref.pages:
            journal_part += f": {ref.pages}"
        journal_part += "."
    else:
        journal_part = f". {ref.year}."

    doi_part = ""
    if ref.doi:
        doi_part = f" DOI:{ref.doi}."

    return f"{author_str}. {title_part}{journal_part}{doi_part}"
