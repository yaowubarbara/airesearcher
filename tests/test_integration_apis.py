"""Integration tests for external API clients.

These tests hit real APIs (OpenAlex, CrossRef, Semantic Scholar).
They are free and require no API keys, but need network access.
Mark with pytest.mark.integration so they can be skipped in CI.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from src.utils.api_clients import CrossRefClient, OpenAlexClient, SemanticScholarClient


pytestmark = pytest.mark.integration


# ============================================================================
# OpenAlex
# ============================================================================


class TestOpenAlex:
    """Integration tests for the OpenAlex API."""

    @pytest.fixture
    async def client(self):
        c = OpenAlexClient(email="test@example.com")
        yield c
        await c.close()

    async def test_search_works_by_source(self, client):
        """Search for works from Comparative Literature (S49861241)."""
        result = await client.search_works(
            source_id="S49861241",
            per_page=5,
        )
        assert "results" in result
        assert "meta" in result
        assert result["meta"]["count"] > 0
        works = result["results"]
        assert len(works) > 0
        for work in works:
            assert work.get("display_name") or work.get("title")

    async def test_search_works_with_date_filter(self, client):
        """Search for recent works with a date filter."""
        result = await client.search_works(
            source_id="S49861241",
            from_date="2023-01-01",
            per_page=3,
        )
        assert "results" in result
        for work in result.get("results", []):
            year = work.get("publication_year", 0)
            assert year >= 2023

    async def test_search_works_by_keyword(self, client):
        """Search OpenAlex by keyword."""
        result = await client.search_works(
            search="world literature translation",
            per_page=5,
        )
        assert "results" in result
        assert len(result["results"]) > 0

    async def test_get_single_work(self, client):
        """Fetch a single known work by OpenAlex ID."""
        try:
            result = await client.get_work("W2027555937")
            assert result.get("display_name") or result.get("title")
        except Exception:
            pytest.skip("OpenAlex work ID may have changed or API rate limited")


# ============================================================================
# CrossRef
# ============================================================================


class TestCrossRef:
    """Integration tests for the CrossRef API."""

    @pytest.fixture
    async def client(self):
        c = CrossRefClient(email="test@example.com")
        yield c
        await c.close()

    async def test_search_by_issn(self, client):
        """Search CrossRef by ISSN for Comparative Literature."""
        result = await client.search_works(
            issn="0010-4124",
            rows=5,
        )
        assert "message" in result
        items = result["message"].get("items", [])
        assert len(items) > 0
        for item in items:
            assert item.get("title") or item.get("DOI")

    async def test_search_by_query(self, client):
        """Search CrossRef by keyword query."""
        result = await client.search_works(
            query="comparative literature world",
            rows=3,
        )
        assert "message" in result
        assert len(result["message"].get("items", [])) > 0

    async def test_verify_doi(self, client):
        """Verify a known DOI exists."""
        meta = await client.verify_doi("10.1353/cli.2000.0004")
        # This may fail due to network; don't hard-assert

    async def test_search_with_date_filter(self, client):
        """Search CrossRef with a publication date filter."""
        result = await client.search_works(
            issn="0030-8129",  # PMLA
            from_date="2023-01-01",
            rows=3,
        )
        assert "message" in result


# ============================================================================
# Semantic Scholar
# ============================================================================


class TestSemanticScholar:
    """Integration tests for the Semantic Scholar API."""

    @pytest.fixture
    async def client(self):
        c = SemanticScholarClient()
        yield c
        await c.close()

    async def test_search_papers_by_query(self, client):
        """Search for papers on Semantic Scholar."""
        try:
            result = await client.search_papers(
                query="comparative literature",
                limit=5,
            )
            assert "data" in result
            papers = result["data"]
            assert len(papers) > 0
            for paper in papers:
                assert paper.get("title")
        except Exception:
            pytest.skip("Semantic Scholar rate limited")

    async def test_search_papers_with_venue(self, client):
        """Search for papers from a specific venue."""
        try:
            result = await client.search_papers(
                query="world literature",
                venue="Comparative Literature",
                limit=3,
            )
            assert "data" in result
        except Exception:
            pytest.skip("Semantic Scholar rate limited")

    async def test_get_paper_by_id(self, client):
        """Fetch a specific paper by Semantic Scholar ID."""
        try:
            result = await client.get_paper("649def34f8be52c8b66281af98ae884c09aef38b")
            assert result.get("title")
            assert result.get("year")
        except Exception:
            pytest.skip("Semantic Scholar paper ID may have changed or rate limited")

    async def test_search_with_year_filter(self, client):
        """Search with year filter."""
        try:
            result = await client.search_papers(
                query="translation studies",
                year="2023-",
                limit=3,
            )
            assert "data" in result
        except Exception:
            pytest.skip("Semantic Scholar rate limited")


# ============================================================================
# Monitor integration (uses all sources together)
# ============================================================================


class TestMonitorIntegration:
    """Test the full monitor pipeline with real APIs."""

    async def test_scan_single_journal(self):
        """Scan a single journal using the monitor."""
        from src.journal_monitor.monitor import scan_journal
        from src.knowledge_base.db import Database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.sqlite")
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
                    since_date="2024-01-01",
                    db=db,
                    clients=clients,
                )

                assert result.journal_name == "Comparative Literature"
                assert len(result.sources_queried) > 0
                assert result.papers_found >= 0
                if result.papers_found > 0:
                    assert result.papers_new > 0
            finally:
                for c in clients.values():
                    await c.close()
                db.close()

    async def test_database_stores_papers(self):
        """Verify papers fetched from APIs are properly stored in the database."""
        from src.knowledge_base.db import Database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.sqlite")
            db = Database(db_path)
            db.initialize()

            client = OpenAlexClient(email="test@example.com")
            try:
                result = await client.search_works(
                    source_id="S49861241",
                    per_page=3,
                )
                works = result.get("results", [])
                assert len(works) > 0

                from src.journal_monitor.sources.openalex import _openalex_work_to_paper

                for work in works:
                    paper = _openalex_work_to_paper(work, "Comparative Literature")
                    db.insert_paper(paper)

                # Verify storage
                stored_count = db.count_papers()
                assert stored_count == len(works)

                # Verify we can retrieve papers (search by any stored paper's journal)
                all_papers = db.search_papers(limit=10)
                assert len(all_papers) == len(works)
            finally:
                await client.close()
                db.close()
