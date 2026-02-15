"""Tests for Phase 10.1 (citation profiles) and Phase 10.2 (reference type system)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from src.knowledge_base.db import Database
from src.knowledge_base.models import Reference, ReferenceType
from src.research_planner.reference_selector import (
    ReferenceSelector,
    _parse_ref_type,
    load_citation_profile,
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
def citation_profile():
    """Load the comparative literature citation profile."""
    return load_citation_profile("Comparative Literature")


@pytest.fixture
def mock_llm():
    """Mock LLM router for classification tests."""
    router = MagicMock()
    router.get_response_text = MagicMock(side_effect=lambda r: r)
    return router


@pytest.fixture
def selector(db, mock_llm):
    """Create a ReferenceSelector with mocked dependencies."""
    vs = MagicMock()
    return ReferenceSelector(db=db, vector_store=vs, llm_router=mock_llm)


# --- Phase 10.1: Citation Profile Tests ---


class TestCitationProfile:
    def test_profile_file_exists(self):
        path = Path("config/citation_profiles/comparative_literature.yaml")
        assert path.exists(), "Citation profile YAML not found"

    def test_profile_loads_valid_yaml(self, citation_profile):
        assert citation_profile is not None
        assert isinstance(citation_profile, dict)

    def test_profile_has_journal_name(self, citation_profile):
        assert citation_profile["journal"] == "Comparative Literature"

    def test_profile_has_reference_type_distribution(self, citation_profile):
        dist = citation_profile["reference_type_distribution"]
        expected_types = [
            "primary_literary",
            "secondary_criticism",
            "theory",
            "methodology",
            "historical_context",
            "reference_work",
            "self_citation",
        ]
        for t in expected_types:
            assert t in dist, f"Missing type: {t}"
            assert "target_pct" in dist[t]
            assert len(dist[t]["target_pct"]) == 2
            low, high = dist[t]["target_pct"]
            assert 0 <= low <= high <= 100

    def test_profile_has_bibliography_targets(self, citation_profile):
        bib = citation_profile["bibliography"]
        assert "target_entries" in bib
        low, high = bib["target_entries"]
        assert low > 0 and high > low

    def test_profile_has_citation_density(self, citation_profile):
        density = citation_profile["citation_density"]
        assert "avg_citations_per_page" in density
        low, high = density["avg_citations_per_page"]
        assert low > 0 and high > low

    def test_profile_has_quotation_patterns(self, citation_profile):
        assert "quotation" in citation_profile
        q = citation_profile["quotation"]
        assert "what_to_quote" in q
        assert "block_quotes" in q

    def test_profile_has_multilingual_section(self, citation_profile):
        ml = citation_profile["multilingual"]
        assert ml["minimum_languages"] >= 2

    def test_profile_has_footnote_conventions(self, citation_profile):
        fn = citation_profile["footnotes"]
        assert "target_count" in fn
        low, high = fn["target_count"]
        assert low > 0 and high > low

    def test_profile_has_selection_principles(self, citation_profile):
        principles = citation_profile["selection_principles"]
        assert isinstance(principles, list)
        assert len(principles) >= 5
        names = [p["name"] for p in principles]
        assert "deep_engagement_over_breadth" in names
        assert "primary_text_privilege" in names
        assert "multilingual_competence" in names

    def test_profile_target_pcts_sum_reasonable(self, citation_profile):
        """Target ranges should not sum to an impossibly low or high total."""
        dist = citation_profile["reference_type_distribution"]
        min_sum = sum(d["target_pct"][0] for d in dist.values())
        max_sum = sum(d["target_pct"][1] for d in dist.values())
        # The minimums should allow room (not exceed 100) and maximums should
        # cover at least 50% (otherwise targets are too restrictive)
        assert min_sum <= 100, f"Minimum target sum {min_sum}% exceeds 100%"
        assert max_sum >= 50, f"Maximum target sum {max_sum}% seems too restrictive"

    def test_load_nonexistent_profile_returns_none(self):
        result = load_citation_profile("Nonexistent Journal 12345")
        assert result is None


# --- Phase 10.2a: ReferenceType Enum Tests ---


class TestReferenceType:
    def test_enum_values(self):
        assert ReferenceType.PRIMARY_LITERARY.value == "primary_literary"
        assert ReferenceType.SECONDARY_CRITICISM.value == "secondary_criticism"
        assert ReferenceType.THEORY.value == "theory"
        assert ReferenceType.METHODOLOGY.value == "methodology"
        assert ReferenceType.HISTORICAL_CONTEXT.value == "historical_context"
        assert ReferenceType.REFERENCE_WORK.value == "reference_work"
        assert ReferenceType.SELF_CITATION.value == "self_citation"
        assert ReferenceType.UNCLASSIFIED.value == "unclassified"

    def test_reference_model_default_type(self):
        ref = Reference(title="Test", year=2020)
        assert ref.ref_type == ReferenceType.UNCLASSIFIED

    def test_reference_model_with_type(self):
        ref = Reference(
            title="Test",
            year=2020,
            ref_type=ReferenceType.PRIMARY_LITERARY,
        )
        assert ref.ref_type == ReferenceType.PRIMARY_LITERARY

    def test_parse_ref_type_exact(self):
        assert _parse_ref_type("primary_literary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("theory") == ReferenceType.THEORY
        assert _parse_ref_type("self_citation") == ReferenceType.SELF_CITATION

    def test_parse_ref_type_aliases(self):
        assert _parse_ref_type("primary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("literary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("secondary") == ReferenceType.SECONDARY_CRITICISM
        assert _parse_ref_type("criticism") == ReferenceType.SECONDARY_CRITICISM
        assert _parse_ref_type("historical") == ReferenceType.HISTORICAL_CONTEXT
        assert _parse_ref_type("method") == ReferenceType.METHODOLOGY
        assert _parse_ref_type("reference") == ReferenceType.REFERENCE_WORK
        assert _parse_ref_type("self") == ReferenceType.SELF_CITATION

    def test_parse_ref_type_normalization(self):
        assert _parse_ref_type("Primary Literary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("THEORY") == ReferenceType.THEORY
        assert _parse_ref_type("historical-context") == ReferenceType.HISTORICAL_CONTEXT
        assert _parse_ref_type("  self_citation  ") == ReferenceType.SELF_CITATION

    def test_parse_ref_type_unknown(self):
        assert _parse_ref_type("garbage") == ReferenceType.UNCLASSIFIED
        assert _parse_ref_type("") == ReferenceType.UNCLASSIFIED


# --- Phase 10.2b: DB Migration Tests ---


class TestDBRefType:
    def test_insert_reference_with_type(self, db):
        ref = Reference(
            title="The Origins of Totalitarianism",
            authors=["Hannah Arendt"],
            year=1951,
            publisher="Harcourt",
            ref_type=ReferenceType.THEORY,
        )
        ref_id = db.insert_reference(ref)
        rows = db.conn.execute(
            "SELECT ref_type FROM references_ WHERE id = ?", (ref_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["ref_type"] == "theory"

    def test_insert_reference_default_type(self, db):
        ref = Reference(
            title="Some Paper",
            authors=["Author"],
            year=2020,
        )
        ref_id = db.insert_reference(ref)
        rows = db.conn.execute(
            "SELECT ref_type FROM references_ WHERE id = ?", (ref_id,)
        ).fetchall()
        assert rows[0]["ref_type"] == "unclassified"

    def test_row_to_reference_preserves_type(self, db):
        ref = Reference(
            title="Men in the Sun",
            authors=["Ghassan Kanafani"],
            year=1963,
            ref_type=ReferenceType.PRIMARY_LITERARY,
        )
        ref_id = db.insert_reference(ref)
        retrieved = db.get_verified_references(limit=100)
        # Our ref is not verified, so use direct query
        row = db.conn.execute(
            "SELECT * FROM references_ WHERE id = ?", (ref_id,)
        ).fetchone()
        from src.knowledge_base.db import _row_to_reference
        result = _row_to_reference(row)
        assert result.ref_type == ReferenceType.PRIMARY_LITERARY

    def test_update_reference_type(self, db):
        ref = Reference(title="Test", authors=["A"], year=2020)
        ref_id = db.insert_reference(ref)
        db.update_reference_type(ref_id, ReferenceType.SECONDARY_CRITICISM)
        row = db.conn.execute(
            "SELECT ref_type FROM references_ WHERE id = ?", (ref_id,)
        ).fetchone()
        assert row["ref_type"] == "secondary_criticism"

    def test_get_references_by_type(self, db):
        refs = [
            Reference(title="Novel A", authors=["X"], year=2020,
                      ref_type=ReferenceType.PRIMARY_LITERARY),
            Reference(title="Criticism B", authors=["Y"], year=2020,
                      ref_type=ReferenceType.SECONDARY_CRITICISM),
            Reference(title="Novel C", authors=["Z"], year=2020,
                      ref_type=ReferenceType.PRIMARY_LITERARY),
        ]
        for r in refs:
            db.insert_reference(r)

        primaries = db.get_references_by_type(ReferenceType.PRIMARY_LITERARY)
        assert len(primaries) == 2
        secondary = db.get_references_by_type(ReferenceType.SECONDARY_CRITICISM)
        assert len(secondary) == 1
        theory = db.get_references_by_type(ReferenceType.THEORY)
        assert len(theory) == 0

    def test_migration_adds_column(self, tmp_path):
        """Simulate an old database without ref_type column, then migrate."""
        db = Database(tmp_path / "old.sqlite")
        # Create tables WITHOUT ref_type
        db.conn.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                authors TEXT NOT NULL DEFAULT '[]',
                abstract TEXT,
                journal TEXT NOT NULL,
                year INTEGER NOT NULL,
                volume TEXT, issue TEXT, pages TEXT,
                doi TEXT UNIQUE,
                semantic_scholar_id TEXT, openalex_id TEXT,
                language TEXT NOT NULL DEFAULT 'en',
                keywords TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'discovered',
                pdf_path TEXT, url TEXT, pdf_url TEXT,
                external_ids TEXT NOT NULL DEFAULT '{}',
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS references_ (
                id TEXT PRIMARY KEY,
                paper_id TEXT,
                title TEXT NOT NULL,
                authors TEXT NOT NULL DEFAULT '[]',
                year INTEGER NOT NULL,
                journal TEXT, volume TEXT, issue TEXT, pages TEXT,
                doi TEXT, publisher TEXT,
                verified INTEGER NOT NULL DEFAULT 0,
                verification_source TEXT,
                formatted_mla TEXT, formatted_chicago TEXT, formatted_gb TEXT,
                FOREIGN KEY (paper_id) REFERENCES papers(id)
            );
        """)
        db.conn.commit()

        # Insert a reference without ref_type column
        db.conn.execute(
            "INSERT INTO references_ (id, title, authors, year) VALUES (?, ?, ?, ?)",
            ("old_ref", "Old Reference", '["Author"]', 2019),
        )
        db.conn.commit()

        # Run migration
        db.initialize()

        # Check column now exists
        row = db.conn.execute(
            "SELECT ref_type FROM references_ WHERE id = 'old_ref'"
        ).fetchone()
        assert row["ref_type"] == "unclassified"
        db.close()


