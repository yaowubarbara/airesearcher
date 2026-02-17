"""Tests for the P-ontology annotation, direction clustering, and topic generation pipeline."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    AnnotationGap,
    AnnotationScale,
    Paper,
    PaperAnnotation,
    PaperStatus,
    ProblematiqueDirection,
    TopicProposal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Create a fresh temporary database."""
    db = Database(tmp_path / "test.sqlite")
    db.initialize()
    return db


@pytest.fixture
def sample_papers():
    """A small corpus of sample papers with abstracts."""
    return [
        Paper(
            id="p1",
            title="Translation and the Impossibility of Fidelity",
            authors=["Alice Translator"],
            abstract="This paper argues that fidelity in translation is an unattainable ideal...",
            journal="Comparative Literature",
            year=2023,
            language="en",
            keywords=["translation", "fidelity"],
        ),
        Paper(
            id="p2",
            title="Rhythm as Mediator in Cross-Cultural Poetics",
            authors=["Bob Rhythm"],
            abstract="We investigate how rhythmic patterns serve as mediators between poetic traditions...",
            journal="Comparative Literature",
            year=2022,
            language="en",
            keywords=["rhythm", "poetics"],
        ),
        Paper(
            id="p3",
            title="No Abstract Paper",
            authors=["Charlie None"],
            abstract="",
            journal="Some Journal",
            year=2021,
            language="en",
            keywords=[],
        ),
    ]


@pytest.fixture
def sample_annotations():
    return [
        PaperAnnotation(
            id="a1",
            paper_id="p1",
            tensions=["fidelity ↔ creativity"],
            mediators=["close-reading of rhythm"],
            scale=AnnotationScale.TEXTUAL,
            gap=AnnotationGap.MEDIATIONAL_GAP,
            evidence="Fidelity remains an impossible ideal.",
            deobjectification="The problem of untranslatability persists across all texts.",
        ),
        PaperAnnotation(
            id="a2",
            paper_id="p2",
            tensions=["tradition ↔ innovation"],
            mediators=["rhythmic patterning"],
            scale=AnnotationScale.PERCEPTUAL,
            gap=AnnotationGap.TEMPORAL_FLATTENING,
            evidence="Rhythm bridges poetic traditions.",
            deobjectification="The problem of cross-cultural mediation persists.",
        ),
    ]


def _make_mock_router(return_text: str) -> MagicMock:
    """Create a mock LLMRouter that returns the given text."""
    router = MagicMock()
    router.complete.return_value = "mock_response"
    router.get_response_text.return_value = return_text
    return router


# ===========================================================================
# Model validation tests
# ===========================================================================


class TestAnnotationScaleEnum:
    def test_all_values(self):
        assert len(AnnotationScale) == 5
        assert AnnotationScale.TEXTUAL.value == "textual"
        assert AnnotationScale.PERCEPTUAL.value == "perceptual"
        assert AnnotationScale.MEDIATIONAL.value == "mediational"
        assert AnnotationScale.INSTITUTIONAL.value == "institutional"
        assert AnnotationScale.METHODOLOGICAL.value == "methodological"

    def test_from_string(self):
        assert AnnotationScale("textual") == AnnotationScale.TEXTUAL


class TestAnnotationGapEnum:
    def test_all_values(self):
        assert len(AnnotationGap) == 5
        assert AnnotationGap.MEDIATIONAL_GAP.value == "mediational_gap"
        assert AnnotationGap.TEMPORAL_FLATTENING.value == "temporal_flattening"
        assert AnnotationGap.METHOD_NATURALIZATION.value == "method_naturalization"
        assert AnnotationGap.SCALE_MISMATCH.value == "scale_mismatch"
        assert AnnotationGap.INCOMMENSURABILITY_BLINDSPOT.value == "incommensurability_blindspot"


class TestPaperAnnotationModel:
    def test_defaults(self):
        ann = PaperAnnotation(paper_id="x")
        assert ann.tensions == []
        assert ann.mediators == []
        assert ann.scale == AnnotationScale.TEXTUAL
        assert ann.gap == AnnotationGap.MEDIATIONAL_GAP
        assert ann.evidence == ""
        assert ann.deobjectification == ""

    def test_full_construction(self):
        ann = PaperAnnotation(
            paper_id="p1",
            tensions=["A ↔ B"],
            mediators=["rhythm"],
            scale=AnnotationScale.MEDIATIONAL,
            gap=AnnotationGap.SCALE_MISMATCH,
            evidence="Evidence text",
            deobjectification="Problem statement",
        )
        assert ann.tensions == ["A ↔ B"]
        assert ann.scale == AnnotationScale.MEDIATIONAL


