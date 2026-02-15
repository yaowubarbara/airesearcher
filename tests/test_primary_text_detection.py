"""Tests for primary text missing detection (corpus principal analysis)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    MissingPrimaryText,
    OutlineSection,
    Paper,
    PaperStatus,
    PrimaryTextReport,
    ResearchPlan,
)
from src.research_planner.planner import (
    _extract_title,
    _jaccard_word_overlap,
    detect_missing_primary_texts,
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


def _make_plan(sections: list[OutlineSection]) -> ResearchPlan:
    """Helper to create a ResearchPlan with given sections."""
    return ResearchPlan(
        topic_id="topic-1",
        thesis_statement="Test thesis",
        target_journal="Comparative Literature",
        outline=sections,
        reference_ids=[],
    )


# --- _extract_title tests ---


class TestExtractTitle:
    """Tests for _extract_title() parsing of primary_texts entries."""

    def test_author_comma_title(self):
        assert _extract_title("Paul Celan, Atemwende") == "Atemwende"

    def test_author_comma_title_with_year(self):
        assert _extract_title("Glissant, Poétique de la Relation (1990)") == "Poétique de la Relation"

    def test_author_comma_quoted_title_with_collection(self):
        assert _extract_title("Celan, 'Psalm' (Die Niemandsrose, 1963)") == "Psalm"

    def test_author_comma_double_quoted_title(self):
        assert _extract_title('Celan, "Todesfuge"') == "Todesfuge"

    def test_title_only_no_comma(self):
        assert _extract_title("Atemwende") == "Atemwende"

    def test_chinese_author_title(self):
        assert _extract_title("Can Xue, 黄泥街") == "黄泥街"

    def test_title_with_asterisk_italic(self):
        assert _extract_title("Celan, *Die Niemandsrose*") == "Die Niemandsrose"

    def test_empty_string(self):
        assert _extract_title("") == ""

    def test_whitespace_only(self):
        assert _extract_title("   ") == ""

    def test_author_comma_title_with_year_no_spaces(self):
        assert _extract_title("Derrida, Sovereignties in Question(2005)") == "Sovereignties in Question"

    def test_smart_quotes(self):
        result = _extract_title("Celan, \u2018Psalm\u2019")
        assert result == "Psalm"

    def test_multiple_commas_takes_first(self):
        """Author, Title with, extra comma -> title is everything after first comma."""
        result = _extract_title("Derrida, Writing and Difference, vol. 1")
        # After first comma: "Writing and Difference, vol. 1"
        # No trailing paren to strip, so result includes the second comma part
        assert "Writing and Difference" in result


# --- _jaccard_word_overlap tests ---


class TestJaccardWordOverlap:
    def test_identical(self):
        assert _jaccard_word_overlap("hello world", "hello world") == 1.0

    def test_no_overlap(self):
        assert _jaccard_word_overlap("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        score = _jaccard_word_overlap("the great gatsby", "gatsby the novel")
        # intersection: {the, gatsby} = 2, union: {the, great, gatsby, novel} = 4
        assert abs(score - 0.5) < 0.01

    def test_empty_string(self):
        assert _jaccard_word_overlap("", "hello") == 0.0

    def test_case_insensitive(self):
        assert _jaccard_word_overlap("Hello World", "hello world") == 1.0


# --- PrimaryTextReport model tests ---


class TestPrimaryTextReport:
    def test_empty_report(self):
        report = PrimaryTextReport(total_unique=0)
        assert report.all_available
        assert report.summary() == "No primary texts listed in the outline."

    def test_all_available(self):
        report = PrimaryTextReport(
            total_unique=3,
            available=["A", "B", "C"],
            missing=[],
        )
        assert report.all_available
        assert "All 3" in report.summary()

    def test_some_missing(self):
        report = PrimaryTextReport(
            total_unique=3,
            available=["A"],
            missing=[
                MissingPrimaryText(text_name="B", sections_needing=["Sec 1"]),
                MissingPrimaryText(text_name="C", sections_needing=["Sec 2"]),
            ],
        )
        assert not report.all_available
        assert "2/3" in report.summary()
        assert "NOT indexed" in report.summary()

    def test_all_missing(self):
        report = PrimaryTextReport(
            total_unique=2,
            missing=[
                MissingPrimaryText(text_name="X", sections_needing=["Sec 1"]),
                MissingPrimaryText(text_name="Y", sections_needing=["Sec 2"]),
            ],
        )
        assert not report.all_available
        assert "2/2" in report.summary()


# --- MissingPrimaryText model tests ---


class TestMissingPrimaryText:
    def test_basic_fields(self):
        m = MissingPrimaryText(
            text_name="Celan, Atemwende",
            sections_needing=["Sec 1", "Sec 3"],
            passages_needed=["poems 1-7", "final stanza"],
            purpose="Close reading of breath imagery",
        )
        assert m.text_name == "Celan, Atemwende"
        assert len(m.sections_needing) == 2
        assert len(m.passages_needed) == 2
        assert "breath imagery" in m.purpose

    def test_default_fields(self):
        m = MissingPrimaryText(text_name="Test")
        assert m.sections_needing == []
        assert m.passages_needed == []
        assert m.purpose == ""


# --- detect_missing_primary_texts tests ---


class TestDetectMissingPrimaryTexts:
    def test_empty_outline(self, db, mock_vs):
        plan = _make_plan([])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert report.total_unique == 0
        assert report.all_available

    def test_no_primary_texts_in_sections(self, db, mock_vs):
        plan = _make_plan([
            OutlineSection(title="Intro", argument="Introduction", primary_texts=[]),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert report.total_unique == 0

    def test_all_found_via_sqlite(self, db, mock_vs):
        """When all primary texts are found as INDEXED papers in SQLite."""
        # Insert indexed papers
        db.insert_paper(Paper(
            title="Atemwende by Paul Celan",
            journal="collected works",
            year=1967,
            status=PaperStatus.INDEXED,
        ))

        plan = _make_plan([
            OutlineSection(
                title="Celan's Poetics",
                argument="Analysis of breath imagery",
                primary_texts=["Celan, Atemwende"],
            ),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert report.total_unique == 1
        assert len(report.available) == 1
        assert len(report.missing) == 0

    def test_missing_not_in_db(self, db, mock_vs):
        """When a primary text has no matching paper in the DB at all."""
        plan = _make_plan([
            OutlineSection(
                title="Sec 1",
                argument="Analysis of X",
                primary_texts=["Author, Some Unknown Book"],
                passages_to_analyze=["Chapter 3 opening"],
            ),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert report.total_unique == 1
        assert len(report.missing) == 1
        assert report.missing[0].text_name == "Author, Some Unknown Book"
        assert "Chapter 3 opening" in report.missing[0].passages_needed

    def test_paper_exists_but_not_indexed(self, db, mock_vs):
        """Paper found by title search but status is DISCOVERED, not INDEXED."""
        db.insert_paper(Paper(
            title="Poétique de la Relation",
            journal="Gallimard",
            year=1990,
            status=PaperStatus.DISCOVERED,
        ))

        plan = _make_plan([
            OutlineSection(
                title="Glissant",
                argument="Opacity concept",
                primary_texts=["Glissant, Poétique de la Relation (1990)"],
            ),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert len(report.missing) == 1
        assert "Poétique de la Relation" in report.missing[0].text_name

    def test_dedup_across_sections(self, db, mock_vs):
        """Same primary text in multiple sections should be counted once."""
        plan = _make_plan([
            OutlineSection(
                title="Sec 1",
                argument="First analysis",
                primary_texts=["Celan, Atemwende"],
                passages_to_analyze=["poems 1-3"],
            ),
            OutlineSection(
                title="Sec 2",
                argument="Second analysis",
                primary_texts=["Celan, Atemwende"],
                passages_to_analyze=["poems 4-7"],
            ),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert report.total_unique == 1
        assert len(report.missing) == 1
        m = report.missing[0]
        assert "Sec 1" in m.sections_needing
        assert "Sec 2" in m.sections_needing
        assert "poems 1-3" in m.passages_needed
        assert "poems 4-7" in m.passages_needed

    def test_mixed_found_and_missing(self, db, mock_vs):
        """Some texts found, some missing."""
        db.insert_paper(Paper(
            title="Die Niemandsrose",
            journal="collected",
            year=1963,
            status=PaperStatus.INDEXED,
        ))

        plan = _make_plan([
            OutlineSection(
                title="Sec 1",
                argument="A",
                primary_texts=["Celan, Die Niemandsrose"],
            ),
            OutlineSection(
                title="Sec 2",
                argument="B",
                primary_texts=["Glissant, Tout-Monde"],
            ),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert report.total_unique == 2
        assert len(report.available) == 1
        assert len(report.missing) == 1
        assert report.missing[0].text_name == "Glissant, Tout-Monde"

    def test_purpose_from_argument(self, db, mock_vs):
        """Purpose field should come from the section argument."""
        plan = _make_plan([
            OutlineSection(
                title="Sec 1",
                argument="Close reading of breath metaphors in late Celan",
                primary_texts=["Celan, Atemwende"],
            ),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert len(report.missing) == 1
        assert "breath metaphors" in report.missing[0].purpose

    def test_empty_primary_text_string_skipped(self, db, mock_vs):
        """Empty strings in primary_texts should be ignored."""
        plan = _make_plan([
            OutlineSection(
                title="Sec 1",
                argument="A",
                primary_texts=["", "  ", "Celan, Atemwende"],
            ),
        ])
        report = detect_missing_primary_texts(plan, db, mock_vs)
        assert report.total_unique == 1


# --- search_papers_by_title DB method tests ---


class TestSearchPapersByTitle:
    def test_finds_substring_match(self, db):
        db.insert_paper(Paper(
            title="The Collected Poems of Paul Celan",
            journal="test",
            year=2000,
        ))
        results = db.search_papers_by_title("Paul Celan")
        assert len(results) == 1
        assert "Paul Celan" in results[0].title

    def test_case_insensitive(self, db):
        db.insert_paper(Paper(
            title="Atemwende",
            journal="test",
            year=1967,
        ))
        results = db.search_papers_by_title("atemwende")
        assert len(results) == 1

    def test_no_match(self, db):
        db.insert_paper(Paper(
            title="Unrelated Paper",
            journal="test",
            year=2020,
        ))
        results = db.search_papers_by_title("Atemwende")
        assert len(results) == 0

    def test_limit_parameter(self, db):
        for i in range(10):
            db.insert_paper(Paper(
                id=f"paper-{i}",
                title=f"Test Paper {i}",
                journal="test",
                year=2020,
                doi=f"10.1234/test{i}",
            ))
        results = db.search_papers_by_title("Test Paper", limit=3)
        assert len(results) == 3
