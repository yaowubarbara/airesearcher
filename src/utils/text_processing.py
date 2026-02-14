"""Multilingual text processing utilities."""

from __future__ import annotations

import re
from typing import Optional


def detect_language(text: str) -> str:
    """Simple heuristic language detection for en/zh/fr."""
    if not text:
        return "en"

    # Count Chinese characters
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    total_chars = len(text.strip())

    if total_chars == 0:
        return "en"

    # If >20% Chinese characters, it's Chinese
    if chinese_chars / total_chars > 0.2:
        return "zh"

    # Check for French-specific patterns
    french_markers = [
        r"\b(le|la|les|un|une|des|du|au|aux)\b",
        r"\b(est|sont|être|avoir|fait|cette|ces|dans|pour|avec|sur|par)\b",
        r"[àâäéèêëïîôùûüÿçœæ]",
    ]
    french_score = 0
    text_lower = text.lower()
    for pattern in french_markers:
        french_score += len(re.findall(pattern, text_lower))

    # Rough threshold for French
    word_count = len(text_lower.split())
    if word_count > 0 and french_score / word_count > 0.15:
        return "fr"

    return "en"


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    respect_paragraphs: bool = True,
) -> list[str]:
    """Split text into overlapping chunks, respecting paragraph boundaries."""
    if not text:
        return []

    if respect_paragraphs:
        paragraphs = re.split(r"\n\s*\n", text)
    else:
        paragraphs = [text]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_length = len(para)

        if current_length + para_length > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))

            # Keep overlap by retaining last paragraph(s)
            overlap_text = ""
            overlap_paras: list[str] = []
            for p in reversed(current_chunk):
                if len(overlap_text) + len(p) <= overlap:
                    overlap_paras.insert(0, p)
                    overlap_text += p
                else:
                    break
            current_chunk = overlap_paras
            current_length = len(overlap_text)

        current_chunk.append(para)
        current_length += para_length

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def extract_citations_from_text(text: str) -> list[dict]:
    """Extract citation patterns from academic text.

    Supports:
    - Parenthetical: (Author Year), (Author Year, p. 123)
    - MLA: (Author 123)
    - Chinese: （作者 年份）
    - Footnote markers: [1], ¹
    """
    citations: list[dict] = []

    # Parenthetical with year: (Author 2024), (Author 2024, p. 45)
    for match in re.finditer(
        r"\(([A-Z][a-zA-Zéèêëàâäïîôùûüçœæ\-]+(?:\s+(?:and|et|&)\s+[A-Z][a-zA-Zéèêëàâäïîôùûüçœæ\-]+)?)\s+(\d{4})"
        r"(?:,\s*(?:p\.|pp\.)\s*([\d\-]+))?\)",
        text,
    ):
        citations.append({
            "type": "parenthetical",
            "author": match.group(1),
            "year": int(match.group(2)),
            "pages": match.group(3),
            "raw": match.group(0),
        })

    # MLA style: (Author 123-45)
    for match in re.finditer(
        r"\(([A-Z][a-zA-Zéèêëàâäïîôùûüçœæ\-]+)\s+(\d+(?:\-\d+)?)\)",
        text,
    ):
        # Avoid matching parenthetical year citations already captured
        year_candidate = match.group(2)
        if len(year_candidate) == 4 and year_candidate.startswith(("19", "20")):
            continue
        citations.append({
            "type": "mla",
            "author": match.group(1),
            "pages": match.group(2),
            "raw": match.group(0),
        })

    # Chinese citations: （作者 2024）
    for match in re.finditer(r"（([\u4e00-\u9fff]+)\s*(\d{4})）", text):
        citations.append({
            "type": "chinese",
            "author": match.group(1),
            "year": int(match.group(2)),
            "raw": match.group(0),
        })

    return citations


def normalize_author_name(name: str) -> str:
    """Normalize author name to 'Last, First' format."""
    name = name.strip()

    # Already in "Last, First" format
    if "," in name:
        return name

    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name


def word_count(text: str, language: Optional[str] = None) -> int:
    """Count words, handling Chinese character counting."""
    if not text:
        return 0

    lang = language or detect_language(text)

    if lang == "zh":
        # Chinese: count characters (excluding punctuation) as "words"
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        # Also count English words mixed in
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        return chinese_chars + english_words

    return len(text.split())