class TestProblematiqueDirectionModel:
    def test_defaults(self):
        d = ProblematiqueDirection(title="Test", description="Desc")
        assert d.paper_ids == []
        assert d.topic_ids == []
        assert d.dominant_scale is None

    def test_full_construction(self):
        d = ProblematiqueDirection(
            title="Direction",
            description="Description",
            dominant_tensions=["A ↔ B"],
            dominant_mediators=["M1"],
            dominant_scale="textual",
            dominant_gap="mediational_gap",
            paper_ids=["p1", "p2"],
        )
        assert len(d.paper_ids) == 2


class TestTopicProposalDirectionId:
    def test_direction_id_default_none(self):
        t = TopicProposal(title="T", research_question="Q", gap_description="G")
        assert t.direction_id is None

    def test_direction_id_set(self):
        t = TopicProposal(
            title="T",
            research_question="Q",
            gap_description="G",
            direction_id="dir-1",
        )
        assert t.direction_id == "dir-1"


# ===========================================================================
# Database tests
# ===========================================================================


class TestDBAnnotations:
    def test_insert_and_get_annotation(self, tmp_db):
        paper = Paper(id="p1", title="Test", journal="J", year=2023)
        tmp_db.insert_paper(paper)

        ann = PaperAnnotation(
            paper_id="p1",
            tensions=["A ↔ B"],
            mediators=["M1"],
            scale=AnnotationScale.TEXTUAL,
            gap=AnnotationGap.MEDIATIONAL_GAP,
            evidence="Evidence",
            deobjectification="Deobj",
        )
        ann_id = tmp_db.insert_annotation(ann)
        assert ann_id

        fetched = tmp_db.get_annotation("p1")
        assert fetched is not None
        assert fetched.paper_id == "p1"
        assert fetched.tensions == ["A ↔ B"]
        assert fetched.mediators == ["M1"]
        assert fetched.scale == AnnotationScale.TEXTUAL
        assert fetched.gap == AnnotationGap.MEDIATIONAL_GAP

    def test_get_annotation_not_found(self, tmp_db):
        assert tmp_db.get_annotation("nonexistent") is None

    def test_get_annotations_list(self, tmp_db):
        for pid in ["p1", "p2"]:
            paper = Paper(id=pid, title=f"Paper {pid}", journal="J", year=2023)
            tmp_db.insert_paper(paper)
            ann = PaperAnnotation(paper_id=pid, tensions=[f"T{pid}"])
            tmp_db.insert_annotation(ann)

        all_anns = tmp_db.get_annotations(limit=10)
        assert len(all_anns) == 2

    def test_count_annotations(self, tmp_db):
        assert tmp_db.count_annotations() == 0
        paper = Paper(id="p1", title="Test", journal="J", year=2023)
        tmp_db.insert_paper(paper)
        tmp_db.insert_annotation(PaperAnnotation(paper_id="p1"))
        assert tmp_db.count_annotations() == 1

    def test_get_unannotated_papers(self, tmp_db):
        # Paper with abstract, no annotation
        p1 = Paper(id="p1", title="With Abstract", abstract="Some text", journal="J", year=2023)
        tmp_db.insert_paper(p1)
        # Paper without abstract
        p2 = Paper(id="p2", title="No Abstract", abstract="", journal="J", year=2023)
        tmp_db.insert_paper(p2)
        # Paper with abstract AND annotation
        p3 = Paper(id="p3", title="Annotated", abstract="Has text", journal="J", year=2023)
        tmp_db.insert_paper(p3)
        tmp_db.insert_annotation(PaperAnnotation(paper_id="p3"))

        unannotated = tmp_db.get_unannotated_papers(limit=10)
        assert len(unannotated) == 1
        assert unannotated[0].id == "p1"

    def test_insert_or_replace_annotation(self, tmp_db):
        paper = Paper(id="p1", title="Test", journal="J", year=2023)
        tmp_db.insert_paper(paper)

        ann1 = PaperAnnotation(paper_id="p1", tensions=["old"])
        tmp_db.insert_annotation(ann1)
        assert tmp_db.get_annotation("p1").tensions == ["old"]

        # Replace with updated annotation (same paper_id)
        ann2 = PaperAnnotation(paper_id="p1", tensions=["new"])
        tmp_db.insert_annotation(ann2)
        assert tmp_db.get_annotation("p1").tensions == ["new"]


