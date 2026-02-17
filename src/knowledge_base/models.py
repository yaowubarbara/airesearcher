"""Data models for the knowledge base."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Language(str, enum.Enum):
    EN = "en"
    ZH = "zh"
    FR = "fr"


class PaperStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    METADATA_ONLY = "metadata_only"
    PDF_DOWNLOADED = "pdf_downloaded"
    INDEXED = "indexed"
    ANALYZED = "analyzed"


class ReferenceType(str, enum.Enum):
    """Classification of a reference's role in a scholarly argument."""

    PRIMARY_LITERARY = "primary_literary"
    SECONDARY_CRITICISM = "secondary_criticism"
    THEORY = "theory"
    METHODOLOGY = "methodology"
    HISTORICAL_CONTEXT = "historical_context"
    REFERENCE_WORK = "reference_work"
    SELF_CITATION = "self_citation"
    UNCLASSIFIED = "unclassified"


class AnnotationScale(str, enum.Enum):
    """Scale at which a paper's problematic operates."""

    TEXTUAL = "textual"
    PERCEPTUAL = "perceptual"
    MEDIATIONAL = "mediational"
    INSTITUTIONAL = "institutional"
    METHODOLOGICAL = "methodological"


class AnnotationGap(str, enum.Enum):
    """Type of gap identified in a paper's problematic."""

    MEDIATIONAL_GAP = "mediational_gap"
    TEMPORAL_FLATTENING = "temporal_flattening"
    METHOD_NATURALIZATION = "method_naturalization"
    SCALE_MISMATCH = "scale_mismatch"
    INCOMMENSURABILITY_BLINDSPOT = "incommensurability_blindspot"


class Paper(BaseModel):
    """A scholarly paper tracked by the system."""

    id: Optional[str] = None
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    journal: str
    year: int
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    openalex_id: Optional[str] = None
    language: Language = Language.EN
    keywords: list[str] = Field(default_factory=list)
    status: PaperStatus = PaperStatus.DISCOVERED
    pdf_path: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Reference(BaseModel):
    """A verified bibliographic reference."""

    id: Optional[str] = None
    paper_id: Optional[str] = None  # which paper this ref was extracted from
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    publisher: Optional[str] = None
    ref_type: ReferenceType = ReferenceType.UNCLASSIFIED
    verified: bool = False
    verification_source: Optional[str] = None  # crossref, semantic_scholar, openalex
    formatted_mla: Optional[str] = None
    formatted_chicago: Optional[str] = None
    formatted_gb: Optional[str] = None  # GB/T 7714 for Chinese journals


class Quotation(BaseModel):
    """An extracted quotation from a primary or secondary text."""

    id: Optional[str] = None
    paper_id: str
    text: str
    page: Optional[str] = None
    context: Optional[str] = None  # surrounding text for context
    language: Language = Language.EN
    is_primary_text: bool = False  # True if from a literary work being analyzed


class PaperAnnotation(BaseModel):
    """P-ontology annotation for a paper: P = <T, M, S, G>."""

    id: Optional[str] = None
    paper_id: str
    tensions: list[str] = Field(default_factory=list)  # 1-2 items, "A <-> B"
    mediators: list[str] = Field(default_factory=list)  # 1-2 mechanisms
    scale: AnnotationScale = AnnotationScale.TEXTUAL
    gap: AnnotationGap = AnnotationGap.MEDIATIONAL_GAP
    evidence: str = ""
    deobjectification: str = ""
    created_at: Optional[datetime] = None


class ProblematiqueDirection(BaseModel):
    """A cluster of annotations forming a broad research direction."""

    id: Optional[str] = None
    title: str
    description: str
    dominant_tensions: list[str] = Field(default_factory=list)
    dominant_mediators: list[str] = Field(default_factory=list)
    dominant_scale: Optional[str] = None
    dominant_gap: Optional[str] = None
    paper_ids: list[str] = Field(default_factory=list)
    topic_ids: list[str] = Field(default_factory=list)
    recency_score: float = 0.0
    created_at: Optional[datetime] = None


