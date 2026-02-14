"""PDF parsing for academic papers using PyMuPDF (fitz).

Extracts structured content from scholarly PDFs including title, abstract,
section headers, body text, references, and quotations with page numbers.
Handles multi-column layouts, footnotes, and headers/footers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Typical header/footer zones as fraction of page height.
_HEADER_ZONE = 0.08  # top 8% of page
_FOOTER_ZONE = 0.92  # bottom 8% of page

# Minimum y-gap between text blocks that suggests a column break (points).
_COLUMN_GAP_THRESHOLD = 20

# Patterns used to identify section headings in academic papers.
_SECTION_HEADING_PATTERNS = [
    # Numbered sections: "1. Introduction", "2.1 Methods", "III. Results"
    re.compile(
        r"^(?:[IVXLC]+\.|[0-9]{1,2}(?:\.[0-9]{1,2})*\.?\s)"
        r"\s*[A-Z\u4e00-\u9fff].*$"
    ),
    # Common unnumbered headings
    re.compile(
        r"^(?:Abstract|Introduction|Background|Literature\s+Review|"
        r"Methodology|Methods|Materials?\s+and\s+Methods|Results|"
        r"Discussion|Conclusion|Conclusions|Acknowledgment|Acknowledgments|"
        r"Acknowledgement|Acknowledgements|References|Bibliography|"
        r"Appendix|Notes|Works\s+Cited|Funding|"
        # French equivalents
        r"Résumé|Introduction|Méthodologie|Résultats|Discussion|"
        r"Conclusion|Bibliographie|Remerciements|"
        # Chinese equivalents
        r"摘要|引言|导论|绪论|文献综述|研究方法|结果|讨论|结论|参考文献|致谢"
        r")$",
        re.IGNORECASE,
    ),
]

# Pattern to detect reference list entries.
_REFERENCE_ENTRY_PATTERN = re.compile(
    r"^\[?\d{1,3}[\].)]\s|"  # [1] or 1) or 1.
    r"^[A-Z\u4e00-\u9fff][a-zA-Z\u4e00-\u9fff\-éèêëàâäïîôùûüçœæ]+,?\s",
)

# Patterns for identifying quoted text.
_QUOTATION_PATTERNS = [
    # English double quotes
    re.compile(r"\u201c([^\u201d]{15,})\u201d"),
    # Straight double quotes (at least 15 chars to avoid trivial matches)
    re.compile(r'"([^"]{15,})"'),
    # Block quote heuristic: indented paragraph of 40+ chars
    re.compile(r"(?:^|\n)([ \t]{4,}.{40,})(?:\n|$)"),
    # Chinese quotation marks
    re.compile(r"\u300c([^\u300d]{10,})\u300d"),
    re.compile(r"\u201c([^\u201d]{10,})\u201d"),
    # French guillemets
    re.compile(r"\u00ab\s?([^\u00bb]{15,})\s?\u00bb"),
]


@dataclass
class ExtractedQuotation:
    """A quotation extracted from the PDF with its location."""

    text: str
    page: int  # 1-indexed page number
    context: str = ""  # surrounding text for disambiguation


@dataclass
class Section:
    """A section of the paper with its heading and body text."""

    heading: str
    content: str
    level: int = 1  # 1 = top-level, 2 = subsection, etc.


@dataclass
class ParsedPaper:
    """Structured representation of a parsed academic PDF."""

    title: str = ""
    abstract: str = ""
    sections: list[Section] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    quotations: list[ExtractedQuotation] = field(default_factory=list)
    full_text: str = ""  # the entire extracted body text
    page_count: int = 0
    language: str = "en"  # detected language hint


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_header_or_footer(block_bbox: tuple, page_height: float) -> bool:
    """Return True if the text block sits in the header or footer zone."""
    _, y0, _, y1 = block_bbox
    mid_y = (y0 + y1) / 2
    return mid_y < page_height * _HEADER_ZONE or mid_y > page_height * _FOOTER_ZONE


def _sort_blocks_reading_order(blocks: list[dict], page_width: float) -> list[dict]:
    """Sort text blocks into reading order, handling two-column layouts.

    Strategy: if more than 40% of blocks have their centre in the left
    half and a similar proportion in the right half, assume two columns.
    Sort left-column blocks first (top-to-bottom), then right-column.
    Otherwise fall back to simple top-to-bottom ordering.
    """
    if not blocks:
        return blocks

    midpoint = page_width / 2
    left = [b for b in blocks if (b["x0"] + b["x1"]) / 2 < midpoint]
    right = [b for b in blocks if (b["x0"] + b["x1"]) / 2 >= midpoint]

    total = len(blocks)
    if total >= 4 and len(left) / total > 0.3 and len(right) / total > 0.3:
        # Two-column layout detected.
        left.sort(key=lambda b: b["y0"])
        right.sort(key=lambda b: b["y0"])
        return left + right

    # Single-column: sort top-to-bottom, then left-to-right for ties.
    return sorted(blocks, key=lambda b: (b["y0"], b["x0"]))


def _extract_text_blocks(page: fitz.Page) -> list[dict]:
    """Extract text blocks from a page, filtering headers/footers.

    Returns a list of dicts with keys: x0, y0, x1, y1, text, font_size.
    """
    page_height = page.rect.height
    raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    results: list[dict] = []
    for block in raw_blocks:
        if block.get("type") != 0:
            # Skip image blocks.
            continue

        bbox = (block["bbox"][0], block["bbox"][1], block["bbox"][2], block["bbox"][3])
        if _is_header_or_footer(bbox, page_height):
            continue

        # Collect lines from spans.
        lines_text: list[str] = []
        max_font_size = 0.0
        for line in block.get("lines", []):
            spans_text: list[str] = []
            for span in line.get("spans", []):
                spans_text.append(span["text"])
                if span.get("size", 0) > max_font_size:
                    max_font_size = span["size"]
            line_str = "".join(spans_text).rstrip()
            if line_str:
                lines_text.append(line_str)

        text = "\n".join(lines_text).strip()
        if not text:
            continue

        results.append({
            "x0": bbox[0],
            "y0": bbox[1],
            "x1": bbox[2],
            "y1": bbox[3],
            "text": text,
            "font_size": max_font_size,
        })

    return results


def _is_heading(text: str, font_size: float, median_font_size: float) -> bool:
    """Heuristically decide whether a text block is a section heading."""
    stripped = text.strip()
    if not stripped or len(stripped) > 200:
        return False

    # If font is noticeably larger than body text, likely a heading.
    if font_size > median_font_size * 1.15 and len(stripped) < 120:
        return True

    # Check against known heading patterns.
    for pattern in _SECTION_HEADING_PATTERNS:
        if pattern.match(stripped):
            return True

    return False


def _heading_level(text: str) -> int:
    """Guess heading level: 1 for top-level, 2 for subsection, etc."""
    stripped = text.strip()
    # "2.1 Foo" -> level 2, "2.1.3 Foo" -> level 3
    m = re.match(r"^(\d+(?:\.\d+)*)", stripped)
    if m:
        return m.group(1).count(".") + 1
    return 1


def _detect_references_start(text: str) -> bool:
    """Return True if text looks like the start of the References section."""
    stripped = text.strip().lower()
    return stripped in {
        "references",
        "bibliography",
        "works cited",
        "参考文献",
        "bibliographie",
    } or re.match(r"^\d+\.\s*references$", stripped) is not None


def _extract_quotations_from_page(
    page_text: str, page_number: int, context_chars: int = 200
) -> list[ExtractedQuotation]:
    """Find quotations on a single page of text."""
    quotations: list[ExtractedQuotation] = []
    seen_texts: set[str] = set()

    for pattern in _QUOTATION_PATTERNS:
        for match in pattern.finditer(page_text):
            q_text = match.group(1).strip()
            # De-duplicate within page.
            if q_text in seen_texts:
                continue
            seen_texts.add(q_text)

            # Build context window.
            start = max(0, match.start() - context_chars)
            end = min(len(page_text), match.end() + context_chars)
            context = page_text[start:end].strip()

            quotations.append(
                ExtractedQuotation(text=q_text, page=page_number, context=context)
            )

    return quotations


def _split_references(text: str) -> list[str]:
    """Split a references section block into individual reference strings."""
    lines = text.strip().splitlines()
    refs: list[str] = []
    current: list[str] = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            if current:
                refs.append(" ".join(current))
                current = []
            continue

        # New reference entry detected.
        if _REFERENCE_ENTRY_PATTERN.match(line_stripped) and current:
            refs.append(" ".join(current))
            current = [line_stripped]
        else:
            current.append(line_stripped)

    if current:
        refs.append(" ".join(current))

    return [r for r in refs if len(r) > 10]


def _compute_median_font_size(all_blocks: list[dict]) -> float:
    """Return the median font size across all extracted blocks."""
    sizes = sorted(b["font_size"] for b in all_blocks if b["font_size"] > 0)
    if not sizes:
        return 12.0
    mid = len(sizes) // 2
    if len(sizes) % 2 == 0:
        return (sizes[mid - 1] + sizes[mid]) / 2
    return sizes[mid]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_pdf(pdf_path: str) -> ParsedPaper:
    """Parse an academic PDF and return structured content.

    Args:
        pdf_path: Path to the PDF file on disk.

    Returns:
        A ParsedPaper dataclass with extracted title, abstract, sections,
        references, quotations, and full text.
    """
    doc = fitz.open(pdf_path)
    page_count = len(doc)

    # First pass: extract all text blocks from every page.
    pages_blocks: list[list[dict]] = []
    for page in doc:
        raw = _extract_text_blocks(page)
        ordered = _sort_blocks_reading_order(raw, page.rect.width)
        pages_blocks.append(ordered)

    # Flatten for global statistics.
    all_blocks = [b for page_blocks in pages_blocks for b in page_blocks]
    median_fs = _compute_median_font_size(all_blocks)

    # ------------------------------------------------------------------
    # Title heuristic: largest font on first page, first occurrence.
    # ------------------------------------------------------------------
    title = ""
    if pages_blocks and pages_blocks[0]:
        first_page = pages_blocks[0]
        max_fs = max(b["font_size"] for b in first_page)
        for b in first_page:
            if b["font_size"] >= max_fs * 0.95 and len(b["text"]) > 5:
                title = b["text"].replace("\n", " ").strip()
                break

    # ------------------------------------------------------------------
    # Second pass: build sections, detect abstract and references.
    # ------------------------------------------------------------------
    abstract = ""
    sections: list[Section] = []
    references_raw: list[str] = []
    full_text_parts: list[str] = []
    all_quotations: list[ExtractedQuotation] = []

    in_references = False
    current_heading = ""
    current_body: list[str] = []
    references_body: list[str] = []

    for page_idx, page_blocks in enumerate(pages_blocks):
        page_number = page_idx + 1  # 1-indexed

        # Collect page-level text for quotation extraction.
        page_text = "\n".join(b["text"] for b in page_blocks)
        all_quotations.extend(
            _extract_quotations_from_page(page_text, page_number)
        )

        for block in page_blocks:
            text = block["text"]
            fs = block["font_size"]

            if in_references:
                references_body.append(text)
                continue

            # Check for references section start.
            if _detect_references_start(text):
                # Flush current section.
                if current_heading or current_body:
                    sections.append(
                        Section(
                            heading=current_heading,
                            content="\n\n".join(current_body),
                            level=_heading_level(current_heading)
                            if current_heading
                            else 1,
                        )
                    )
                    current_heading = ""
                    current_body = []
                in_references = True
                continue

            # Check for heading.
            if _is_heading(text, fs, median_fs):
                # Flush previous section.
                if current_heading or current_body:
                    body_text = "\n\n".join(current_body)

                    # Detect abstract specially.
                    if current_heading.lower().strip() in (
                        "abstract",
                        "résumé",
                        "摘要",
                    ):
                        abstract = body_text
                    else:
                        sections.append(
                            Section(
                                heading=current_heading,
                                content=body_text,
                                level=_heading_level(current_heading),
                            )
                        )

                current_heading = text.replace("\n", " ").strip()
                current_body = []
            else:
                current_body.append(text)
                full_text_parts.append(text)

    # Flush last section.
    if current_heading or current_body:
        body_text = "\n\n".join(current_body)
        if current_heading.lower().strip() in ("abstract", "résumé", "摘要"):
            abstract = body_text
        else:
            sections.append(
                Section(
                    heading=current_heading,
                    content=body_text,
                    level=_heading_level(current_heading),
                )
            )

    # Process references.
    if references_body:
        references_raw = _split_references("\n".join(references_body))

    # If abstract was not captured via heading, try first-page heuristic:
    # look for a block on page 1 starting with "Abstract" inline.
    if not abstract and pages_blocks:
        for b in pages_blocks[0]:
            t = b["text"]
            if re.match(r"(?i)^abstract[\s:.]\s*", t):
                abstract = re.sub(r"(?i)^abstract[\s:.]\s*", "", t).strip()
                break

    full_text = "\n\n".join(full_text_parts)

    doc.close()

    return ParsedPaper(
        title=title,
        abstract=abstract,
        sections=sections,
        references=references_raw,
        quotations=all_quotations,
        full_text=full_text,
        page_count=page_count,
    )