class TestDBDirections:
    def test_insert_and_get_direction(self, tmp_db):
        d = ProblematiqueDirection(
            title="Direction 1",
            description="A research direction",
            dominant_tensions=["A ↔ B"],
            paper_ids=["p1", "p2"],
        )
        d_id = tmp_db.insert_direction(d)
        assert d_id

        fetched = tmp_db.get_direction(d_id)
        assert fetched is not None
        assert fetched.title == "Direction 1"
        assert fetched.dominant_tensions == ["A ↔ B"]
        assert fetched.paper_ids == ["p1", "p2"]

    def test_get_direction_not_found(self, tmp_db):
        assert tmp_db.get_direction("nonexistent") is None

    def test_get_directions_list(self, tmp_db):
        for i in range(3):
            tmp_db.insert_direction(
                ProblematiqueDirection(title=f"Dir {i}", description=f"Desc {i}")
            )
        dirs = tmp_db.get_directions(limit=10)
        assert len(dirs) == 3


class TestDBTopicWithDirection:
    def test_insert_topic_with_direction_id(self, tmp_db):
        topic = TopicProposal(
            title="Topic",
            research_question="RQ?",
            gap_description="Gap",
            direction_id="dir-1",
        )
        tid = tmp_db.insert_topic(topic)
        assert tid

        # Fetch back
        topics = tmp_db.get_topics(limit=10)
        assert len(topics) == 1
        assert topics[0].direction_id == "dir-1"

    def test_get_topics_by_direction(self, tmp_db):
        # Insert topics for different directions
        for i in range(5):
            topic = TopicProposal(
                title=f"Topic {i}",
                research_question=f"RQ {i}?",
                gap_description=f"Gap {i}",
                direction_id="dir-A" if i < 3 else "dir-B",
            )
            tmp_db.insert_topic(topic)

        dir_a_topics = tmp_db.get_topics_by_direction("dir-A", limit=10)
        assert len(dir_a_topics) == 3

        dir_b_topics = tmp_db.get_topics_by_direction("dir-B", limit=10)
        assert len(dir_b_topics) == 2


# ===========================================================================
# Annotation pipeline tests
# ===========================================================================


class TestAnnotatePaper:
    @pytest.mark.asyncio
    async def test_valid_annotation(self, sample_papers):
        mock_json = json.dumps({
            "deobjectification": "The problem of untranslatability.",
            "tensions": ["fidelity ↔ creativity"],
            "mediators": ["close-reading"],
            "scale": "textual",
            "gap": "mediational_gap",
            "evidence": "Fidelity is an impossible ideal.",
        })
        router = _make_mock_router(mock_json)

        from src.topic_discovery.gap_analyzer import annotate_paper
        ann = await annotate_paper(sample_papers[0], router)

        assert ann is not None
        assert ann.paper_id == "p1"
        assert ann.tensions == ["fidelity ↔ creativity"]
        assert ann.scale == AnnotationScale.TEXTUAL
        assert ann.gap == AnnotationGap.MEDIATIONAL_GAP

    @pytest.mark.asyncio
    async def test_empty_abstract_returns_none(self, sample_papers):
        router = _make_mock_router("{}")
        from src.topic_discovery.gap_analyzer import annotate_paper
        result = await annotate_paper(sample_papers[2], router)  # empty abstract
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_enum_fallback(self, sample_papers):
        mock_json = json.dumps({
            "deobjectification": "Deobj",
            "tensions": ["A ↔ B"],
            "mediators": ["M"],
            "scale": "INVALID_SCALE",
            "gap": "INVALID_GAP",
            "evidence": "Ev",
        })
        router = _make_mock_router(mock_json)

        from src.topic_discovery.gap_analyzer import annotate_paper
        ann = await annotate_paper(sample_papers[0], router)

        assert ann is not None
        assert ann.scale == AnnotationScale.TEXTUAL  # fallback
        assert ann.gap == AnnotationGap.MEDIATIONAL_GAP  # fallback

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, sample_papers):
        router = MagicMock()
        router.complete.side_effect = RuntimeError("LLM error")

        from src.topic_discovery.gap_analyzer import annotate_paper
        result = await annotate_paper(sample_papers[0], router)
        assert result is None


