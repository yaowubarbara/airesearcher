"""Tests for pre-plan readiness checker."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import Paper, PaperStatus, Language, Reference, ReferenceType
from src.research_planner.readiness_checker import (
    ReadinessItem,
    ReadinessReport,
    check_readiness,
    _check_availability,
    _determine_status,
    _predict_needed_works,
)


# --- Fixtures ---


@pytest.fixture
def db(tmp_path):
    """Create a temporary test database."""
    db = Database(tmp_path / "test.sqlite")
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def mock_vs():
    """Create a mock VectorStore."""
    vs = MagicMock()
    vs.search_papers = MagicMock(return_value={"metadatas": [[]], "documents": [[]]})
    return vs


@pytest.fixture
def mock_llm():
    """Create a mock LLMRouter."""
    llm = MagicMock()
    return llm


def _make_paper(title: str, status: PaperStatus = PaperStatus.INDEXED) -> Paper:
    return Paper(
        title=title,
        authors=["Test Author"],
        journal="Test Journal",
        year=2020,
        status=status,
        language=Language.EN,
    )


def _make_ref(title: str) -> Reference:
    return Reference(
        title=title,
        authors=["Test Author"],
        year=2020,
        ref_type=ReferenceType.THEORY,
    )


# --- ReadinessItem tests ---


class TestReadinessItem:
    def test_basic_fields(self):
        item = ReadinessItem(
            author="Walter Benjamin",
            title="The Task of the Translator",
            category="criticism",
            reason="Essential for translation theory",
        )
        assert item.author == "Walter Benjamin"
        assert item.title == "The Task of the Translator"
        assert item.category == "criticism"
        assert not item.available

    def test_default_available_false(self):
        item = ReadinessItem(author="A", title="B", category="primary")
        assert item.available is False

    def test_available_set(self):
        item = ReadinessItem(author="A", title="B", category="primary", available=True)
        assert item.available is True


# --- ReadinessReport tests ---


class TestReadinessReport:
    def test_empty_report(self):
        report = ReadinessReport(query="test")
        assert report.status == "ready"
        assert report.missing_primary == []
        assert report.missing_criticism == []

    def test_missing_primary(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=False),
            ReadinessItem(author="C", title="D", category="criticism", available=True),
        ]
        report = ReadinessReport(query="test", status="missing_primary", items=items)
        assert len(report.missing_primary) == 1
        assert report.missing_primary[0].title == "B"
        assert report.missing_criticism == []

    def test_missing_criticism(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=True),
            ReadinessItem(author="C", title="D", category="criticism", available=False),
        ]
        report = ReadinessReport(query="test", status="insufficient_criticism", items=items)
        assert report.missing_primary == []
        assert len(report.missing_criticism) == 1

    def test_summary(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=True),
            ReadinessItem(author="C", title="D", category="criticism", available=False),
        ]
        report = ReadinessReport(query="test", status="insufficient_criticism", items=items)
        s = report.summary()
        assert "1/2 works available" in s
        assert "insufficient_criticism" in s


# --- _determine_status tests ---


class TestDetermineStatus:
    def test_all_available(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=True),
            ReadinessItem(author="C", title="D", category="criticism", available=True),
        ]
        assert _determine_status(items) == "ready"

    def test_missing_primary_only(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=False),
            ReadinessItem(author="C", title="D", category="criticism", available=True),
        ]
        assert _determine_status(items) == "missing_primary"

    def test_insufficient_criticism(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=True),
            ReadinessItem(author="C", title="D", category="criticism", available=False),
            ReadinessItem(author="E", title="F", category="criticism", available=False),
            ReadinessItem(author="G", title="H", category="criticism", available=False),
        ]
        assert _determine_status(items) == "insufficient_criticism"

    def test_not_ready(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=False),
            ReadinessItem(author="C", title="D", category="criticism", available=False),
            ReadinessItem(author="E", title="F", category="criticism", available=False),
            ReadinessItem(author="G", title="H", category="criticism", available=False),
            ReadinessItem(author="I", title="J", category="criticism", available=False),
        ]
        assert _determine_status(items) == "not_ready"

    def test_empty_items(self):
        assert _determine_status([]) == "ready"

    def test_no_primary_all_criticism_missing(self):
        items = [
            ReadinessItem(author="C", title="D", category="criticism", available=False),
            ReadinessItem(author="E", title="F", category="criticism", available=False),
        ]
        assert _determine_status(items) == "insufficient_criticism"

    def test_mixed_some_criticism_available(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=True),
            ReadinessItem(author="C", title="D", category="criticism", available=True),
            ReadinessItem(author="E", title="F", category="criticism", available=False),
        ]
        # 50% criticism available, threshold is 0.5 so this is ready
        assert _determine_status(items) == "ready"

    def test_criticism_below_half(self):
        items = [
            ReadinessItem(author="A", title="B", category="primary", available=True),
            ReadinessItem(author="C", title="D", category="criticism", available=False),
            ReadinessItem(author="E", title="F", category="criticism", available=False),
            ReadinessItem(author="G", title="H", category="criticism", available=True),
        ]
        # 1/3 = 0.33 < 0.5 => insufficient_criticism
        # Actually 1 out of 3 = 0.33 which is < 0.5 but wait, there are 3 criticism items
        # available = 1, total = 3, ratio = 0.33 < 0.5
        assert _determine_status(items) == "insufficient_criticism"


# --- _check_availability tests ---


class TestCheckAvailability:
    def test_found_in_db_indexed(self, db, mock_vs):
        """Paper in DB with INDEXED status should be available."""
        paper = _make_paper("Atemwende", PaperStatus.INDEXED)
        db.insert_paper(paper)
        item = ReadinessItem(author="Paul Celan", title="Atemwende", category="primary")
        assert _check_availability(item, db, mock_vs) is True

    def test_found_in_db_analyzed(self, db, mock_vs):
        paper = _make_paper("Die Niemandsrose", PaperStatus.ANALYZED)
        db.insert_paper(paper)
        item = ReadinessItem(author="Paul Celan", title="Die Niemandsrose", category="primary")
        assert _check_availability(item, db, mock_vs) is True

    def test_found_in_db_not_indexed(self, db, mock_vs):
        """Paper in DB but only DISCOVERED should not count."""
        paper = _make_paper("Atemwende", PaperStatus.DISCOVERED)
        db.insert_paper(paper)
        item = ReadinessItem(author="Paul Celan", title="Atemwende", category="primary")
        assert _check_availability(item, db, mock_vs) is False

    def test_not_found(self, db, mock_vs):
        item = ReadinessItem(author="Unknown", title="Nonexistent Book", category="primary")
        assert _check_availability(item, db, mock_vs) is False

    def test_criticism_found_in_references(self, db, mock_vs):
        """Criticism found in references_ table should count."""
        ref = _make_ref("The Task of the Translator")
        db.insert_reference(ref)
        item = ReadinessItem(
            author="Walter Benjamin",
            title="The Task of the Translator",
            category="criticism",
        )
        assert _check_availability(item, db, mock_vs) is True

    def test_primary_not_in_references(self, db, mock_vs):
        """Primary texts should only check papers, not references."""
        ref = _make_ref("Atemwende")
        db.insert_reference(ref)
        item = ReadinessItem(author="Celan", title="Atemwende", category="primary")
        # References exist but no paper is indexed
        assert _check_availability(item, db, mock_vs) is False

    def test_title_extraction(self, db, mock_vs):
        """Author, Title pattern should extract title correctly."""
        paper = _make_paper("Poétique de la Relation", PaperStatus.INDEXED)
        db.insert_paper(paper)
        item = ReadinessItem(
            author="Glissant",
            title="Poétique de la Relation",
            category="primary",
        )
        assert _check_availability(item, db, mock_vs) is True


# --- _predict_needed_works tests ---


class TestPredictNeededWorks:
    @pytest.mark.asyncio
    async def test_valid_response(self, mock_llm):
        """LLM returns valid JSON array."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Benjamin", "title": "The Arcades Project", "category": "criticism", "reason": "key theory"},
            {"author": "Celan", "title": "Atemwende", "category": "primary", "reason": "primary text"},
        ]))

        items = await _predict_needed_works("Paul Celan poetry", [], mock_llm)
        assert len(items) == 2
        assert items[0].author == "Benjamin"
        assert items[0].category == "criticism"
        assert items[1].category == "primary"

    @pytest.mark.asyncio
    async def test_invalid_json(self, mock_llm):
        """LLM returns invalid JSON — should return empty list."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value="Not valid JSON at all")

        items = await _predict_needed_works("test", [], mock_llm)
        assert items == []

    @pytest.mark.asyncio
    async def test_empty_title_skipped(self, mock_llm):
        """Entries with empty title should be skipped."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "A", "title": "", "category": "primary"},
            {"author": "B", "title": "Good Title", "category": "criticism"},
        ]))

        items = await _predict_needed_works("test", [], mock_llm)
        assert len(items) == 1
        assert items[0].title == "Good Title"

    @pytest.mark.asyncio
    async def test_llm_error(self, mock_llm):
        """LLM call fails — should return empty list."""
        mock_llm.complete = MagicMock(side_effect=Exception("API error"))

        items = await _predict_needed_works("test", [], mock_llm)
        assert items == []

    @pytest.mark.asyncio
    async def test_with_available_titles(self, mock_llm):
        """Available titles are included in prompt context."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value="[]")

        await _predict_needed_works("test", ["Title A", "Title B"], mock_llm)
        call_args = mock_llm.complete.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Title A" in prompt
        assert "Title B" in prompt

    @pytest.mark.asyncio
    async def test_json_in_markdown_fences(self, mock_llm):
        """LLM wraps JSON in markdown code fences."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value='```json\n[{"author": "A", "title": "B", "category": "primary"}]\n```')

        items = await _predict_needed_works("test", [], mock_llm)
        assert len(items) == 1


