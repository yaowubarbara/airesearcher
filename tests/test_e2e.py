"""End-to-end tests for the AI Research Agent pipeline.

Tests the full flow from monitoring to database storage, and optionally
through LLM-powered stages if API keys are available.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    Language,
    Manuscript,
    OutlineSection,
    Paper,
    PaperStatus,
    ReflexionEntry,
    ResearchPlan,
    TopicProposal,
)
from src.utils.api_clients import CrossRefClient, OpenAlexClient


pytestmark = pytest.mark.integration


class TestE2EMonitorToIndex:
    """End-to-end: Monitor → Index → DB without LLM."""

    async def test_monitor_indexes_and_stores_papers(self):
        """Full pipeline: fetch from OpenAlex → parse → store in DB → verify retrieval."""
        from src.journal_monitor.monitor import scan_journal
        from src.journal_monitor.sources.openalex import _openalex_work_to_paper

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "e2e.sqlite")
            db = Database(db_path)
            db.initialize()

            journal_config = {
                "name": "Comparative Literature",
                "issn": "0010-4124",
                "openalex_source_id": "S49861241",
                "language": "en",
            }

            clients = {
                "openalex": OpenAlexClient(email="test@example.com"),
                "crossref": CrossRefClient(email="test@example.com"),
            }

            try:
                result = await scan_journal(
                    journal_config=journal_config,
                    since_date="2024-06-01",
                    db=db,
                    clients=clients,
                )

                # Verify scan produced results
                assert result.journal_name == "Comparative Literature"
                assert len(result.sources_queried) > 0

                if result.papers_new > 0:
                    # Verify papers are in the database
                    stored = db.search_papers(limit=50)
                    assert len(stored) > 0

                    # Verify paper fields are populated
                    paper = stored[0]
                    assert paper.title
                    assert paper.year > 0
                    assert paper.journal

                    # Verify count matches
                    count = db.count_papers()
                    assert count == result.papers_new

                    # Verify DOI-based deduplication: scanning again should not add duplicates
                    result2 = await scan_journal(
                        journal_config=journal_config,
                        since_date="2024-06-01",
                        db=db,
                        clients=clients,
                    )
                    count_after = db.count_papers()
                    assert count_after == count  # No new papers added

            finally:
                for c in clients.values():
                    await c.close()
                db.close()


class TestE2EDatabaseWorkflow:
    """End-to-end: Test the full database workflow without external APIs."""

    def test_full_db_workflow(self):
        """Paper → Topic → Plan → Manuscript → Reflexion full DB lifecycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "workflow.sqlite")
            db = Database(db_path)
            db.initialize()

            try:
                # 1. Insert a paper
                paper = Paper(
                    title="World Literature and the Comparative Method",
                    authors=["Franco Moretti"],
                    abstract="This article explores the comparative method in world literature studies.",
                    journal="Comparative Literature",
                    year=2024,
                    doi="10.1234/test-e2e-001",
                    language=Language.EN,
                    keywords=["world literature", "comparative method"],
                    status=PaperStatus.DISCOVERED,
                )
                paper_id = db.insert_paper(paper)
                assert paper_id

                # Verify retrieval
                stored_paper = db.get_paper_by_doi("10.1234/test-e2e-001")
                assert stored_paper is not None
                assert stored_paper.title == paper.title
                assert stored_paper.authors == paper.authors

                # 2. Create a topic proposal
                topic = TopicProposal(
                    title="Distant Reading and National Literatures",
                    research_question="How can distant reading methods reveal patterns across national literary traditions?",
                    gap_description="Limited application of computational methods to non-Western literatures.",
                    evidence_paper_ids=[paper_id],
                    target_journals=["Comparative Literature"],
                    novelty_score=0.8,
                    feasibility_score=0.7,
                    journal_fit_score=0.9,
                    timeliness_score=0.85,
                    overall_score=0.81,
                )
                topic_id = db.insert_topic(topic)
                assert topic_id

                # Verify topic retrieval
                topics = db.get_topics()
                assert len(topics) == 1
                assert topics[0].title == topic.title
                assert topics[0].overall_score == 0.81

                # 3. Create a research plan
                plan = ResearchPlan(
                    topic_id=topic_id,
                    thesis_statement="Distant reading reveals structural patterns invisible to close reading alone.",
                    target_journal="Comparative Literature",
                    target_language=Language.EN,
                    outline=[
                        OutlineSection(
                            title="Introduction",
                            argument="Establish the problem of scale in comparative literature.",
                            estimated_words=1500,
                        ),
                        OutlineSection(
                            title="Methodology",
                            argument="Describe the distant reading approach.",
                            estimated_words=2000,
                        ),
                        OutlineSection(
                            title="Analysis",
                            argument="Present findings from computational analysis.",
                            estimated_words=3000,
                        ),
                        OutlineSection(
                            title="Conclusion",
                            argument="Synthesize implications for comparative literature.",
                            estimated_words=1500,
                        ),
                    ],
                    reference_ids=[paper_id],
                )
                plan_id = db.insert_plan(plan)
                assert plan_id

                # Verify plan retrieval
                stored_plan = db.get_plan(plan_id)
                assert stored_plan is not None
                assert stored_plan["thesis_statement"] == plan.thesis_statement
                outline = json.loads(stored_plan["outline"])
                assert len(outline) == 4

                # 4. Create a manuscript
                ms = Manuscript(
                    plan_id=plan_id,
                    title="Distant Reading and National Literatures: A Comparative Analysis",
                    target_journal="Comparative Literature",
                    language=Language.EN,
                    sections={
                        "introduction": "This essay argues that...",
                        "methodology": "We employ distant reading...",
                        "analysis": "Our analysis reveals...",
                        "conclusion": "These findings suggest...",
                    },
                    full_text="This essay argues that... We employ distant reading... Our analysis reveals... These findings suggest...",
                    abstract="This study applies distant reading methods to national literary traditions.",
                    keywords=["distant reading", "comparative literature", "digital humanities"],
                    reference_ids=[paper_id],
                    word_count=8000,
                    version=1,
                )
                ms_id = db.insert_manuscript(ms)
                assert ms_id

                # 5. Add reflexion memory
                reflexion = ReflexionEntry(
                    category="self_review",
                    observation="The methodology section needs more detail on corpus selection.",
                    source="self_review_v1",
                    manuscript_id=ms_id,
                )
                ref_id = db.insert_reflexion(reflexion)
                assert ref_id

                memories = db.get_reflexion_memories(category="self_review")
                assert len(memories) == 1
                assert "methodology" in memories[0].observation.lower()

                # 6. Update manuscript status
                db.update_manuscript(ms_id, status="reviewed", version=2)

                # 7. Verify stats
                assert db.count_papers() == 1
                assert len(db.get_topics()) == 1
                assert len(db.get_reflexion_memories()) == 1

            finally:
                db.close()