class TestAnnotateCorpus:
    @pytest.mark.asyncio
    async def test_batch_annotation(self, tmp_db, sample_papers):
        # Insert papers into DB
        for p in sample_papers:
            tmp_db.insert_paper(p)

        mock_json = json.dumps({
            "deobjectification": "Problem",
            "tensions": ["A ↔ B"],
            "mediators": ["M"],
            "scale": "textual",
            "gap": "mediational_gap",
            "evidence": "Evidence",
        })
        router = _make_mock_router(mock_json)

        from src.topic_discovery.gap_analyzer import annotate_corpus
        annotations = await annotate_corpus(sample_papers, router, tmp_db)

        # p3 has empty abstract, so 2 annotations
        assert len(annotations) == 2
        assert tmp_db.count_annotations() == 2

    @pytest.mark.asyncio
    async def test_skip_already_annotated(self, tmp_db, sample_papers):
        # Insert papers and pre-annotate p1
        for p in sample_papers:
            tmp_db.insert_paper(p)
        existing_ann = PaperAnnotation(paper_id="p1", tensions=["existing"])
        tmp_db.insert_annotation(existing_ann)

        mock_json = json.dumps({
            "deobjectification": "Problem",
            "tensions": ["new"],
            "mediators": ["M"],
            "scale": "textual",
            "gap": "mediational_gap",
            "evidence": "Evidence",
        })
        router = _make_mock_router(mock_json)

        from src.topic_discovery.gap_analyzer import annotate_corpus
        annotations = await annotate_corpus(sample_papers, router, tmp_db)

        # p1 was already annotated, p2 gets new, p3 has no abstract
        assert len(annotations) == 2
        # The existing annotation should be preserved
        p1_ann = [a for a in annotations if a.paper_id == "p1"][0]
        assert p1_ann.tensions == ["existing"]


# ===========================================================================
# Direction clustering tests
# ===========================================================================


class TestClusterIntoDirections:
    @pytest.mark.asyncio
    async def test_valid_clustering(self, sample_papers, sample_annotations):
        mock_json = json.dumps([
            {
                "title": "Translation Tensions",
                "description": "Papers about translation fidelity.",
                "dominant_tensions": ["fidelity ↔ creativity"],
                "dominant_mediators": ["close-reading"],
                "dominant_scale": "textual",
                "dominant_gap": "mediational_gap",
                "paper_indices": [0, 1],
            }
        ])
        router = _make_mock_router(mock_json)

        from src.topic_discovery.trend_tracker import cluster_into_directions
        directions = await cluster_into_directions(
            sample_annotations, sample_papers, router
        )

        assert len(directions) == 1
        assert directions[0].title == "Translation Tensions"
        assert "p1" in directions[0].paper_ids
        assert "p2" in directions[0].paper_ids

    @pytest.mark.asyncio
    async def test_paper_indices_mapping(self, sample_papers, sample_annotations):
        """paper_indices should map to correct paper_ids."""
        mock_json = json.dumps([
            {
                "title": "First Only",
                "description": "Only first paper.",
                "dominant_tensions": [],
                "dominant_mediators": [],
                "dominant_scale": "textual",
                "dominant_gap": "mediational_gap",
                "paper_indices": [0],
            },
            {
                "title": "Second Only",
                "description": "Only second paper.",
                "dominant_tensions": [],
                "dominant_mediators": [],
                "dominant_scale": "perceptual",
                "dominant_gap": "temporal_flattening",
                "paper_indices": [1],
            },
        ])
        router = _make_mock_router(mock_json)

        from src.topic_discovery.trend_tracker import cluster_into_directions
        directions = await cluster_into_directions(
            sample_annotations, sample_papers, router
        )

        assert len(directions) == 2
        assert directions[0].paper_ids == ["p1"]
        assert directions[1].paper_ids == ["p2"]

    @pytest.mark.asyncio
    async def test_empty_annotations(self, sample_papers):
        router = _make_mock_router("[]")
        from src.topic_discovery.trend_tracker import cluster_into_directions
        directions = await cluster_into_directions([], sample_papers, router)
        assert directions == []

    @pytest.mark.asyncio
    async def test_out_of_range_indices_ignored(self, sample_papers, sample_annotations):
        mock_json = json.dumps([
            {
                "title": "Dir",
                "description": "Desc",
                "dominant_tensions": [],
                "dominant_mediators": [],
                "dominant_scale": "textual",
                "dominant_gap": "mediational_gap",
                "paper_indices": [0, 999],  # 999 is out of range
            }
        ])
        router = _make_mock_router(mock_json)

        from src.topic_discovery.trend_tracker import cluster_into_directions
        directions = await cluster_into_directions(
            sample_annotations, sample_papers, router
        )

        assert len(directions) == 1
        assert directions[0].paper_ids == ["p1"]  # only valid index