# --- check_readiness integration tests ---


class TestCheckReadiness:
    @pytest.mark.asyncio
    async def test_empty_prediction(self, db, mock_vs, mock_llm):
        """LLM predicts no works — should return ready."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value="[]")

        report = await check_readiness("test topic", db, mock_vs, mock_llm)
        assert report.status == "ready"
        assert report.items == []

    @pytest.mark.asyncio
    async def test_all_available(self, db, mock_vs, mock_llm):
        """All predicted works are available."""
        paper = _make_paper("Atemwende", PaperStatus.INDEXED)
        db.insert_paper(paper)

        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Celan", "title": "Atemwende", "category": "primary", "reason": "primary text"},
        ]))

        report = await check_readiness("Celan", db, mock_vs, mock_llm)
        assert report.status == "ready"
        assert report.items[0].available is True

    @pytest.mark.asyncio
    async def test_missing_primary(self, db, mock_vs, mock_llm):
        """Missing primary text detected, criticism available."""
        # Insert a reference matching the criticism so it counts as available
        ref = _make_ref("Some Criticism")
        db.insert_reference(ref)

        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Celan", "title": "Atemwende", "category": "primary", "reason": "primary text"},
            {"author": "A", "title": "Some Criticism", "category": "criticism", "reason": "key work"},
        ]))

        report = await check_readiness("Celan", db, mock_vs, mock_llm)
        assert report.status == "missing_primary"
        assert len(report.missing_primary) == 1

    @pytest.mark.asyncio
    async def test_with_session_paper_ids(self, db, mock_vs, mock_llm):
        """Session paper IDs are used for context."""
        paper = _make_paper("Test Paper", PaperStatus.INDEXED)
        pid = db.insert_paper(paper)

        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value="[]")

        report = await check_readiness("test", db, mock_vs, mock_llm, session_paper_ids=[pid])
        assert report.status == "ready"
        # Verify the LLM was called with paper titles in context
        call_args = mock_llm.complete.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Test Paper" in prompt
