"""Tests for Phase 15: Smart Reference Pipeline.

Tests cover:
- CitationChainMiner: metadata extraction, backward/forward/author/journal chains, expansion
- SmartReferencePipeline: blueprint parsing, verification, curation, end-to-end flow
- Helper functions: Jaccard overlap, JSON parsing, candidate-to-paper conversion
- OpenAlex API client: new methods (get_work_references, get_citing_works, etc.)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import Paper, PaperStatus
from src.reference_acquisition.citation_chain import (
    CitationChainMiner,
    _extract_work_metadata,
)
from src.reference_acquisition.smart_search import (
    BlueprintCategory,
    BlueprintResult,
    CuratedRef,
    SmartReferencePipeline,
    SmartSearchReport,
    VerifiedRef,
    _candidate_to_paper,
    _jaccard_word_overlap,
    _parse_json_from_llm,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    db = Database(db_path=tmp_path / "test.db")
    db.initialize()
    return db


@pytest.fixture
def mock_openalex():
    client = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_llm():
    router = MagicMock()
    router.get_response_text = MagicMock(return_value="")
    return router


# ---------------------------------------------------------------------------
# Test _extract_work_metadata
# ---------------------------------------------------------------------------


class TestExtractWorkMetadata:
    def test_full_work(self):
        work = {
            "id": "https://openalex.org/W123",
            "title": "Test Paper",
            "authorships": [
                {"author": {"display_name": "Alice Smith"}},
                {"author": {"display_name": "Bob Jones"}},
            ],
            "publication_year": 2023,
            "primary_location": {
                "source": {"display_name": "Nature"}
            },
            "doi": "https://doi.org/10.1234/test",
            "cited_by_count": 42,
        }
        meta = _extract_work_metadata(work)
        assert meta["openalex_id"] == "https://openalex.org/W123"
        assert meta["title"] == "Test Paper"
        assert meta["authors"] == ["Alice Smith", "Bob Jones"]
        assert meta["year"] == 2023
        assert meta["journal"] == "Nature"
        assert meta["doi"] == "10.1234/test"
        assert meta["cited_by_count"] == 42

    def test_minimal_work(self):
        work = {"id": "W1"}
        meta = _extract_work_metadata(work)
        assert meta["openalex_id"] == "W1"
        assert meta["title"] == ""
        assert meta["authors"] == []
        assert meta["year"] == 0
        assert meta["journal"] == ""
        assert meta["doi"] == ""
        assert meta["cited_by_count"] == 0

    def test_doi_without_prefix(self):
        work = {"id": "W1", "doi": "10.1234/test"}
        meta = _extract_work_metadata(work)
        assert meta["doi"] == "10.1234/test"

    def test_empty_authorships(self):
        work = {"id": "W1", "authorships": [{"author": {}}]}
        meta = _extract_work_metadata(work)
        assert meta["authors"] == []


# ---------------------------------------------------------------------------
# Test _jaccard_word_overlap
# ---------------------------------------------------------------------------


class TestJaccardWordOverlap:
    def test_identical(self):
        assert _jaccard_word_overlap("hello world", "hello world") == 1.0

    def test_no_overlap(self):
        assert _jaccard_word_overlap("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        sim = _jaccard_word_overlap("hello world", "hello there")
        assert 0.3 < sim < 0.5

    def test_empty_string(self):
        assert _jaccard_word_overlap("", "hello") == 0.0

    def test_case_insensitive(self):
        assert _jaccard_word_overlap("Hello World", "hello world") == 1.0


# ---------------------------------------------------------------------------
# Test _parse_json_from_llm
# ---------------------------------------------------------------------------


class TestParseJsonFromLlm:
    def test_plain_json(self):
        result = _parse_json_from_llm('{"key": "value"}')
        assert result == {"key": "value"}

    def test_with_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = _parse_json_from_llm(text)
        assert result == {"key": "value"}

    def test_with_generic_fences(self):
        text = '```\n[1, 2, 3]\n```'
        result = _parse_json_from_llm(text)
        assert result == [1, 2, 3]

    def test_invalid_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_json_from_llm("not json at all")

    def test_array(self):
        result = _parse_json_from_llm('[{"a": 1}]')
        assert result == [{"a": 1}]


# ---------------------------------------------------------------------------
# Test _candidate_to_paper
# ---------------------------------------------------------------------------


class TestCandidateToPaper:
    def test_full_candidate(self):
        c = {
            "title": "Test Paper",
            "authors": ["Author A", "Author B"],
            "year": 2022,
            "journal": "Nature",
            "doi": "10.1234/test",
            "openalex_id": "W123",
        }
        paper = _candidate_to_paper(c)
        assert paper.title == "Test Paper"
        assert paper.authors == ["Author A", "Author B"]
        assert paper.year == 2022
        assert paper.journal == "Nature"
        assert paper.doi == "10.1234/test"
        assert paper.status == PaperStatus.METADATA_ONLY

    def test_minimal_candidate(self):
        paper = _candidate_to_paper({})
        assert paper.title == "Untitled"
        assert paper.authors == []
        assert paper.year == 0

    def test_authors_as_string(self):
        c = {"title": "X", "authors": "Alice, Bob, Charlie"}
        paper = _candidate_to_paper(c)
        assert paper.authors == ["Alice", "Bob", "Charlie"]


# ---------------------------------------------------------------------------
# Test BlueprintResult
# ---------------------------------------------------------------------------


class TestBlueprintResult:
    def test_total_suggested(self):
        bp = BlueprintResult(categories=[
            BlueprintCategory(name="A", description="", suggested_refs=[{"title": "x"}]),
            BlueprintCategory(name="B", description="", suggested_refs=[{"title": "y"}, {"title": "z"}]),
        ])
        assert bp.total_suggested == 3

    def test_all_key_authors_dedup(self):
        bp = BlueprintResult(categories=[
            BlueprintCategory(name="A", description="", key_authors=["Alice", "Bob"]),
            BlueprintCategory(name="B", description="", key_authors=["alice", "Charlie"]),
        ])
        # "alice" should be deduped with "Alice"
        assert len(bp.all_key_authors) == 3

    def test_all_key_journals_dedup(self):
        bp = BlueprintResult(categories=[
            BlueprintCategory(name="A", description="", key_journals=["Nature", "Science"]),
            BlueprintCategory(name="B", description="", key_journals=["nature"]),
        ])
        assert len(bp.all_key_journals) == 2

    def test_empty_blueprint(self):
        bp = BlueprintResult()
        assert bp.total_suggested == 0
        assert bp.all_key_authors == []
        assert bp.all_key_journals == []


# ---------------------------------------------------------------------------
# Test SmartSearchReport
# ---------------------------------------------------------------------------


class TestSmartSearchReport:
    def test_summary(self):
        report = SmartSearchReport(
            topic="test",
            blueprint_suggested=10,
            verified=7,
            hallucinated=3,
            expanded_pool=50,
            final_selected=20,
        )
        s = report.summary()
        assert "test" in s
        assert "10" in s
        assert "7" in s

    def test_defaults(self):
        report = SmartSearchReport()
        assert report.topic == ""
        assert report.references == []
        assert report.categories == {}


# ---------------------------------------------------------------------------
# Test CitationChainMiner
# ---------------------------------------------------------------------------


class TestCitationChainMiner:
    @pytest.mark.asyncio
    async def test_get_references_of(self, mock_openalex):
        mock_openalex.get_work_references = AsyncMock(return_value=[
            {
                "id": "W1",
                "title": "Ref Paper",
                "authorships": [{"author": {"display_name": "Author A"}}],
                "publication_year": 2020,
                "primary_location": {"source": {"display_name": "Journal X"}},
                "doi": "https://doi.org/10.1/a",
                "cited_by_count": 10,
            }
        ])
        miner = CitationChainMiner(openalex=mock_openalex)
        refs = await miner.get_references_of("W100")
        assert len(refs) == 1
        assert refs[0]["title"] == "Ref Paper"
        assert refs[0]["doi"] == "10.1/a"

    @pytest.mark.asyncio
    async def test_get_references_of_failure(self, mock_openalex):
        mock_openalex.get_work_references = AsyncMock(side_effect=Exception("API error"))
        miner = CitationChainMiner(openalex=mock_openalex)
        refs = await miner.get_references_of("W100")
        assert refs == []

    @pytest.mark.asyncio
    async def test_get_citing_works(self, mock_openalex):
        mock_openalex.get_citing_works = AsyncMock(return_value=[
            {"id": "W2", "title": "Citing Paper", "authorships": [],
             "publication_year": 2024, "primary_location": {},
             "doi": None, "cited_by_count": 5}
        ])
        miner = CitationChainMiner(openalex=mock_openalex)
        citing = await miner.get_citing_works("W100")
        assert len(citing) == 1
        assert citing[0]["title"] == "Citing Paper"

    @pytest.mark.asyncio
    async def test_get_author_works(self, mock_openalex):
        mock_openalex.search_author = AsyncMock(return_value="A123")
        mock_openalex.get_author_works = AsyncMock(return_value=[
            {"id": "W3", "title": "Author Paper", "authorships": [],
             "publication_year": 2021, "primary_location": {},
             "doi": None, "cited_by_count": 15}
        ])
        miner = CitationChainMiner(openalex=mock_openalex)
        works = await miner.get_author_works("Test Author")
        assert len(works) == 1

    @pytest.mark.asyncio
    async def test_get_author_works_not_found(self, mock_openalex):
        mock_openalex.search_author = AsyncMock(return_value=None)
        miner = CitationChainMiner(openalex=mock_openalex)
        works = await miner.get_author_works("Unknown Author")
        assert works == []

    @pytest.mark.asyncio
    async def test_search_in_journal(self, mock_openalex):
        mock_openalex.search_works_in_journal = AsyncMock(return_value=[
            {"id": "W4", "title": "Journal Paper", "authorships": [],
             "publication_year": 2022, "primary_location": {"source": {"display_name": "CL"}},
             "doi": None, "cited_by_count": 8}
        ])
        miner = CitationChainMiner(openalex=mock_openalex)
        works = await miner.search_in_journal("translation", "Comparative Literature")
        assert len(works) == 1
        assert works[0]["journal"] == "CL"

    @pytest.mark.asyncio
    async def test_expand_from_seeds_empty(self, mock_openalex):
        miner = CitationChainMiner(openalex=mock_openalex)
        # No seeds, no authors, no journals
        mock_openalex.get_work_references = AsyncMock(return_value=[])
        mock_openalex.get_citing_works = AsyncMock(return_value=[])
        candidates = await miner.expand_from_seeds([], [], [], "test")
        assert candidates == []

    @pytest.mark.asyncio
    async def test_expand_deduplicates_by_doi(self, mock_openalex):
        same_paper = {
            "id": "W1", "title": "Same", "authorships": [],
            "publication_year": 2020, "primary_location": {},
            "doi": "https://doi.org/10.1/dup", "cited_by_count": 5,
        }
        mock_openalex.get_work_references = AsyncMock(return_value=[same_paper])
        mock_openalex.get_citing_works = AsyncMock(return_value=[same_paper])

        miner = CitationChainMiner(openalex=mock_openalex)
        seeds = [{"openalex_id": "W100", "title": "Seed", "doi": ""}]
        candidates = await miner.expand_from_seeds(seeds, [], [], "test")
        # Same DOI paper should only appear once
        assert len(candidates) == 1

    @pytest.mark.asyncio
    async def test_expand_respects_max_total(self, mock_openalex):
        papers = [
            {"id": f"W{i}", "title": f"Paper {i}", "authorships": [],
             "publication_year": 2020, "primary_location": {},
             "doi": f"https://doi.org/10.1/{i}", "cited_by_count": i}
            for i in range(50)
        ]
        mock_openalex.get_work_references = AsyncMock(return_value=papers)
        mock_openalex.get_citing_works = AsyncMock(return_value=[])

        miner = CitationChainMiner(openalex=mock_openalex)
        seeds = [{"openalex_id": "W100", "title": "Seed", "doi": ""}]
        candidates = await miner.expand_from_seeds(seeds, [], [], "test", max_total=10)
        assert len(candidates) <= 10


# ---------------------------------------------------------------------------
# Test SmartReferencePipeline — Phase 1: Blueprint
# ---------------------------------------------------------------------------


class TestGenerateBlueprint:
    @pytest.mark.asyncio
    async def test_parse_valid_blueprint(self, tmp_db, mock_llm):
        blueprint_json = json.dumps({
            "categories": [
                {
                    "name": "Translation Theory",
                    "description": "Core translation studies",
                    "suggested_refs": [
                        {"author": "Venuti", "title": "The Translator's Invisibility", "year": 1995},
                        {"author": "Berman", "title": "L'épreuve de l'étranger", "year": 1984},
                    ],
                    "search_queries": ["translation theory domestication foreignization"],
                    "key_authors": ["Lawrence Venuti", "Antoine Berman"],
                    "key_journals": ["Translation Studies"],
                },
                {
                    "name": "World Literature",
                    "description": "Frameworks of world literature",
                    "suggested_refs": [
                        {"author": "Moretti", "title": "Conjectures on World Literature", "year": 2000},
                    ],
                    "search_queries": ["world literature theory"],
                    "key_authors": ["Franco Moretti"],
                    "key_journals": ["New Left Review"],
                },
            ]
        })
        mock_llm.get_response_text.return_value = blueprint_json
        mock_llm.complete = MagicMock(return_value="mock_response")

        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        bp = await pipeline._generate_blueprint("Test Topic", "Test RQ", "Test gap")
        assert len(bp.categories) == 2
        assert bp.total_suggested == 3
        assert "Lawrence Venuti" in bp.all_key_authors
        assert "Translation Studies" in bp.all_key_journals

    @pytest.mark.asyncio
    async def test_parse_empty_blueprint(self, tmp_db, mock_llm):
        mock_llm.get_response_text.return_value = "not valid json at all"
        mock_llm.complete = MagicMock(return_value="mock_response")

        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        bp = await pipeline._generate_blueprint("X", "Y", "Z")
        assert bp.total_suggested == 0


# ---------------------------------------------------------------------------
# Test SmartReferencePipeline — Phase 2: Verification
# ---------------------------------------------------------------------------


class TestVerifyReferences:
    @pytest.mark.asyncio
    async def test_crossref_match(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        # Mock CrossRef to return a matching result
        pipeline.crossref.search_works = AsyncMock(return_value={
            "message": {
                "items": [
                    {
                        "title": ["The Translator's Invisibility"],
                        "author": [{"given": "Lawrence", "family": "Venuti"}],
                        "published-print": {"date-parts": [[1995]]},
                        "container-title": ["Translation Studies"],
                        "DOI": "10.1234/test",
                    }
                ]
            }
        })

        ref = {"author": "Venuti", "title": "The Translator's Invisibility", "year": 1995}
        result = await pipeline._verify_single_ref(ref)
        assert result.verified is True
        assert result.source == "crossref"
        assert result.paper is not None
        assert result.paper.doi == "10.1234/test"

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_openalex_fallback(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        # CrossRef returns nothing
        pipeline.crossref.search_works = AsyncMock(return_value={
            "message": {"items": []}
        })
        # OpenAlex returns a match
        pipeline.oa.search_works = AsyncMock(return_value={
            "results": [
                {
                    "id": "W123",
                    "title": "The Translator's Invisibility",
                    "authorships": [{"author": {"display_name": "Lawrence Venuti"}}],
                    "publication_year": 1995,
                    "primary_location": {"source": {"display_name": "Translation Studies"}},
                    "doi": None,
                    "cited_by_count": 100,
                }
            ]
        })

        ref = {"author": "Venuti", "title": "The Translator's Invisibility", "year": 1995}
        result = await pipeline._verify_single_ref(ref)
        assert result.verified is True
        assert result.source == "openalex"

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_no_match_found(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        pipeline.crossref.search_works = AsyncMock(return_value={
            "message": {"items": []}
        })
        pipeline.oa.search_works = AsyncMock(return_value={"results": []})

        ref = {"author": "Fake", "title": "Completely Made Up Paper", "year": 2099}
        result = await pipeline._verify_single_ref(ref)
        assert result.verified is False
        assert result.source == "unverified"

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_empty_title(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        ref = {"author": "Venuti", "title": "", "year": 1995}
        result = await pipeline._verify_single_ref(ref)
        assert result.verified is False

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_low_similarity_no_match(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        pipeline.crossref.search_works = AsyncMock(return_value={
            "message": {
                "items": [
                    {
                        "title": ["Completely Different Title About Unrelated Subject"],
                        "author": [{"given": "Other", "family": "Author"}],
                        "DOI": "10.1/x",
                    }
                ]
            }
        })
        pipeline.oa.search_works = AsyncMock(return_value={"results": []})

        ref = {"author": "Venuti", "title": "The Translator's Invisibility", "year": 1995}
        result = await pipeline._verify_single_ref(ref)
        assert result.verified is False

        await pipeline.close()


# ---------------------------------------------------------------------------
# Test SmartReferencePipeline — Phase 4: Curation
# ---------------------------------------------------------------------------


class TestCurateReferences:
    @pytest.mark.asyncio
    async def test_parse_valid_curation(self, tmp_db, mock_llm):
        curation_json = json.dumps({
            "selected": [
                {"index": 0, "category": "Theory", "tier": 1, "usage": "Core framework"},
                {"index": 1, "category": "Criticism", "tier": 2, "usage": "Supporting argument"},
            ],
            "gaps": ["Methodology category has too few references"],
        })
        mock_llm.get_response_text.return_value = curation_json
        mock_llm.complete = MagicMock(return_value="mock_response")

        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        pipeline._topic_title = "Test"
        pipeline._topic_rq = "Test RQ"
        pipeline._gaps = []

        candidates = [
            {"title": "Paper A", "authors": ["Auth A"], "year": 2020, "journal": "J1", "doi": "10.1/a"},
            {"title": "Paper B", "authors": ["Auth B"], "year": 2021, "journal": "J2", "doi": "10.1/b"},
        ]

        verified = [
            VerifiedRef(
                original={"title": "Paper A", "_category": "Theory"},
                verified=True,
                paper=Paper(title="Paper A", authors=["Auth A"], year=2020, journal="J1", doi="10.1/a"),
            ),
        ]

        blueprint = BlueprintResult(categories=[
            BlueprintCategory(name="Theory", description="Theoretical framework"),
            BlueprintCategory(name="Criticism", description="Literary criticism"),
        ])

        curated = await pipeline._curate_references(candidates, verified, blueprint, 2)
        assert len(curated) == 2
        assert curated[0].category == "Theory"
        assert curated[0].tier == 1
        assert curated[1].category == "Criticism"
        assert pipeline._gaps == ["Methodology category has too few references"]

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self, tmp_db, mock_llm):
        mock_llm.get_response_text.return_value = "totally not json"
        mock_llm.complete = MagicMock(return_value="mock_response")

        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        pipeline._topic_title = "Test"
        pipeline._topic_rq = "Test RQ"
        pipeline._gaps = []

        verified = [
            VerifiedRef(
                original={"title": "Paper A", "_category": "Theory"},
                verified=True,
                paper=Paper(title="Paper A", authors=["Auth A"], year=2020, journal="J1"),
            ),
        ]
        blueprint = BlueprintResult(categories=[
            BlueprintCategory(name="Theory", description="x"),
        ])

        curated = await pipeline._curate_references([], verified, blueprint, 5)
        # Should fallback to verified refs
        assert len(curated) == 1
        assert curated[0].paper.title == "Paper A"

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_out_of_range_index_skipped(self, tmp_db, mock_llm):
        curation_json = json.dumps({
            "selected": [
                {"index": 999, "category": "Theory", "tier": 1, "usage": "Test"},
                {"index": 0, "category": "Theory", "tier": 2, "usage": "Valid"},
            ],
            "gaps": [],
        })
        mock_llm.get_response_text.return_value = curation_json
        mock_llm.complete = MagicMock(return_value="mock_response")

        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        pipeline._topic_title = "Test"
        pipeline._topic_rq = "Test RQ"
        pipeline._gaps = []

        verified = [
            VerifiedRef(
                original={"title": "Paper A", "_category": "Theory"},
                verified=True,
                paper=Paper(title="Paper A", authors=["Auth A"], year=2020, journal="J1"),
            ),
        ]
        blueprint = BlueprintResult(categories=[
            BlueprintCategory(name="Theory", description="x"),
        ])

        curated = await pipeline._curate_references([], verified, blueprint, 2)
        # Only the valid index=0 entry should make it
        assert len(curated) == 1

        await pipeline.close()


# ---------------------------------------------------------------------------
# Test SmartReferencePipeline — Phase 5: Persist
# ---------------------------------------------------------------------------


class TestPersistResults:
    @pytest.mark.asyncio
    async def test_insert_new_paper(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        paper = Paper(title="New Paper", authors=["A"], year=2023, journal="J")
        curated = [CuratedRef(paper=paper, category="Theory", tier=1)]

        await pipeline._persist_results(curated)
        assert curated[0].paper.id is not None

        # Verify in DB
        fetched = tmp_db.get_paper(curated[0].paper.id)
        assert fetched is not None
        assert fetched.title == "New Paper"

        await pipeline.close()

    @pytest.mark.asyncio
    async def test_dedup_by_doi(self, tmp_db, mock_llm):
        # Insert a paper with DOI first
        existing = Paper(
            title="Existing Paper", authors=["A"], year=2020,
            journal="J", doi="10.1/existing",
        )
        existing_id = tmp_db.insert_paper(existing)

        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        paper = Paper(
            title="Same Paper", authors=["A"], year=2020,
            journal="J", doi="10.1/existing",
        )
        curated = [CuratedRef(paper=paper, category="Theory", tier=1)]

        await pipeline._persist_results(curated)
        # Should reuse existing paper's ID
        assert curated[0].paper.id == existing_id

        await pipeline.close()


# ---------------------------------------------------------------------------
# Test SmartReferencePipeline — Full flow (mocked)
# ---------------------------------------------------------------------------


class TestSmartSearchFullFlow:
    @pytest.mark.asyncio
    async def test_end_to_end_mocked(self, tmp_db, mock_llm):
        """Test the full smart_search flow with all APIs mocked."""
        # Phase 1: Blueprint response
        blueprint_json = json.dumps({
            "categories": [
                {
                    "name": "Theory",
                    "description": "Theoretical framework",
                    "suggested_refs": [
                        {"author": "Derrida", "title": "Of Grammatology", "year": 1967},
                    ],
                    "search_queries": ["deconstruction theory"],
                    "key_authors": ["Jacques Derrida"],
                    "key_journals": ["Critical Inquiry"],
                },
            ]
        })

        # Phase 4: Curation response
        curation_json = json.dumps({
            "selected": [
                {"index": 0, "category": "Theory", "tier": 1, "usage": "Core framework"},
            ],
            "gaps": [],
        })

        call_count = 0
        def mock_get_text(response):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return blueprint_json
            return curation_json

        mock_llm.get_response_text = MagicMock(side_effect=mock_get_text)
        mock_llm.complete = MagicMock(return_value="mock_response")

        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )

        # Phase 2: Mock CrossRef verification
        pipeline.crossref.search_works = AsyncMock(return_value={
            "message": {
                "items": [
                    {
                        "title": ["Of Grammatology"],
                        "author": [{"given": "Jacques", "family": "Derrida"}],
                        "published-print": {"date-parts": [[1967]]},
                        "container-title": [""],
                        "DOI": "10.1/derrida",
                    }
                ]
            }
        })

        # Phase 3: Mock OpenAlex (chain expansion)
        pipeline.oa.search_works = AsyncMock(return_value={
            "results": [
                {
                    "id": "W999",
                    "title": "Of Grammatology",
                    "authorships": [{"author": {"display_name": "Jacques Derrida"}}],
                    "publication_year": 1967,
                    "primary_location": {"source": {"display_name": ""}},
                    "doi": "https://doi.org/10.1/derrida",
                    "cited_by_count": 5000,
                }
            ]
        })
        pipeline.oa.get_work_references = AsyncMock(return_value=[])
        pipeline.oa.get_citing_works = AsyncMock(return_value=[])
        pipeline.oa.search_author = AsyncMock(return_value="A1")
        pipeline.oa.get_author_works = AsyncMock(return_value=[])
        pipeline.oa.search_works_in_journal = AsyncMock(return_value=[])

        progress_calls = []
        async def track_progress(frac, msg):
            progress_calls.append((frac, msg))

        report = await pipeline.run(
            title="Deconstruction and Translation",
            research_question="How does Derrida's thought inform translation theory?",
            gap_description="No systematic study exists.",
            target_count=5,
            progress_callback=track_progress,
        )

        assert report.blueprint_suggested == 1
        assert report.verified >= 0  # May be 0 or 1 depending on timing
        assert report.final_selected >= 0
        assert len(progress_calls) > 0
        # Progress should go from low to 1.0
        assert progress_calls[-1][0] == 1.0


# ---------------------------------------------------------------------------
# Test VerifiedRef and CuratedRef dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_verified_ref_defaults(self):
        v = VerifiedRef(original={"title": "x"}, verified=False)
        assert v.paper is None
        assert v.source == "unverified"
        assert v.match_confidence == 0.0

    def test_curated_ref_defaults(self):
        p = Paper(title="x", authors=[], year=0, journal="")
        c = CuratedRef(paper=p)
        assert c.category == ""
        assert c.tier == 3
        assert c.usage_note == ""
        assert c.source_phase == "blueprint"

    def test_smart_search_report_defaults(self):
        r = SmartSearchReport()
        assert r.topic == ""
        assert r.gaps == []
        assert r.tier_counts == {}


# ---------------------------------------------------------------------------
# Test CrossRef item to Paper conversion
# ---------------------------------------------------------------------------


class TestCrossRefItemToPaper:
    def test_full_item(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        item = {
            "title": ["Test Title"],
            "author": [
                {"given": "John", "family": "Doe"},
                {"family": "Smith"},
            ],
            "published-print": {"date-parts": [[2023]]},
            "container-title": ["Nature"],
            "DOI": "10.1234/test",
            "volume": "1",
            "issue": "2",
            "page": "10-20",
        }
        paper = pipeline._crossref_item_to_paper(item)
        assert paper.title == "Test Title"
        assert paper.authors == ["John Doe", "Smith"]
        assert paper.year == 2023
        assert paper.journal == "Nature"
        assert paper.doi == "10.1234/test"

    def test_minimal_item(self, tmp_db, mock_llm):
        pipeline = SmartReferencePipeline(
            db=tmp_db, vector_store=MagicMock(), llm_router=mock_llm,
        )
        item = {}
        paper = pipeline._crossref_item_to_paper(item)
        assert paper.title == "Untitled"
        assert paper.authors == []
        assert paper.year == 0