# ===========================================================================
# Topic generation tests
# ===========================================================================


class TestGenerateTopics:
    @pytest.mark.asyncio
    async def test_generates_topics(self, sample_papers, sample_annotations):
        direction = ProblematiqueDirection(
            id="dir-1",
            title="Translation Tensions",
            description="About translation.",
            dominant_tensions=["fidelity ↔ creativity"],
            paper_ids=["p1", "p2"],
        )

        mock_json = json.dumps([
            {
                "title": f"Topic {i}",
                "research_question": f"Question {i}?",
                "gap_description": f"Gap {i}.",
            }
            for i in range(10)
        ])
        router = _make_mock_router(mock_json)

        from src.topic_discovery.topic_scorer import generate_topics_for_direction
        topics = await generate_topics_for_direction(
            direction, sample_papers, sample_annotations, router
        )

        assert len(topics) == 10
        for topic in topics:
            assert topic.direction_id == "dir-1"
            assert topic.novelty_score == 0.0
            assert isinstance(topic.title, str)
            assert isinstance(topic.research_question, str)

    @pytest.mark.asyncio
    async def test_direction_id_set(self, sample_papers, sample_annotations):
        direction = ProblematiqueDirection(
            id="dir-42",
            title="Test",
            description="Test desc",
            paper_ids=["p1"],
        )
        mock_json = json.dumps([
            {"title": "T", "research_question": "Q?", "gap_description": "G."}
        ])
        router = _make_mock_router(mock_json)

        from src.topic_discovery.topic_scorer import generate_topics_for_direction
        topics = await generate_topics_for_direction(
            direction, sample_papers, sample_annotations, router
        )

        assert len(topics) == 1
        assert topics[0].direction_id == "dir-42"

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self, sample_papers, sample_annotations):
        direction = ProblematiqueDirection(
            id="dir-1", title="Test", description="Desc", paper_ids=["p1"]
        )
        router = MagicMock()
        router.complete.side_effect = RuntimeError("LLM error")

        from src.topic_discovery.topic_scorer import generate_topics_for_direction
        topics = await generate_topics_for_direction(
            direction, sample_papers, sample_annotations, router
        )
        assert topics == []


# ===========================================================================
# Row converter tests
# ===========================================================================


class TestRowConverters:
    def test_row_to_annotation(self, tmp_db):
        paper = Paper(id="p1", title="Test", journal="J", year=2023)
        tmp_db.insert_paper(paper)
        ann = PaperAnnotation(
            paper_id="p1",
            tensions=["A ↔ B", "C ↔ D"],
            mediators=["M1", "M2"],
            scale=AnnotationScale.INSTITUTIONAL,
            gap=AnnotationGap.INCOMMENSURABILITY_BLINDSPOT,
            evidence="Evidence text",
            deobjectification="Deobj text",
        )
        tmp_db.insert_annotation(ann)

        fetched = tmp_db.get_annotation("p1")
        assert fetched.tensions == ["A ↔ B", "C ↔ D"]
        assert fetched.mediators == ["M1", "M2"]
        assert fetched.scale == AnnotationScale.INSTITUTIONAL
        assert fetched.gap == AnnotationGap.INCOMMENSURABILITY_BLINDSPOT
        assert fetched.evidence == "Evidence text"
        assert fetched.deobjectification == "Deobj text"

    def test_row_to_direction(self, tmp_db):
        d = ProblematiqueDirection(
            title="Dir Title",
            description="Dir Desc",
            dominant_tensions=["T1"],
            dominant_mediators=["M1"],
            dominant_scale="mediational",
            dominant_gap="temporal_flattening",
            paper_ids=["p1"],
            topic_ids=["t1", "t2"],
        )
        d_id = tmp_db.insert_direction(d)
        fetched = tmp_db.get_direction(d_id)

        assert fetched.title == "Dir Title"
        assert fetched.dominant_tensions == ["T1"]
        assert fetched.dominant_scale == "mediational"
        assert fetched.paper_ids == ["p1"]
        assert fetched.topic_ids == ["t1", "t2"]


# ===========================================================================
# Parse helpers tests
# ===========================================================================


