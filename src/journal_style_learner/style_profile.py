"""Pydantic model for a learned journal style profile.

Matches the YAML schema used for persisting profiles under
``config/journal_profiles/{journal_name}.yaml``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ReferenceExample(BaseModel):
    """An example reference in the journal's preferred format."""

    type: str = ""  # e.g. "book", "article", "chapter"
    example: str = ""


class FormattingProfile(BaseModel):
    """Formatting and citation conventions for a journal."""

    citation_style: str = "MLA"  # MLA, Chicago, APA, GB/T 7714, etc.
    citation_method: str = "parenthetical"  # parenthetical, footnote, endnote
    bibliography: str = "Works Cited"  # section header name
    abstract: str = "required"  # required, optional, none
    word_limit: Optional[int] = None
    block_quote: str = "indent"  # indent, quotation_marks, both
    footnotes: str = "endnotes"  # footnotes, endnotes, none
    reference_examples: list[ReferenceExample] = Field(default_factory=list)
    writing_conventions: list[str] = Field(default_factory=list)


class JournalInfo(BaseModel):
    """Basic journal metadata."""

    name: str
    issn: Optional[str] = None
    publisher: Optional[str] = None
    language: str = "en"
    scope: Optional[str] = None
    url: Optional[str] = None


class LearnedPatterns(BaseModel):
    """Patterns extracted from sample papers via the style learner."""

    avg_paragraph_length: Optional[int] = None
    avg_sentence_length: Optional[int] = None
    passive_voice_ratio: Optional[float] = None
    common_section_headings: list[str] = Field(default_factory=list)
    typical_argument_structures: list[str] = Field(default_factory=list)
    frequent_theoretical_frameworks: list[str] = Field(default_factory=list)
    hedging_frequency: Optional[str] = None  # low, medium, high
    notes: list[str] = Field(default_factory=list)


class StyleProfile(BaseModel):
    """Complete journal style profile persisted as YAML."""

    journal_info: JournalInfo
    formatting: FormattingProfile = Field(default_factory=FormattingProfile)
    learned_patterns: LearnedPatterns = Field(default_factory=LearnedPatterns)
