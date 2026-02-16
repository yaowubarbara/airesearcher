"""Tests for theory supplement stage."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    Language,
    Paper,
    PaperStatus,
    Reference,
    ReferenceType,
)
from src.reference_acquisition.theory_supplement import (
    TheoryCandidate,
    TheoryVerification,
    TheorySupplementReport,
    TheorySupplement,
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
    return MagicMock()


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


# --- TheoryCandidate tests ---


class TestTheoryCandidate:
    def test_basic_fields(self):
        c = TheoryCandidate(
            author="Walter Benjamin",
            title="The Task of the Translator",
            relevance="Translation theory",
            year_hint=1923,
        )
        assert c.author == "Walter Benjamin"
        assert c.title == "The Task of the Translator"
        assert c.year_hint == 1923

    def test_no_year(self):
        c = TheoryCandidate(author="A", title="B", relevance="C")
        assert c.year_hint is None


# --- TheoryVerification tests ---


class TestTheoryVerification:
    def test_defaults(self):
        c = TheoryCandidate(author="A", title="B", relevance="C")
        v = TheoryVerification(candidate=c)
        assert v.verified is False
        assert v.source == "llm_only"
        assert v.reference is None
        assert v.already_in_db is False
        assert v.has_full_text is False

    def test_verified_crossref(self):
        c = TheoryCandidate(author="A", title="B", relevance="C")
        ref = Reference(title="B", authors=["A"], year=2000, ref_type=ReferenceType.THEORY)
        v = TheoryVerification(candidate=c, verified=True, source="crossref", reference=ref)
        assert v.verified is True
        assert v.source == "crossref"


# --- TheorySupplementReport tests ---


class TestTheorySupplementReport:
    def test_empty_report(self):
        r = TheorySupplementReport(plan_id="plan-1")
        assert r.total_recommended == 0
        assert r.verified == 0
        assert r.inserted == 0

    def test_summary(self):
        r = TheorySupplementReport(
            plan_id="plan-1",
            total_recommended=10,
            verified=7,
            inserted=5,
            already_present=2,
        )
        s = r.summary()
        assert "10 recommended" in s
        assert "7 verified" in s
        assert "5 inserted" in s
        assert "2 already in DB" in s


# --- TheorySupplement._predict_theory_works tests ---


class TestPredictTheoryWorks:
    @pytest.mark.asyncio
    async def test_valid_response(self, db, mock_vs, mock_llm):
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Derrida", "title": "Of Grammatology", "year": 1967, "relevance": "Deconstruction"},
            {"author": "Benjamin", "title": "The Arcades Project", "year": 1999, "relevance": "Modernity"},
        ]))

        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidates = await supplement._predict_theory_works(
            "Translation and modernity",
            [{"title": "Section 1", "argument": "Close reading of texts"}],
            [],
        )
        assert len(candidates) == 2
        assert candidates[0].author == "Derrida"
        assert candidates[0].year_hint == 1967

    @pytest.mark.asyncio
    async def test_invalid_json(self, db, mock_vs, mock_llm):
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value="Not JSON")

        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidates = await supplement._predict_theory_works("test", [], [])
        assert candidates == []

    @pytest.mark.asyncio
    async def test_empty_title_skipped(self, db, mock_vs, mock_llm):
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "A", "title": "", "year": 2000, "relevance": "skip"},
            {"author": "B", "title": "Good Title", "year": 2000, "relevance": "keep"},
        ]))

        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidates = await supplement._predict_theory_works("test", [], [])
        assert len(candidates) == 1

    @pytest.mark.asyncio
    async def test_year_as_string(self, db, mock_vs, mock_llm):
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "A", "title": "B", "year": "1967", "relevance": "C"},
        ]))

        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidates = await supplement._predict_theory_works("test", [], [])
        assert candidates[0].year_hint == 1967

    @pytest.mark.asyncio
    async def test_llm_error(self, db, mock_vs, mock_llm):
        mock_llm.complete = MagicMock(side_effect=Exception("API error"))

        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidates = await supplement._predict_theory_works("test", [], [])
        assert candidates == []


# --- TheorySupplement._make_llm_only tests ---


class TestMakeLlmOnly:
    def test_creates_reference(self, db, mock_vs, mock_llm):
        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidate = TheoryCandidate(author="Derrida", title="Of Grammatology", relevance="Key", year_hint=1967)
        v = supplement._make_llm_only(candidate)

        assert v.verified is False
        assert v.source == "llm_only"
        assert v.reference is not None
        assert v.reference.title == "Of Grammatology"
        assert v.reference.authors == ["Derrida"]
        assert v.reference.year == 1967
        assert v.reference.ref_type == ReferenceType.THEORY

    def test_no_year(self, db, mock_vs, mock_llm):
        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidate = TheoryCandidate(author="A", title="B", relevance="C")
        v = supplement._make_llm_only(candidate)
        assert v.reference.year == 0

    def test_no_author(self, db, mock_vs, mock_llm):
        supplement = TheorySupplement(db, mock_vs, mock_llm)
        candidate = TheoryCandidate(author="", title="B", relevance="C")
        v = supplement._make_llm_only(candidate)
        assert v.reference.authors == []


# --- TheorySupplement._normalized_to_reference tests ---


class TestNormalizedToReference:
    def test_full_data(self):
        data = {
            "title": "The Arcades Project",
            "authors": ["Walter Benjamin"],
            "year": 1999,
            "journal": "Harvard University Press",
            "volume": None,
            "issue": None,
            "pages": None,
            "doi": "10.1234/test",
            "publisher": "Harvard",
        }
        ref = TheorySupplement._normalized_to_reference(data, "crossref")
        assert ref.title == "The Arcades Project"
        assert ref.authors == ["Walter Benjamin"]
        assert ref.year == 1999
        assert ref.doi == "10.1234/test"
        assert ref.ref_type == ReferenceType.THEORY
        assert ref.verified is True
        assert ref.verification_source == "crossref"

    def test_missing_year(self):
        data = {"title": "T", "authors": [], "year": None}
        ref = TheorySupplement._normalized_to_reference(data, "openalex")
        assert ref.year == 0


# --- TheorySupplement._openalex_to_reference tests ---


class TestOpenalexToReference:
    def test_full_work(self):
        work = {
            "title": "Orientalism",
            "authorships": [
                {"author": {"display_name": "Edward Said"}},
            ],
            "publication_year": 1978,
            "doi": "https://doi.org/10.1234/test",
            "primary_location": {
                "source": {"display_name": "Vintage Books"},
            },
        }
        ref = TheorySupplement._openalex_to_reference(work)
        assert ref.title == "Orientalism"
        assert ref.authors == ["Edward Said"]
        assert ref.year == 1978
        assert ref.doi == "10.1234/test"
        assert ref.ref_type == ReferenceType.THEORY

    def test_no_authorships(self):
        work = {"title": "T", "authorships": [], "publication_year": 2000}
        ref = TheorySupplement._openalex_to_reference(work)
        assert ref.authors == []

    def test_no_doi(self):
        work = {"title": "T", "authorships": [], "doi": None}
        ref = TheorySupplement._openalex_to_reference(work)
        assert ref.doi is None


# --- DB search_references_by_title ---


class TestSearchReferencesByTitle:
    def test_found(self, db):
        ref = Reference(
            title="The Task of the Translator",
            authors=["Walter Benjamin"],
            year=1923,
            ref_type=ReferenceType.THEORY,
        )
        db.insert_reference(ref)
        results = db.search_references_by_title("task of the translator")
        assert len(results) == 1
        assert results[0].title == "The Task of the Translator"

    def test_case_insensitive(self, db):
        ref = Reference(
            title="Of Grammatology",
            authors=["Jacques Derrida"],
            year=1967,
        )
        db.insert_reference(ref)
        results = db.search_references_by_title("OF GRAMMATOLOGY")
        assert len(results) == 1

    def test_not_found(self, db):
        results = db.search_references_by_title("nonexistent work")
        assert results == []

    def test_limit(self, db):
        for i in range(10):
            ref = Reference(title=f"Theory Work {i}", authors=["Author"], year=2000)
            db.insert_reference(ref)
        results = db.search_references_by_title("Theory Work", limit=3)
        assert len(results) == 3


# --- supplement_plan integration tests ---


class TestSupplementPlan:
    @pytest.mark.asyncio
    async def test_empty_prediction(self, db, mock_vs, mock_llm):
        """LLM predicts nothing — report is empty."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value="[]")

        supplement = TheorySupplement(db, mock_vs, mock_llm)
        report = await supplement.supplement_plan(
            plan_id="plan-1",
            thesis="Test thesis",
            outline_sections=[],
            existing_reference_ids=[],
        )
        assert report.total_recommended == 0
        assert report.inserted == 0

    @pytest.mark.asyncio
    async def test_inserts_llm_only_refs(self, db, mock_vs, mock_llm):
        """When API verification fails, LLM-only refs are still inserted."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Derrida", "title": "Of Grammatology", "year": 1967, "relevance": "Deconstruction"},
        ]))

        # Mock the API clients to return nothing
        with patch("src.reference_acquisition.theory_supplement.CrossRefClient") as mock_cr, \
             patch("src.reference_acquisition.theory_supplement.OpenAlexClient") as mock_oa:
            mock_cr_inst = MagicMock()
            mock_cr_inst.search_works = AsyncMock(return_value={"message": {"items": []}})
            mock_cr_inst.close = AsyncMock()
            mock_cr.return_value = mock_cr_inst

            mock_oa_inst = MagicMock()
            mock_oa_inst.search_works = AsyncMock(return_value={"results": []})
            mock_oa_inst.close = AsyncMock()
            mock_oa.return_value = mock_oa_inst

            supplement = TheorySupplement(db, mock_vs, mock_llm)
            report = await supplement.supplement_plan(
                plan_id="plan-1",
                thesis="Test thesis",
                outline_sections=[],
                existing_reference_ids=[],
            )

        assert report.total_recommended == 1
        assert report.inserted == 1
        assert report.items[0].source == "llm_only"
        assert report.items[0].verified is False

        # Verify ref is in DB
        refs = db.search_references_by_title("Of Grammatology")
        assert len(refs) == 1
        assert refs[0].ref_type == ReferenceType.THEORY

    @pytest.mark.asyncio
    async def test_dedup_existing_refs(self, db, mock_vs, mock_llm):
        """References already in DB are not re-inserted."""
        # Pre-insert a reference
        existing_ref = Reference(
            title="Of Grammatology",
            authors=["Jacques Derrida"],
            year=1967,
            ref_type=ReferenceType.THEORY,
        )
        db.insert_reference(existing_ref)

        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Derrida", "title": "Of Grammatology", "year": 1967, "relevance": "Deconstruction"},
        ]))

        with patch("src.reference_acquisition.theory_supplement.CrossRefClient") as mock_cr, \
             patch("src.reference_acquisition.theory_supplement.OpenAlexClient") as mock_oa:
            mock_cr_inst = MagicMock()
            mock_cr_inst.search_works = AsyncMock(return_value={"message": {"items": []}})
            mock_cr_inst.close = AsyncMock()
            mock_cr.return_value = mock_cr_inst

            mock_oa_inst = MagicMock()
            mock_oa_inst.search_works = AsyncMock(return_value={"results": []})
            mock_oa_inst.close = AsyncMock()
            mock_oa.return_value = mock_oa_inst

            supplement = TheorySupplement(db, mock_vs, mock_llm)
            report = await supplement.supplement_plan(
                plan_id="plan-1",
                thesis="Test thesis",
                outline_sections=[],
                existing_reference_ids=[],
            )

        assert report.already_present == 1
        assert report.inserted == 0

    @pytest.mark.asyncio
    async def test_crossref_verified(self, db, mock_vs, mock_llm):
        """CrossRef match should produce a verified reference."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Derrida", "title": "Of Grammatology", "year": 1967, "relevance": "Deconstruction"},
        ]))

        crossref_item = {
            "title": ["Of Grammatology"],
            "author": [{"given": "Jacques", "family": "Derrida"}],
            "published-print": {"date-parts": [[1967]]},
            "container-title": [],
            "DOI": "10.1234/og",
            "type": "book",
        }

        with patch("src.reference_acquisition.theory_supplement.CrossRefClient") as mock_cr, \
             patch("src.reference_acquisition.theory_supplement.OpenAlexClient") as mock_oa:
            mock_cr_inst = MagicMock()
            mock_cr_inst.search_works = AsyncMock(return_value={
                "message": {"items": [crossref_item]}
            })
            mock_cr_inst.close = AsyncMock()
            mock_cr.return_value = mock_cr_inst

            mock_oa_inst = MagicMock()
            mock_oa_inst.close = AsyncMock()
            mock_oa.return_value = mock_oa_inst

            supplement = TheorySupplement(db, mock_vs, mock_llm)
            report = await supplement.supplement_plan(
                plan_id="plan-1",
                thesis="Test",
                outline_sections=[],
                existing_reference_ids=[],
            )

        assert report.verified == 1
        assert report.inserted == 1
        assert report.items[0].source == "crossref"
        assert report.items[0].verified is True

        refs = db.search_references_by_title("Of Grammatology")
        assert len(refs) == 1
        assert refs[0].doi == "10.1234/og"

    @pytest.mark.asyncio
    async def test_progress_callback(self, db, mock_vs, mock_llm):
        """Progress callback is invoked."""
        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value="[]")

        progress_calls = []

        async def track_progress(progress, message):
            progress_calls.append((progress, message))

        supplement = TheorySupplement(db, mock_vs, mock_llm)
        await supplement.supplement_plan(
            plan_id="plan-1",
            thesis="Test",
            outline_sections=[],
            existing_reference_ids=[],
            progress_callback=track_progress,
        )

        # At minimum: 0.1 and final
        assert len(progress_calls) >= 1

    @pytest.mark.asyncio
    async def test_full_text_check(self, db, mock_vs, mock_llm):
        """has_full_text is True when paper with matching title is indexed."""
        # Pre-insert an indexed paper
        paper = _make_paper("Of Grammatology", PaperStatus.INDEXED)
        db.insert_paper(paper)

        mock_llm.complete = MagicMock(return_value={"choices": [{"message": {"content": "test"}}]})
        mock_llm.get_response_text = MagicMock(return_value=json.dumps([
            {"author": "Derrida", "title": "Of Grammatology", "year": 1967, "relevance": "Key"},
        ]))

        with patch("src.reference_acquisition.theory_supplement.CrossRefClient") as mock_cr, \
             patch("src.reference_acquisition.theory_supplement.OpenAlexClient") as mock_oa:
            mock_cr_inst = MagicMock()
            mock_cr_inst.search_works = AsyncMock(return_value={"message": {"items": []}})
            mock_cr_inst.close = AsyncMock()
            mock_cr.return_value = mock_cr_inst

            mock_oa_inst = MagicMock()
            mock_oa_inst.search_works = AsyncMock(return_value={"results": []})
            mock_oa_inst.close = AsyncMock()
            mock_oa.return_value = mock_oa_inst

            supplement = TheorySupplement(db, mock_vs, mock_llm)
            report = await supplement.supplement_plan(
                plan_id="plan-1",
                thesis="Test",
                outline_sections=[],
                existing_reference_ids=[],
            )

        assert report.items[0].has_full_text is True