class TestParseAnnotation:
    def test_valid_json(self):
        from src.topic_discovery.gap_analyzer import _parse_annotation
        raw = json.dumps({
            "deobjectification": "Deobj",
            "tensions": ["A ↔ B"],
            "mediators": ["M"],
            "scale": "perceptual",
            "gap": "temporal_flattening",
            "evidence": "Evidence",
        })
        result = _parse_annotation(raw)
        assert result["scale"] == "perceptual"
        assert result["gap"] == "temporal_flattening"

    def test_invalid_scale_fallback(self):
        from src.topic_discovery.gap_analyzer import _parse_annotation
        raw = json.dumps({
            "deobjectification": "D",
            "tensions": [],
            "mediators": [],
            "scale": "WRONG",
            "gap": "mediational_gap",
            "evidence": "E",
        })
        result = _parse_annotation(raw)
        assert result["scale"] == "textual"

    def test_invalid_gap_fallback(self):
        from src.topic_discovery.gap_analyzer import _parse_annotation
        raw = json.dumps({
            "deobjectification": "D",
            "tensions": [],
            "mediators": [],
            "scale": "textual",
            "gap": "WRONG",
            "evidence": "E",
        })
        result = _parse_annotation(raw)
        assert result["gap"] == "mediational_gap"

    def test_no_json(self):
        from src.topic_discovery.gap_analyzer import _parse_annotation
        result = _parse_annotation("This is not JSON at all")
        assert result == {}

    def test_markdown_fenced_json(self):
        from src.topic_discovery.gap_analyzer import _parse_annotation
        raw = '```json\n{"deobjectification":"D","tensions":[],"mediators":[],"scale":"textual","gap":"mediational_gap","evidence":"E"}\n```'
        result = _parse_annotation(raw)
        assert result["deobjectification"] == "D"

    def test_non_list_tensions_fallback(self):
        from src.topic_discovery.gap_analyzer import _parse_annotation
        raw = json.dumps({
            "deobjectification": "D",
            "tensions": "not a list",
            "mediators": 42,
            "scale": "textual",
            "gap": "mediational_gap",
            "evidence": "E",
        })
        result = _parse_annotation(raw)
        assert result["tensions"] == []
        assert result["mediators"] == []


# ===========================================================================
# Recency score tests
# ===========================================================================


class TestRecencyScore:
    def test_current_year_papers(self):
        from src.topic_discovery.trend_tracker import compute_recency_scores
        papers = [
            Paper(id="p1", title="P1", journal="J", year=2026),
            Paper(id="p2", title="P2", journal="J", year=2026),
        ]
        d = ProblematiqueDirection(title="D", description="", paper_ids=["p1", "p2"])
        compute_recency_scores([d], papers, 2026)
        assert d.recency_score == 1.0

    def test_old_papers(self):
        from src.topic_discovery.trend_tracker import compute_recency_scores
        papers = [
            Paper(id="p1", title="P1", journal="J", year=2020),
        ]
        d = ProblematiqueDirection(title="D", description="", paper_ids=["p1"])
        compute_recency_scores([d], papers, 2026)
        # 1 / (2026 - 2020 + 1) = 1/7
        assert abs(d.recency_score - 1.0 / 7) < 1e-9

    def test_mixed_years(self):
        from src.topic_discovery.trend_tracker import compute_recency_scores
        papers = [
            Paper(id="p1", title="P1", journal="J", year=2026),
            Paper(id="p2", title="P2", journal="J", year=2024),
        ]
        d = ProblematiqueDirection(title="D", description="", paper_ids=["p1", "p2"])
        compute_recency_scores([d], papers, 2026)
        expected = (1.0 + 1.0 / 3) / 2
        assert abs(d.recency_score - expected) < 1e-9

    def test_empty_paper_ids(self):
        from src.topic_discovery.trend_tracker import compute_recency_scores
        d = ProblematiqueDirection(title="D", description="", paper_ids=[])
        compute_recency_scores([d], [], 2026)
        assert d.recency_score == 0.0

    def test_missing_paper_in_corpus(self):
        from src.topic_discovery.trend_tracker import compute_recency_scores
        papers = [Paper(id="p1", title="P1", journal="J", year=2026)]
        d = ProblematiqueDirection(title="D", description="", paper_ids=["p1", "p_missing"])
        compute_recency_scores([d], papers, 2026)
        # Only p1 contributes
        assert d.recency_score == 1.0


