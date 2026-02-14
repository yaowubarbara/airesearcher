"""Rule-based extraction of style features from paper text.

Used by the JournalStyleLearner to detect formatting conventions before
handing results to the LLM for deeper analysis.
"""

from __future__ import annotations

import re
from typing import Any


class StyleExtractor:
    """Extracts formatting and stylistic features from a paper's plain text."""

    def extract_style_features(self, text: str) -> dict[str, Any]:
        """Analyze *text* and return a dictionary of detected style features.

        Detected features:
        - citation_style: guessed citation style (MLA, Chicago, APA, etc.)
        - footnote_style: footnotes, endnotes, or none
        - heading_patterns: list of detected section headings
        - block_quote_patterns: description of block-quote formatting
        - avg_paragraph_length: average word count per paragraph
        - avg_sentence_length: average word count per sentence
        - passive_voice_ratio: estimated fraction of passive-voice sentences
        """
        features: dict[str, Any] = {}

        features["citation_style"] = self._detect_citation_style(text)
        features["footnote_style"] = self._detect_footnote_style(text)
        features["heading_patterns"] = self._detect_headings(text)
        features["block_quote_patterns"] = self._detect_block_quotes(text)

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        features["avg_paragraph_length"] = self._avg_word_count(paragraphs)

        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s for s in sentences if len(s.split()) > 3]
        features["avg_sentence_length"] = self._avg_word_count(sentences)

        features["passive_voice_ratio"] = self._estimate_passive_ratio(sentences)

        return features

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_citation_style(text: str) -> str:
        """Guess the citation style from in-text citation patterns."""
        # MLA: (Author page) -- no year in parenthetical, has Works Cited
        mla_cites = len(re.findall(r"\([A-Z][a-z]+\s+\d{1,4}\)", text))
        works_cited = bool(re.search(r"Works\s+Cited", text, re.IGNORECASE))

        # APA: (Author, year) or (Author, year, p. X)
        apa_cites = len(re.findall(r"\([A-Z][a-z]+,\s*\d{4}", text))

        # Chicago notes: superscript numbers or footnote markers
        chicago_notes = len(re.findall(r"(?:^|\s)\d+\.\s+[A-Z]", text, re.MULTILINE))
        footnote_markers = len(re.findall(r"\^\d+|\[\d+\]", text))

        # GB/T 7714: [1], [2], etc. in-text with numbered reference list
        gb_cites = len(re.findall(r"\[\d+\]", text))

        scores = {
            "MLA": mla_cites * 2 + (10 if works_cited else 0),
            "APA": apa_cites * 2,
            "Chicago": chicago_notes + footnote_markers * 2,
            "GB/T 7714": gb_cites * 2,
        }

        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return "unknown"
        return best

    @staticmethod
    def _detect_footnote_style(text: str) -> str:
        """Detect whether the paper uses footnotes, endnotes, or neither."""
        # Superscript-style footnote markers
        superscripts = len(re.findall(r"\^\d+", text))
        # Numbered notes at end of document
        endnote_section = bool(re.search(r"\n\s*(Notes|Endnotes)\s*\n", text, re.IGNORECASE))
        # Footnote-style markers at bottom of text blocks
        footnote_markers = len(re.findall(r"^\d+\s+", text, re.MULTILINE))

        if endnote_section:
            return "endnotes"
        elif superscripts > 2 or footnote_markers > 5:
            return "footnotes"
        return "none"

    @staticmethod
    def _detect_headings(text: str) -> list[str]:
        """Extract lines that look like section headings."""
        headings: list[str] = []
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped or len(stripped) > 120:
                continue
            # All-caps headings (e.g. "INTRODUCTION")
            if stripped.isupper() and len(stripped.split()) <= 8:
                headings.append(stripped)
                continue
            # Numbered headings (e.g. "1. Introduction", "I. Background")
            if re.match(r"^(?:\d+\.|[IVXLC]+\.)\s+\S", stripped) and len(stripped.split()) <= 10:
                headings.append(stripped)
                continue
            # Title-case short lines (likely headings)
            words = stripped.split()
            if (
                2 <= len(words) <= 8
                and words[0][0].isupper()
                and not stripped.endswith((".", ",", ";", ":"))
                and stripped == stripped.title()
            ):
                headings.append(stripped)
        return headings

    @staticmethod
    def _detect_block_quotes(text: str) -> str:
        """Describe how block quotes appear to be formatted."""
        # Indented blocks (4+ spaces at line start, multi-line)
        indented = re.findall(r"(?:^[ \t]{4,}.+\n?){2,}", text, re.MULTILINE)
        if indented:
            return "indent"
        # Long inline quotes (>40 words between quotation marks)
        long_quotes = re.findall(r'"([^"]{200,})"', text)
        if long_quotes:
            return "quotation_marks"
        return "unknown"

    # ------------------------------------------------------------------
    # Numeric helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _avg_word_count(segments: list[str]) -> int:
        """Return the average word count across a list of text segments."""
        if not segments:
            return 0
        total = sum(len(s.split()) for s in segments)
        return total // len(segments)

    @staticmethod
    def _estimate_passive_ratio(sentences: list[str]) -> float:
        """Estimate the fraction of sentences using passive voice."""
        if not sentences:
            return 0.0
        passive_re = re.compile(
            r"\b(is|are|was|were|be|been|being)\s+(\w+ed|(\w+en))\b",
            re.IGNORECASE,
        )
        passive_count = sum(1 for s in sentences if passive_re.search(s))
        return round(passive_count / len(sentences), 2)