class TopicProposal(BaseModel):
    """A proposed research topic with gap analysis."""

    id: Optional[str] = None
    title: str
    research_question: str
    gap_description: str
    evidence_paper_ids: list[str] = Field(default_factory=list)
    target_journals: list[str] = Field(default_factory=list)
    novelty_score: float = 0.0
    feasibility_score: float = 0.0
    journal_fit_score: float = 0.0
    timeliness_score: float = 0.0
    overall_score: float = 0.0
    direction_id: Optional[str] = None
    status: str = "proposed"  # proposed, approved, in_progress, completed
    created_at: Optional[datetime] = None


class ResearchPlan(BaseModel):
    """A detailed plan for a research paper."""

    id: Optional[str] = None
    topic_id: str
    thesis_statement: str
    target_journal: str
    target_language: Language = Language.EN
    outline: list[OutlineSection] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    status: str = "draft"  # draft, approved, writing, completed
    created_at: Optional[datetime] = None


class OutlineSection(BaseModel):
    """A section in a research paper outline."""

    title: str
    argument: str
    primary_texts: list[str] = Field(default_factory=list)
    passages_to_analyze: list[str] = Field(default_factory=list)
    secondary_sources: list[str] = Field(default_factory=list)
    estimated_words: int = 0
    missing_references: list[str] = Field(default_factory=list)


class MissingPrimaryText(BaseModel):
    """A primary literary text required by the outline but not indexed."""

    text_name: str  # e.g. "Paul Celan, Atemwende"
    sections_needing: list[str] = Field(default_factory=list)  # section titles that need it
    passages_needed: list[str] = Field(default_factory=list)  # specific passages requested
    purpose: str = ""  # from section argument, truncated


class PrimaryTextReport(BaseModel):
    """Report on primary text availability for a research plan."""

    total_unique: int = 0
    available: list[str] = Field(default_factory=list)
    missing: list[MissingPrimaryText] = Field(default_factory=list)

    @property
    def all_available(self) -> bool:
        return len(self.missing) == 0

    def summary(self) -> str:
        if self.total_unique == 0:
            return "No primary texts listed in the outline."
        if self.all_available:
            return f"All {self.total_unique} primary texts are indexed."
        n_missing = len(self.missing)
        return (
            f"{n_missing}/{self.total_unique} primary texts are NOT indexed "
            f"in the knowledge base."
        )


class Manuscript(BaseModel):
    """A manuscript in progress or completed."""

    id: Optional[str] = None
    plan_id: str
    title: str
    target_journal: str
    language: Language = Language.EN
    sections: dict[str, str] = Field(default_factory=dict)  # section_name -> content
    full_text: Optional[str] = None
    abstract: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    word_count: int = 0
    version: int = 1
    status: str = "drafting"  # drafting, self_review, human_review, revision, final
    review_scores: dict[str, float] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ReflexionEntry(BaseModel):
    """A reflexion memory entry for learning from past experience."""

    id: Optional[str] = None
    category: str  # writing_pattern, user_preference, reviewer_feedback
    observation: str
    source: str  # e.g., "self_review_v3", "user_edit", "reviewer_feedback"
    manuscript_id: Optional[str] = None
    created_at: Optional[datetime] = None


class JournalProfile(BaseModel):
    """Metadata about a target journal."""

    id: Optional[str] = None
    name: str
    issn: Optional[str] = None
    publisher: Optional[str] = None
    language: Language = Language.EN
    citation_style: str = "MLA"
    url: Optional[str] = None
    scope: Optional[str] = None
    avg_review_time_days: Optional[int] = None


class LLMUsageRecord(BaseModel):
    """Record of an LLM API call for cost tracking."""

    id: Optional[str] = None
    model: str
    task_type: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    success: bool = True
    created_at: Optional[datetime] = None
