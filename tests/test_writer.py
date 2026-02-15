"""Tests for the writing agent and text processing utilities."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge_base.models import (
    Language,
    Manuscript,
    OutlineSection,
    ResearchPlan,
)
from src.utils.text_processing import (
    chunk_text,
    detect_language,
    extract_citations_from_text,
    normalize_author_name,
    word_count,
)
from src.writing_agent.writer import WritingAgent


class TestLanguageDetection:
    def test_detect_english(self):
        text = "This is a paper about comparative literature and world literature theory."
        assert detect_language(text) == "en"

    def test_detect_chinese(self):
        text = "本文探讨了比较文学中的翻译问题，分析了中西文学交流的历史。"
        assert detect_language(text) == "zh"

    def test_detect_french(self):
        text = "Cette étude analyse les rapports entre la littérature comparée et la traduction dans le contexte francophone."
        assert detect_language(text) == "fr"

    def test_detect_empty(self):
        assert detect_language("") == "en"


class TestChunking:
    def test_basic_chunking(self):
        text = "Paragraph one about literature.\n\nParagraph two about theory.\n\nParagraph three about comparison."
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        assert len(chunks) >= 1
        assert all(len(c) > 0 for c in chunks)

    def test_empty_text(self):
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        text = "A short paragraph."
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1

    def test_overlap_preserved(self):
        paras = [f"Paragraph {i} with some content about literature." for i in range(10)]
        text = "\n\n".join(paras)
        chunks = chunk_text(text, chunk_size=100, overlap=50)
        assert len(chunks) > 1


class TestCitationExtraction:
    def test_parenthetical_citation(self):
        text = "As Moretti argues (Moretti 2000), world literature is..."
        cites = extract_citations_from_text(text)
        assert len(cites) >= 1
        assert cites[0]["author"] == "Moretti"
        assert cites[0]["year"] == 2000

    def test_citation_with_page(self):
        text = "The concept of world literature (Damrosch 2003, p. 45) has..."
        cites = extract_citations_from_text(text)
        assert len(cites) >= 1
        assert cites[0]["pages"] == "45"

    def test_chinese_citation(self):
        text = "在比较诗学的视野下（张隆溪 2006），中西文学的关系..."
        cites = extract_citations_from_text(text)
        assert len(cites) >= 1
        assert cites[0]["type"] == "chinese"
        assert cites[0]["year"] == 2006

    def test_no_citations(self):
        text = "A simple sentence without any citations."
        cites = extract_citations_from_text(text)
        assert len(cites) == 0


class TestAuthorNormalization:
    def test_first_last_to_last_first(self):
        assert normalize_author_name("Franco Moretti") == "Moretti, Franco"

    def test_already_last_first(self):
        assert normalize_author_name("Moretti, Franco") == "Moretti, Franco"

    def test_single_name(self):
        assert normalize_author_name("Voltaire") == "Voltaire"

    def test_multiple_names(self):
        assert normalize_author_name("Gayatri Chakravorty Spivak") == "Spivak, Gayatri Chakravorty"


class TestWordCount:
    def test_english_word_count(self):
        text = "This is a test sentence with eight words total."
        # "total." counts as one word
        assert word_count(text) == 9

    def test_chinese_word_count(self):
        text = "这是一个测试句子"
        count = word_count(text, language="zh")
        assert count == 8  # 8 Chinese characters

    def test_empty_text(self):
        assert word_count("") == 0

    def test_mixed_chinese_english(self):
        text = "比较文学 comparative literature 研究"
        count = word_count(text, language="zh")
        assert count > 0  # Should count both Chinese chars and English words


# ------------------------------------------------------------------ #
#  Helpers for WritingAgent revision tests
# ------------------------------------------------------------------ #

def _make_plan(num_sections: int = 2) -> ResearchPlan:
    """Create a minimal ResearchPlan for testing."""
    sections = [
        OutlineSection(
            title=f"Section {i}",
            argument=f"Argument for section {i}",
            primary_texts=[],
            secondary_sources=[],
            passages_to_analyze=[],
            estimated_words=500,
        )
        for i in range(1, num_sections + 1)
    ]
    return ResearchPlan(
        id="plan-001",
        topic_id="topic-001",
        thesis_statement="Test thesis",
        target_journal="Comparative Literature",
        target_language=Language.EN,
        outline=sections,
        reference_ids=["ref1", "ref2"],
    )


def _make_manuscript(plan: ResearchPlan, version: int = 1) -> Manuscript:
    """Create a Manuscript matching the plan's outline."""
    sections = {s.title: f"Draft text for {s.title}." for s in plan.outline}
    full_text = "\n\n".join(f"## {t}\n\n{c}" for t, c in sections.items())
    return Manuscript(
        id="ms-001",
        plan_id=plan.id or "",
        title=plan.thesis_statement,
        target_journal=plan.target_journal,
        language=plan.target_language,
        sections=sections,
        full_text=full_text,
        abstract="Old abstract.",
        reference_ids=plan.reference_ids,
        word_count=len(full_text.split()),
        version=version,
        status="drafting",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _make_review_result() -> dict:
    return {
        "scores": {"close_reading_depth": 2, "argument_logic": 4, "citation_density": 3},
        "revision_instructions": [
            "Expand close reading in Section 1",
            "Vary citation verbs throughout",
        ],
        "comments": ["The argument in Section 2 lacks evidence."],
    }


def _build_writer() -> tuple[WritingAgent, MagicMock, MagicMock, MagicMock]:
    """Build a WritingAgent with mocked dependencies."""
    db = MagicMock()
    db.conn.execute.return_value.fetchall.return_value = []  # no reflexion memories
    vs = MagicMock()
    llm = MagicMock()
    llm.complete.return_value = {"choices": [{"message": {"content": "Revised text."}}]}
    llm.get_response_text.return_value = "Revised text."
    writer = WritingAgent(db, vs, llm)
    return writer, db, vs, llm


class TestReviseManuscript:
    """Tests for WritingAgent.revise_manuscript()."""

    @pytest.mark.asyncio
    async def test_revise_calls_revise_draft_per_section(self):
        """_revise_draft should be called once for each section in the plan."""
        writer, db, vs, llm = _build_writer()
        plan = _make_plan(num_sections=3)
        ms = _make_manuscript(plan)
        review = _make_review_result()

        with patch.object(writer, "_revise_draft", new_callable=AsyncMock, return_value="Revised.") as mock_revise, \
             patch.object(writer, "_generate_abstract", new_callable=AsyncMock, return_value="New abstract."):
            result = await writer.revise_manuscript(plan, ms, review)

        assert mock_revise.call_count == 3
        # Each call should receive the section's current text and the feedback block
        for call_args in mock_revise.call_args_list:
            _, kwargs = call_args
            assert isinstance(kwargs["draft"], str)
            assert "REVIEWER SCORES" in kwargs["revision_instructions"] or \
                   "REVISION INSTRUCTIONS" in kwargs["revision_instructions"]

    @pytest.mark.asyncio
    async def test_revise_increments_version(self):
        """The returned Manuscript should have version = old version + 1."""
        writer, db, vs, llm = _build_writer()
        plan = _make_plan()
        ms = _make_manuscript(plan, version=2)
        review = _make_review_result()

        with patch.object(writer, "_revise_draft", new_callable=AsyncMock, return_value="Revised."), \
             patch.object(writer, "_generate_abstract", new_callable=AsyncMock, return_value="Abstract."):
            result = await writer.revise_manuscript(plan, ms, review)

        assert result.version == 3
        assert result.status == "revision"
        assert result.created_at == ms.created_at  # preserves original creation time

    @pytest.mark.asyncio
    async def test_revise_formats_feedback_into_instructions(self):
        """The feedback block passed to _revise_draft should contain scores, instructions, and comments."""
        writer, db, vs, llm = _build_writer()
        plan = _make_plan(num_sections=1)
        ms = _make_manuscript(plan)
        review = _make_review_result()

        captured_instructions: list[str] = []

        async def capture_revise(*, draft, revision_instructions, section, plan, reflexion_memories):
            captured_instructions.append(revision_instructions)
            return "Revised."

        with patch.object(writer, "_revise_draft", side_effect=capture_revise), \
             patch.object(writer, "_generate_abstract", new_callable=AsyncMock, return_value="Abstract."):
            await writer.revise_manuscript(plan, ms, review)

        assert len(captured_instructions) == 1
        block = captured_instructions[0]
        assert "close_reading_depth=2" in block
        assert "Expand close reading in Section 1" in block
        assert "The argument in Section 2 lacks evidence." in block


class TestFormatReviewFeedback:
    """Tests for WritingAgent._format_review_feedback()."""

    def test_formats_all_fields(self):
        review = _make_review_result()
        block = WritingAgent._format_review_feedback(review)
        assert "REVIEWER SCORES:" in block
        assert "REVISION INSTRUCTIONS" in block
        assert "REVIEWER COMMENTS:" in block

    def test_handles_string_instructions(self):
        review = {
            "scores": {},
            "revision_instructions": "Fix everything.",
            "comments": [],
        }
        block = WritingAgent._format_review_feedback(review)
        assert "Fix everything." in block

    def test_handles_empty_review(self):
        block = WritingAgent._format_review_feedback({})
        assert block == ""