# --- Phase 10.2c: Classification & Balance Tests ---


class TestClassification:
    @pytest.mark.asyncio
    async def test_classify_detects_self_citation(self, selector):
        """Self-citations are detected by author overlap without LLM call."""
        references = [
            {
                "id": "ref1",
                "title": "My Prior Work",
                "authors": ["John Smith"],
                "year": 2020,
            },
            {
                "id": "ref2",
                "title": "Someone Else's Work",
                "authors": ["Jane Doe"],
                "year": 2019,
            },
        ]
        # Mock the LLM to classify the non-self-citation
        selector.llm.complete = MagicMock(
            return_value='{"0": "secondary_criticism"}'
        )

        results = await selector.classify_references(
            references, manuscript_authors=["John Smith"]
        )
        result_dict = dict(results)
        assert result_dict["ref1"] == ReferenceType.SELF_CITATION
        assert result_dict["ref2"] == ReferenceType.SECONDARY_CRITICISM

    @pytest.mark.asyncio
    async def test_classify_llm_response_parsing(self, selector):
        """LLM responses are correctly parsed into ReferenceType values."""
        references = [
            {"id": "r1", "title": "Hamlet", "authors": ["Shakespeare"], "year": 1603},
            {"id": "r2", "title": "Mimesis", "authors": ["Auerbach"], "year": 1946},
            {"id": "r3", "title": "Orientalism", "authors": ["Said"], "year": 1978},
        ]
        selector.llm.complete = MagicMock(
            return_value='{"0": "primary_literary", "1": "theory", "2": "secondary_criticism"}'
        )

        results = await selector.classify_references(references)
        result_dict = dict(results)
        assert result_dict["r1"] == ReferenceType.PRIMARY_LITERARY
        assert result_dict["r2"] == ReferenceType.THEORY
        assert result_dict["r3"] == ReferenceType.SECONDARY_CRITICISM

    @pytest.mark.asyncio
    async def test_classify_handles_malformed_llm_response(self, selector):
        """Malformed LLM output produces UNCLASSIFIED rather than errors."""
        references = [
            {"id": "r1", "title": "Test", "authors": ["X"], "year": 2020},
        ]
        selector.llm.complete = MagicMock(return_value="Sorry, I can't do that.")

        results = await selector.classify_references(references)
        assert len(results) == 1
        assert results[0] == ("r1", ReferenceType.UNCLASSIFIED)


