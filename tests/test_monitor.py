"""Tests for the journal monitor module."""

from __future__ import annotations

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import Language, Paper, PaperStatus


@pytest.fixture
def db(tmp_path):
    """Create a temporary test database."""
    db = Database(tmp_path / "test.sqlite")
    db.initialize()
    yield db
    db.close()


class TestDatabase:
    def test_insert_and_get_paper(self, db):
        paper = Paper(
            title="Test Paper on World Literature",
            authors=["Author One", "Author Two"],
            abstract="This is a test abstract.",
            journal="Comparative Literature",
            year=2024,
            doi="10.1234/test.001",
            language=Language.EN,
            keywords=["world literature", "comparison"],
            status=PaperStatus.DISCOVERED,
        )
        paper_id = db.insert_paper(paper)
        assert paper_id

        retrieved = db.get_paper(paper_id)
        assert retrieved is not None
        assert retrieved.title == "Test Paper on World Literature"
        assert retrieved.authors == ["Author One", "Author Two"]
        assert retrieved.doi == "10.1234/test.001"
        assert retrieved.language == Language.EN

    def test_get_paper_by_doi(self, db):
        paper = Paper(
            title="DOI Test",
            authors=["Test Author"],
            journal="PMLA",
            year=2023,
            doi="10.5678/doi.test",
        )
        db.insert_paper(paper)

        found = db.get_paper_by_doi("10.5678/doi.test")
        assert found is not None
        assert found.title == "DOI Test"

    def test_duplicate_doi_ignored(self, db):
        paper1 = Paper(
            title="First Paper",
            authors=["Author A"],
            journal="PMLA",
            year=2023,
            doi="10.1111/dup",
        )
        paper2 = Paper(
            title="Duplicate Paper",
            authors=["Author B"],
            journal="PMLA",
            year=2023,
            doi="10.1111/dup",
        )
        db.insert_paper(paper1)
        db.insert_paper(paper2)  # Should be ignored

        assert db.count_papers() == 1

    def test_search_papers_by_journal(self, db):
        for i in range(5):
            db.insert_paper(Paper(
                title=f"Paper {i}",
                authors=[f"Author {i}"],
                journal="Comparative Literature" if i < 3 else "PMLA",
                year=2024,
            ))

        cl_papers = db.search_papers(journal="Comparative Literature")
        assert len(cl_papers) == 3

        pmla_papers = db.search_papers(journal="PMLA")
        assert len(pmla_papers) == 2

    def test_search_papers_by_language(self, db):
        db.insert_paper(Paper(
            title="English Paper",
            authors=["Author"],
            journal="CL",
            year=2024,
            language=Language.EN,
        ))
        db.insert_paper(Paper(
            title="中文论文",
            authors=["作者"],
            journal="中国比较文学",
            year=2024,
            language=Language.ZH,
        ))

        en_papers = db.search_papers(language=Language.EN)
        assert len(en_papers) == 1
        assert en_papers[0].title == "English Paper"

        zh_papers = db.search_papers(language=Language.ZH)
        assert len(zh_papers) == 1
        assert zh_papers[0].title == "中文论文"

    def test_reflexion_memory(self, db):
        from src.knowledge_base.models import ReflexionEntry

        entry = ReflexionEntry(
            category="writing_pattern",
            observation="Tends to use passive voice too much in section 3",
            source="self_review_v1",
        )
        entry_id = db.insert_reflexion(entry)
        assert entry_id

        memories = db.get_reflexion_memories(category="writing_pattern")
        assert len(memories) == 1
        assert "passive voice" in memories[0].observation

    def test_topic_proposals(self, db):
        from src.knowledge_base.models import TopicProposal

        topic = TopicProposal(
            title="Translation and World Literature",
            research_question="How does translation shape canon formation?",
            gap_description="No study compares Chinese and French translation practices",
            novelty_score=0.8,
            feasibility_score=0.7,
            journal_fit_score=0.9,
            timeliness_score=0.6,
            overall_score=0.75,
        )
        topic_id = db.insert_topic(topic)
        assert topic_id

        topics = db.get_topics()
        assert len(topics) == 1
        assert topics[0].overall_score == 0.75