# ===========================================================================
# Delta cluster tests
# ===========================================================================


class TestDeltaCluster:
    @pytest.mark.asyncio
    async def test_assign_to_existing(self, sample_papers, sample_annotations):
        existing = [
            ProblematiqueDirection(
                id="dir-1", title="Existing", description="D",
                dominant_tensions=["A ↔ B"], paper_ids=["p1"],
            )
        ]
        new_ann = [sample_annotations[1]]  # p2

        result_json = json.dumps({
            "assignments": [{"annotation_index": 0, "direction_id": "dir-1"}],
            "new_directions": [],
        })
        router = _make_mock_router(result_json)

        from src.topic_discovery.trend_tracker import delta_cluster_directions
        dirs, changed = await delta_cluster_directions(
            new_ann, existing, sample_papers, router
        )

        assert len(dirs) == 1
        assert "p2" in dirs[0].paper_ids
        assert "dir-1" in changed

    @pytest.mark.asyncio
    async def test_new_direction(self, sample_papers, sample_annotations):
        existing = [
            ProblematiqueDirection(
                id="dir-1", title="Existing", description="D", paper_ids=["p1"],
            )
        ]
        new_ann = [sample_annotations[1]]

        result_json = json.dumps({
            "assignments": [],
            "new_directions": [{
                "title": "Brand New",
                "description": "New direction",
                "dominant_tensions": ["new tension"],
                "dominant_mediators": [],
                "dominant_scale": "textual",
                "dominant_gap": "mediational_gap",
                "annotation_indices": [0],
            }],
        })
        router = _make_mock_router(result_json)

        from src.topic_discovery.trend_tracker import delta_cluster_directions
        dirs, changed = await delta_cluster_directions(
            new_ann, existing, sample_papers, router
        )

        assert len(dirs) == 2
        assert dirs[1].title == "Brand New"
        assert "p2" in dirs[1].paper_ids
        assert "__new__" in changed

    @pytest.mark.asyncio
    async def test_empty_new_annotations(self, sample_papers):
        existing = [
            ProblematiqueDirection(
                id="dir-1", title="Existing", description="D", paper_ids=["p1"],
            )
        ]

        from src.topic_discovery.trend_tracker import delta_cluster_directions
        router = _make_mock_router("{}")
        dirs, changed = await delta_cluster_directions(
            [], existing, sample_papers, router
        )

        assert len(dirs) == 1
        assert len(changed) == 0

    @pytest.mark.asyncio
    async def test_invalid_direction_id(self, sample_papers, sample_annotations):
        existing = [
            ProblematiqueDirection(
                id="dir-1", title="Existing", description="D", paper_ids=["p1"],
            )
        ]
        new_ann = [sample_annotations[1]]

        result_json = json.dumps({
            "assignments": [{"annotation_index": 0, "direction_id": "NONEXISTENT"}],
            "new_directions": [],
        })
        router = _make_mock_router(result_json)

        from src.topic_discovery.trend_tracker import delta_cluster_directions
        dirs, changed = await delta_cluster_directions(
            new_ann, existing, sample_papers, router
        )

        assert len(dirs) == 1
        assert "p2" not in dirs[0].paper_ids  # invalid ID ignored
        assert len(changed) == 0


# ===========================================================================
# Compress directions tests
# ===========================================================================


