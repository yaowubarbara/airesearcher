"""Parse MLA-style inline citations from manuscript text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedCitation:
    """A citation parsed from manuscript text."""

    author: Optional[str] = None
    title: Optional[str] = None
    title_style: Optional[str] = None  # "italic" or "quoted"
    pages: Optional[str] = None
    is_secondary: bool = False
    mediating_author: Optional[str] = None
    raw: str = ""
    start_pos: int = 0
    end_pos: int = 0


# Regex building blocks
_AUTHOR = r"[A-Z\u00C0-\u024F][a-zA-Z\u00C0-\u024F''\-]+"  # Surname (allows hyphens + caps)
_CHINESE_AUTHOR = r"[\u4e00-\u9fff]{1,4}"  # Chinese name
_AUTHOR_ANY = rf"(?:{_AUTHOR}|{_CHINESE_AUTHOR})"
_PAGE = r"\d{1,4}"  # Page number (1-4 digits)
_PAGES = rf"{_PAGE}(?:\s*[-\u2013]\s*{_PAGE})?"  # Single page or range
_ITALIC_TITLE = r"\*([^*]+)\*"  # *Title*
_QUOTED_TITLE = r'"([^"]+)"'  # "Title"

# Year-like numbers to exclude from page matching (1800-2099)
_YEAR_RANGE = range(1800, 2100)


def _is_year(s: str) -> bool:
    """Check if a string looks like a publication year."""
    try:
        return int(s) in _YEAR_RANGE
    except ValueError:
        return False


def parse_mla_citations(text: str) -> list[ParsedCitation]:
    """Parse MLA-style inline citations from text.

    Recognizes these patterns in priority order:
    1. Secondary citation: (qtd. in Author, *Title* Page)
    2. Author + italic title + page: (Author, *Title* Page)
    3. Author + quoted title + page: (Author, "Title" Page)
    4. Simple author + page: (Author Page) — excludes year-like numbers
    5. Title-only italic: (*Title* Page)
    """
    citations: list[ParsedCitation] = []
    seen_spans: set[tuple[int, int]] = set()

    def _add(c: ParsedCitation) -> None:
        span = (c.start_pos, c.end_pos)
        if span not in seen_spans:
            seen_spans.add(span)
            citations.append(c)

    # Pattern 1: Secondary citation — (qtd. in Author, *Title* Page)
    # Also handles: (qtd. in Author Page) without title
    pat_secondary_title = re.compile(
        r'\(\s*qtd\.\s+in\s+'
        rf'({_AUTHOR_ANY})'         # mediating author
        r'(?:,\s*'
        rf'{_ITALIC_TITLE}'         # optional italic title
        r')?\s+'
        rf'({_PAGES})'              # page
        r'\s*\)',
        re.UNICODE,
    )
    for m in pat_secondary_title.finditer(text):
        _add(ParsedCitation(
            author=None,
            mediating_author=m.group(1),
            title=m.group(2),
            title_style="italic" if m.group(2) else None,
            pages=m.group(3),
            is_secondary=True,
            raw=m.group(0),
            start_pos=m.start(),
            end_pos=m.end(),
        ))

    # Pattern 1b: Secondary — (quoted in Author Year, Page) [Chicago variant]
    pat_secondary_chicago = re.compile(
        r'\(\s*quoted\s+in\s+'
        rf'({_AUTHOR_ANY})'
        r'(?:\s+\d{{4}})?\s*'
        r'(?:,\s*)?'
        rf'({_PAGES})?'
        r'\s*\)',
        re.UNICODE,
    )
    for m in pat_secondary_chicago.finditer(text):
        span = (m.start(), m.end())
        if span not in seen_spans:
            _add(ParsedCitation(
                author=None,
                mediating_author=m.group(1),
                pages=m.group(2),
                is_secondary=True,
                raw=m.group(0),
                start_pos=m.start(),
                end_pos=m.end(),
            ))

    # Pattern 2: Author + italic title + page — (Derrida, *Sovereignties* 42)
    pat_author_italic = re.compile(
        r'\(\s*'
        rf'({_AUTHOR_ANY})'         # author
        r',\s*'
        rf'{_ITALIC_TITLE}'         # italic title
        r'(?:\s+'
        rf'({_PAGES})'              # optional page
        r')?\s*\)',
        re.UNICODE,
    )
    for m in pat_author_italic.finditer(text):
        span = (m.start(), m.end())
        if span not in seen_spans:
            _add(ParsedCitation(
                author=m.group(1),
                title=m.group(2),
                title_style="italic",
                pages=m.group(3),
                raw=m.group(0),
                start_pos=m.start(),
                end_pos=m.end(),
            ))

    # Pattern 3: Author + quoted title + page — (Derrida, "Demeure" 78)
    pat_author_quoted = re.compile(
        r'\(\s*'
        rf'({_AUTHOR_ANY})'         # author
        r',\s*'
        rf'{_QUOTED_TITLE}'         # quoted title
        r'(?:\s+'
        rf'({_PAGES})'              # optional page
        r')?\s*\)',
        re.UNICODE,
    )
    for m in pat_author_quoted.finditer(text):
        span = (m.start(), m.end())
        if span not in seen_spans:
            _add(ParsedCitation(
                author=m.group(1),
                title=m.group(2),
                title_style="quoted",
                pages=m.group(3),
                raw=m.group(0),
                start_pos=m.start(),
                end_pos=m.end(),
            ))

    # Pattern 4: Simple author + page — (Felstiner 247)
    pat_simple = re.compile(
        r'\(\s*'
        rf'({_AUTHOR_ANY})'         # author
        r'\s+'
        rf'({_PAGES})'              # page
        r'\s*\)',
        re.UNICODE,
    )
    for m in pat_simple.finditer(text):
        span = (m.start(), m.end())
        if span not in seen_spans:
            page_str = m.group(2)
            # Exclude year-like numbers
            if _is_year(page_str.split("-")[0].split("\u2013")[0].strip()):
                continue
            _add(ParsedCitation(
                author=m.group(1),
                pages=page_str,
                raw=m.group(0),
                start_pos=m.start(),
                end_pos=m.end(),
            ))

    # Pattern 5: Title-only italic — (*Atemwende* 78)
    pat_title_only = re.compile(
        r'\(\s*'
        rf'{_ITALIC_TITLE}'         # italic title
        r'\s+'
        rf'({_PAGES})'              # page
        r'\s*\)',
        re.UNICODE,
    )
    for m in pat_title_only.finditer(text):
        span = (m.start(), m.end())
        if span not in seen_spans:
            _add(ParsedCitation(
                title=m.group(1),
                title_style="italic",
                pages=m.group(2),
                raw=m.group(0),
                start_pos=m.start(),
                end_pos=m.end(),
            ))

    # Sort by position
    citations.sort(key=lambda c: c.start_pos)
    return citations


def group_citations(
    citations: list[ParsedCitation],
) -> dict[str, list[ParsedCitation]]:
    """Group citations by author surname (or mediating author for secondary)."""
    groups: dict[str, list[ParsedCitation]] = {}
    for c in citations:
        key = c.author or c.mediating_author or c.title or "unknown"
        groups.setdefault(key, []).append(c)
    return groups