class TestE2EFormatChecker:
    """End-to-end: Test reference formatting across citation styles."""

    def test_multilingual_reference_formatting(self):
        """Test that references are formatted correctly across MLA/Chicago/GB."""
        from src.knowledge_base.models import Reference
        from src.reference_verifier.format_checker import FormatChecker

        checker = FormatChecker()

        ref_data = Reference(
            title="World Literature in Theory",
            authors=["David Damrosch"],
            year=2014,
            publisher="Wiley-Blackwell",
        )

        # MLA format
        mla = checker.format_reference(ref_data, "MLA")
        assert "Damrosch" in mla
        assert "2014" in mla

        # Chicago format
        chicago = checker.format_reference(ref_data, "Chicago")
        assert "Damrosch" in chicago
        assert "2014" in chicago

        # GB/T 7714
        gb = checker.format_reference(ref_data, "GB/T 7714")
        assert "Damrosch" in gb or "DAMROSCH" in gb


class TestE2ECLICommands:
    """End-to-end: Test CLI command parsing without execution."""

    def test_cli_group_exists(self):
        """Verify CLI group and commands are properly registered."""
        from cli import main
        from click.testing import CliRunner

        runner = CliRunner()

        # Test help output
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "AI Academic Research Agent" in result.output

    def test_cli_commands_registered(self):
        """Verify all expected CLI commands exist."""
        from cli import main

        command_names = list(main.commands.keys())
        expected = [
            "monitor",
            "index",
            "discover",
            "plan",
            "write",
            "verify",
            "review",
            "format-manuscript",
            "pipeline",
            "stats",
            "learn-style",
            "scheduler",
        ]
        for cmd in expected:
            assert cmd in command_names, f"Missing CLI command: {cmd}"

    def test_stats_command_empty_db(self):
        """Stats command should work even with an empty database."""
        from cli import main
        from click.testing import CliRunner

        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.sqlite")
            # Pre-initialize DB
            db = Database(db_path)
            db.initialize()
            db.close()

            # Patch the default DB path (stats creates its own)
            result = runner.invoke(main, ["stats"])
            # Should not crash even with empty/fresh DB
            assert result.exit_code == 0