class TestCompressDirections:
    @pytest.mark.asyncio
    async def test_under_cap_returns_unchanged(self):
        dirs = [
            ProblematiqueDirection(
                id=f"d{i}", title=f"Dir {i}", description="D", paper_ids=[f"p{i}"]
            )
            for i in range(5)
        ]
        router = _make_mock_router("[]")

        from src.topic_discovery.trend_tracker import compress_directions
        result = await compress_directions(dirs, router, max_directions=10)

        assert len(result) == 5  # unchanged
        assert result is dirs  # same list object

    @pytest.mark.asyncio
    async def test_merge_over_cap(self):
        dirs = [
            ProblematiqueDirection(
                id=f"d{i}", title=f"Dir {i}", description="D", paper_ids=[f"p{i}"]
            )
            for i in range(12)
        ]
        merged_json = json.dumps([
            {
                "title": "Merged 1",
                "description": "Combined",
                "dominant_tensions": ["A ↔ B"],
                "dominant_mediators": [],
                "dominant_scale": "textual",
                "dominant_gap": "mediational_gap",
                "merged_from": ["d0", "d1", "d2", "d3", "d4", "d5"],
                "paper_ids": ["p0", "p1", "p2", "p3", "p4", "p5"],
            },
            {
                "title": "Merged 2",
                "description": "Combined",
                "dominant_tensions": ["C ↔ D"],
                "dominant_mediators": [],
                "dominant_scale": "perceptual",
                "dominant_gap": "temporal_flattening",
                "merged_from": ["d6", "d7", "d8", "d9", "d10", "d11"],
                "paper_ids": ["p6", "p7", "p8", "p9", "p10", "p11"],
            },
        ])
        router = _make_mock_router(merged_json)

        from src.topic_discovery.trend_tracker import compress_directions
        result = await compress_directions(dirs, router, max_directions=10)

        assert len(result) == 2
        all_pids = set()
        for d in result:
            all_pids.update(d.paper_ids)
        assert len(all_pids) == 12  # no orphans

    @pytest.mark.asyncio
    async def test_llm_failure_returns_original(self):
        dirs = [
            ProblematiqueDirection(
                id=f"d{i}", title=f"Dir {i}", description="D", paper_ids=[f"p{i}"]
            )
            for i in range(12)
        ]
        router = MagicMock()
        router.complete.side_effect = RuntimeError("LLM error")

        from src.topic_discovery.trend_tracker import compress_directions
        result = await compress_directions(dirs, router, max_directions=10)

        assert len(result) == 12  # unchanged


# ===========================================================================
# DB delete directions/topics tests
# ===========================================================================


class TestDBDeleteDirectionsAndTopics:
    def test_delete_all(self, tmp_db):
        # Insert directions and topics
        d1 = ProblematiqueDirection(title="D1", description="Desc")
        d1_id = tmp_db.insert_direction(d1)
        t1 = TopicProposal(
            title="T1", research_question="Q", gap_description="G", direction_id=d1_id,
        )
        tmp_db.insert_topic(t1)

        d2 = ProblematiqueDirection(title="D2", description="Desc")
        d2_id = tmp_db.insert_direction(d2)
        t2 = TopicProposal(
            title="T2", research_question="Q", gap_description="G", direction_id=d2_id,
        )
        tmp_db.insert_topic(t2)

        assert len(tmp_db.get_directions(limit=10)) == 2
        assert len(tmp_db.get_topics(limit=10)) == 2

        tmp_db.delete_all_directions_and_topics()

        assert len(tmp_db.get_directions(limit=10)) == 0
        assert len(tmp_db.get_topics(limit=10)) == 0

    def test_delete_topics_for_direction(self, tmp_db):
        d1 = ProblematiqueDirection(title="D1", description="Desc")
        d1_id = tmp_db.insert_direction(d1)
        for i in range(3):
            tmp_db.insert_topic(TopicProposal(
                title=f"T{i}", research_question="Q", gap_description="G",
                direction_id=d1_id,
            ))

        d2 = ProblematiqueDirection(title="D2", description="Desc")
        d2_id = tmp_db.insert_direction(d2)
        tmp_db.insert_topic(TopicProposal(
            title="T_other", research_question="Q", gap_description="G",
            direction_id=d2_id,
        ))

        tmp_db.delete_topics_for_direction(d1_id)

        # D1 topics gone, D2 topic remains
        assert len(tmp_db.get_topics_by_direction(d1_id, limit=10)) == 0
        assert len(tmp_db.get_topics_by_direction(d2_id, limit=10)) == 1


# ===========================================================================
# Direction recency_score persistence + sort order
# ===========================================================================


class TestDirectionRecencyScoreDB:
    def test_persist_recency_score(self, tmp_db):
        d = ProblematiqueDirection(
            title="D1", description="Desc", recency_score=0.75,
        )
        d_id = tmp_db.insert_direction(d)
        fetched = tmp_db.get_direction(d_id)
        assert abs(fetched.recency_score - 0.75) < 1e-9

    def test_sort_by_recency_desc(self, tmp_db):
        tmp_db.insert_direction(ProblematiqueDirection(
            title="Low", description="", recency_score=0.1,
        ))
        tmp_db.insert_direction(ProblematiqueDirection(
            title="High", description="", recency_score=0.9,
        ))
        tmp_db.insert_direction(ProblematiqueDirection(
            title="Mid", description="", recency_score=0.5,
        ))

        dirs = tmp_db.get_directions(limit=10)
        assert dirs[0].title == "High"
        assert dirs[1].title == "Mid"
        assert dirs[2].title == "Low"