class TestTypeBalance:
    def test_balanced_distribution_no_deviations(self, citation_profile):
        """A well-balanced distribution should produce no deviations."""
        type_counts = {
            "primary_literary": 12,
            "secondary_criticism": 15,
            "theory": 5,
            "methodology": 3,
            "historical_context": 3,
            "reference_work": 1,
            "self_citation": 1,
        }
        deviations = ReferenceSelector.check_type_balance(type_counts, citation_profile)
        assert len(deviations) == 0

    def test_under_primary_literary(self, citation_profile):
        """Too few primary literary texts should be flagged."""
        type_counts = {
            "primary_literary": 2,  # ~5% of 40 -- well below 20% min
            "secondary_criticism": 25,
            "theory": 8,
            "methodology": 2,
            "historical_context": 2,
            "reference_work": 1,
        }
        deviations = ReferenceSelector.check_type_balance(type_counts, citation_profile)
        under_types = [d["type"] for d in deviations if d["status"] == "under"]
        assert "primary_literary" in under_types

    def test_over_theory(self, citation_profile):
        """Too much theory should be flagged."""
        type_counts = {
            "primary_literary": 5,
            "secondary_criticism": 5,
            "theory": 30,  # 75% of 40 -- far above 25% max
        }
        deviations = ReferenceSelector.check_type_balance(type_counts, citation_profile)
        over_types = [d["type"] for d in deviations if d["status"] == "over"]
        assert "theory" in over_types

    def test_empty_counts(self, citation_profile):
        """Empty distribution should produce no deviations (not crash)."""
        deviations = ReferenceSelector.check_type_balance({}, citation_profile)
        assert deviations == []

    def test_format_balance_report(self):
        type_counts = {
            "primary_literary": 10,
            "secondary_criticism": 15,
            "theory": 5,
        }
        deviations = [
            {
                "type": "primary_literary",
                "count": 10,
                "actual_pct": 33.3,
                "target_range": [20, 40],
                "status": "ok",
            }
        ]
        report = ReferenceSelector.format_balance_report(type_counts, [])
        assert "Reference Type Distribution" in report
        assert "30 total references" in report
        assert "All reference types within target ranges" in report

    def test_format_report_with_deviations(self):
        type_counts = {"theory": 20, "primary_literary": 1}
        deviations = [
            {
                "type": "theory",
                "count": 20,
                "actual_pct": 95.2,
                "target_range": [8, 25],
                "status": "over",
            },
            {
                "type": "primary_literary",
                "count": 1,
                "actual_pct": 4.8,
                "target_range": [20, 40],
                "status": "under",
            },
        ]
        report = ReferenceSelector.format_balance_report(type_counts, deviations)
        assert "WARNING" in report
        assert "OVER" in report
        assert "UNDER" in report
