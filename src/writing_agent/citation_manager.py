"""Citation management: formatting, verification, and bibliography generation.

Supports MLA (9th ed.), Chicago (17th ed. notes-bibliography), and
GB/T 7714-2015 citation styles, plus footnote generation, block quote
formatting, secondary ("qtd. in") citations, and multilingual handling.
"""

from __future__ import annotations

import re
from typing import Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import Reference


class CitationManager:
    """Manages inline citations, bibliography entries, and citation verification.

    Supports MLA (9th ed.), Chicago (17th ed. notes-bibliography), and
    GB/T 7714-2015 citation styles.  Extended with footnote/endnote generation,
    block-quote formatting (multilingual), and secondary citation ("qtd. in").
    """

    def __init__(self) -> None:
        self._footnotes: list[str] = []
        self._footnote_counter: int = 0

    def reset_footnotes(self) -> None:
        """Clear footnote state for a new section or manuscript."""
        self._footnotes = []
        self._footnote_counter = 0

    # ------------------------------------------------------------------ #
    #  Inline citation formatting
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_citation(
        ref: Reference,
        style: str,
        page: Optional[str] = None,
        short_title: Optional[str] = None,
    ) -> str:
        """Format an inline (in-text) citation for a reference.

        Args:
            ref: The Reference object to cite.
            style: Citation style - one of "MLA", "Chicago", or "GB/T 7714".
            page: Override page number for this specific citation.
            short_title: Short title for disambiguation (MLA style).

        Returns:
            A formatted inline citation string.
        """
        style_upper = style.upper().replace(" ", "")
        p = page or ref.pages
        if style_upper in ("MLA", "MLA9"):
            return _format_inline_mla(ref, page=p, short_title=short_title)
        elif style_upper in ("CHICAGO", "CHICAGO17"):
            return _format_inline_chicago(ref, page=p)
        elif style_upper in ("GB/T7714", "GBT7714", "GB"):
            return _format_inline_gb(ref, page=p)
        else:
            return _format_inline_mla(ref, page=p, short_title=short_title)

    # ------------------------------------------------------------------ #
    #  Secondary citation ("qtd. in")
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_secondary_citation(
        original_author: str,
        mediating_ref: Reference,
        style: str,
        page: Optional[str] = None,
    ) -> str:
        """Format a secondary citation (quoting through a mediating source).

        Used when quoting an author whose work you accessed through another
        source, e.g. ``(qtd. in Smith 45)`` in MLA.

        Args:
            original_author: Name of the original author being quoted.
            mediating_ref: The Reference through which the quote was accessed.
            style: Citation style.
            page: Page number in the mediating source.

        Returns:
            Formatted secondary citation string.
        """
        style_upper = style.upper().replace(" ", "")
        surname = _extract_surname(mediating_ref.authors[0]) if mediating_ref.authors else "Unknown"
        p = page or mediating_ref.pages or ""

        if style_upper in ("MLA", "MLA9"):
            if p:
                return f"({original_author}, qtd. in {surname} {p})"
            return f"({original_author}, qtd. in {surname})"
        elif style_upper in ("CHICAGO", "CHICAGO17"):
            if p:
                return f"({original_author}, quoted in {surname} {mediating_ref.year}, {p})"
            return f"({original_author}, quoted in {surname} {mediating_ref.year})"
        elif style_upper in ("GB/T7714", "GBT7714", "GB"):
            if p:
                return f"({original_author}, 转引自 {surname}, {mediating_ref.year}, {p})"
            return f"({original_author}, 转引自 {surname}, {mediating_ref.year})"
        else:
            if p:
                return f"({original_author}, qtd. in {surname} {p})"
            return f"({original_author}, qtd. in {surname})"

    # ------------------------------------------------------------------ #
    #  Footnote / endnote generation (Chicago Notes-Bibliography)
    # ------------------------------------------------------------------ #

    def add_footnote(
        self,
        content: str,
        refs: Optional[list[Reference]] = None,
        style: str = "Chicago",
    ) -> str:
        """Create a footnote and return the superscript marker.

        Footnotes in Comparative Literature are substantive: they contain
        bibliographic guidance clusters, extended arguments, translation
        notes, and philological observations -- not mere reference pointers.

        Args:
            content: The substantive footnote text.
            refs: Optional references to format as "See ..." citations
                  appended to the footnote content.
            style: Citation style for formatting any appended references.

        Returns:
            A superscript marker string, e.g. ``[^1]`` (Markdown footnote).
        """
        self._footnote_counter += 1
        n = self._footnote_counter

        note_text = content
        if refs:
            see_parts = []
            for ref in refs:
                surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
                if style.upper().startswith("CHICAGO"):
                    see_parts.append(
                        f"{surname}, *{ref.title}* ({ref.year})"
                    )
                else:
                    page_str = f" {ref.pages}" if ref.pages else ""
                    see_parts.append(f"{surname}{page_str}")

            see_cluster = "; ".join(see_parts)
            if note_text:
                note_text = f"{note_text} See {see_cluster}."
            else:
                note_text = f"See {see_cluster}."

        self._footnotes.append(note_text)
        return f"[^{n}]"

    def format_footnote_full(
        self,
        ref: Reference,
        page: Optional[str] = None,
    ) -> str:
        """Format a full Chicago-style footnote citation (first occurrence).

        Chicago Notes-Bibliography uses a different format in footnotes
        than in the bibliography: first name before last name, commas
        instead of periods, specific page cited.

        Args:
            ref: The Reference to cite.
            page: Specific page(s) cited.

        Returns:
            Formatted footnote citation string.
        """
        if not ref.authors:
            author_str = "Unknown Author"
        elif len(ref.authors) == 1:
            author_str = ref.authors[0]  # First Last in notes
        elif len(ref.authors) == 2:
            author_str = f"{ref.authors[0]} and {ref.authors[1]}"
        elif len(ref.authors) == 3:
            author_str = f"{ref.authors[0]}, {ref.authors[1]}, and {ref.authors[2]}"
        else:
            author_str = f"{ref.authors[0]} et al."

        title_part = f'"{ref.title},"'
        journal_part = ""
        if ref.journal:
            journal_part = f" *{ref.journal}*"
            if ref.volume:
                journal_part += f" {ref.volume}"
            if ref.issue:
                journal_part += f", no. {ref.issue}"
            journal_part += f" ({ref.year})"
            p = page or ref.pages
            if p:
                journal_part += f": {p}"
        else:
            if ref.publisher:
                journal_part = f" ({ref.publisher}, {ref.year})"
            else:
                journal_part = f" ({ref.year})"
            p = page or ref.pages
            if p:
                journal_part += f", {p}"

        return f"{author_str}, {title_part}{journal_part}."

    def format_footnote_short(
        self,
        ref: Reference,
        page: Optional[str] = None,
    ) -> str:
        """Format a shortened Chicago-style footnote (subsequent occurrences).

        Args:
            ref: The Reference to cite.
            page: Specific page(s) cited.

        Returns:
            Shortened footnote string, e.g. ``Surname, "Short Title," page.``
        """
        surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
        words = ref.title.split()
        short_title = " ".join(words[:4])
        if len(words) > 4:
            short_title += "..."

        p = page or ref.pages
        if p:
            return f'{surname}, "{short_title}," {p}.'
        return f'{surname}, "{short_title}."'

    def get_all_footnotes(self) -> list[str]:
        """Return all accumulated footnotes in order."""
        return list(self._footnotes)

    def render_footnotes_section(self) -> str:
        """Render all footnotes as a Markdown footnote block."""
        if not self._footnotes:
            return ""
        lines = []
        for i, note in enumerate(self._footnotes, 1):
            lines.append(f"[^{i}]: {note}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Block quote formatting (with multilingual support)
    # ------------------------------------------------------------------ #

    @staticmethod
    def format_block_quote(
        text: str,
        ref: Reference,
        style: str,
        page: Optional[str] = None,
        translation: Optional[str] = None,
        translator_note: Optional[str] = None,
    ) -> str:
        """Format a block quotation (35+ words) with optional translation.

        For multilingual comparative literature, primary text block quotes
        present the original language first, followed by the translation.

        Args:
            text: The quoted passage (in original language).
            ref: The source Reference.
            style: Citation style.
            page: Specific page(s).
            translation: Target-language translation of the passage.
            translator_note: e.g. "(translation modified)" or "(my translation)".

        Returns:
            Formatted block quote string with Markdown indentation.
        """
        p = page or ref.pages or ""
        surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
        style_upper = style.upper().replace(" ", "")

        if style_upper in ("MLA", "MLA9"):
            cite = f"({surname} {p})" if p else f"({surname})"
        elif style_upper in ("CHICAGO", "CHICAGO17"):
            cite = f"({surname} {ref.year}, {p})" if p else f"({surname} {ref.year})"
        else:
            cite = f"({surname}, {ref.year}, {p})" if p else f"({surname}, {ref.year})"

        lines: list[str] = []

        # Original text block
        for line in text.strip().split("\n"):
            lines.append(f"> {line}")

        if translation:
            lines.append(">")
            for line in translation.strip().split("\n"):
                lines.append(f"> *{line}*")
            if translator_note:
                lines.append(f"> {translator_note}")

        # Attribution
        lines.append(f"> {cite}")

        return "\n".join(lines)

    @staticmethod
    def format_inline_quote_multilingual(
        quoted_text: str,
        translation: Optional[str] = None,
        translator_note: Optional[str] = None,
    ) -> str:
        """Format a short inline quotation with optional translation.

        Original language in quotes, translation in parentheses separated
        by semicolon, per CL convention.

        Args:
            quoted_text: The original-language quotation.
            translation: Translation into the article's language.
            translator_note: e.g. "(my translation)" or "(translation modified)".

        Returns:
            Formatted inline quotation string.
        """
        if translation:
            t_note = f" {translator_note}" if translator_note else ""
            return f'"{quoted_text}" ("{translation}"{t_note})'
        return f'"{quoted_text}"'

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

        Scans for parenthetical citations ``(Author Year)``, ``(Author Page)``,
        ``(qtd. in Author Page)``, ``[1]``, etc. and checks each against
        *known_refs*.

        Args:
            text: The manuscript text to scan.
            known_refs: Mapping of reference id -> Reference for all known refs.

        Returns:
            A tuple of (verified, unverified) citation strings.
        """
        # Build lookup helpers
        surname_year: dict[str, str] = {}
        surname_only: dict[str, str] = {}
        for ref_id, ref in known_refs.items():
            for author in ref.authors:
                surname = _extract_surname(author)
                key = f"{surname.lower()}_{ref.year}"
                surname_year[key] = ref_id
                surname_only[surname.lower()] = ref_id

        # Author-year: (Author Year), (Author, Year, p. 23)
        citation_pattern = re.compile(
            r"\(([A-Z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\-'\s]*?)"
            r"[,\s]+(\d{4})"
            r"[^)]*\)"
        )
        # MLA author-page: (Author 42), (Author 42-50)
        mla_pattern = re.compile(
            r"\(([A-Z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\-'\s]*?)"
            r"\s+(\d+(?:\s*[-\u2013]\s*\d+)?)\)"
        )
        # Secondary: (qtd. in Author Page), (quoted in Author Year)
        secondary_pattern = re.compile(
            r"\((?:qtd\.\s+in|quoted\s+in|转引自)\s+"
            r"([A-Z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\-'\s]*?)"
            r"[,\s]+[^)]+\)"
        )
        # Numeric bracket: [1], [1, 2]
        bracket_pattern = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

        verified: list[str] = []
        unverified: list[str] = []
        seen: set[str] = set()

        for match in citation_pattern.finditer(text):
            full = match.group(0)
            if full in seen:
                continue
            seen.add(full)
            cited_name = match.group(1).strip()
            cited_year = match.group(2).strip()
            surname = _extract_surname(cited_name)
            key = f"{surname.lower()}_{cited_year}"
            if key in surname_year:
                verified.append(full)
            else:
                unverified.append(full)

        for match in secondary_pattern.finditer(text):
            full = match.group(0)
            if full in seen:
                continue
            seen.add(full)
            mediator = match.group(1).strip()
            surname = _extract_surname(mediator)
            if surname.lower() in surname_only:
                verified.append(full)
            else:
                unverified.append(full)

        for match in mla_pattern.finditer(text):
            full = match.group(0)
            if full in seen:
                continue
            seen.add(full)
            cited_name = match.group(1).strip()
            surname = _extract_surname(cited_name)
            if surname.lower() in surname_only:
                verified.append(full)
            else:
                unverified.append(full)

        for match in bracket_pattern.finditer(text):
            full = match.group(0)
            if full in seen:
                continue
            seen.add(full)
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
            pass
        else:
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

def _format_inline_mla(
    ref: Reference,
    page: Optional[str] = None,
    short_title: Optional[str] = None,
) -> str:
    surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
    p = page or ref.pages
    if short_title and p:
        return f'({surname}, *{short_title}* {p})'
    elif short_title:
        return f'({surname}, *{short_title}*)'
    elif p:
        return f"({surname} {p})"
    return f"({surname})"


def _format_bib_mla(ref: Reference) -> str:
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

def _format_inline_chicago(
    ref: Reference,
    page: Optional[str] = None,
) -> str:
    surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
    p = page or ref.pages
    if p:
        return f"({surname} {ref.year}, {p})"
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

def _format_inline_gb(
    ref: Reference,
    page: Optional[str] = None,
) -> str:
    surname = _extract_surname(ref.authors[0]) if ref.authors else "Unknown"
    p = page or ref.pages
    if p:
        return f"({surname}, {ref.year}, {p})"
    return f"({surname}, {ref.year})"


def _format_bib_gb(ref: Reference) -> str:
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
