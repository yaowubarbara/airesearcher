"""Tests for the reference acquisition pipeline."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge_base.db import Database
from src.knowledge_base.models import Language, Paper, PaperStatus
from src.reference_acquisition.downloader import PDFDownloader
from src.reference_acquisition.searcher import ReferenceSearcher


# ---------------------------------------------------------------------------
# Unit tests: OA URL extraction
# ---------------------------------------------------------------------------


class TestOAURLExtraction:
    """Test that OA PDF URLs are correctly extracted from API responses."""

    def test_s2_pdf_url_extraction(self):
        """Semantic Scholar openAccessPdf → Paper.pdf_url."""
        from src.journal_monitor.sources.semantic_scholar import _s2_paper_to_paper

        raw = {
            "title": "Test Paper",
            "authors": [{"name": "Alice"}],
            "year": 2024,
            "venue": "Test Journal",
            "externalIds": {"DOI": "10.1234/test"},
            "paperId": "abc123",
            "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        }
        paper = _s2_paper_to_paper(raw, "Test Journal")
        assert paper.pdf_url == "https://example.com/paper.pdf"

    def test_s2_no_pdf_url(self):
        """Semantic Scholar with no openAccessPdf → pdf_url is None."""
        from src.journal_monitor.sources.semantic_scholar import _s2_paper_to_paper

        raw = {
            "title": "Closed Paper",
            "authors": [],
            "year": 2024,
            "venue": "Closed Journal",
            "externalIds": {},
            "paperId": "def456",
        }
        paper = _s2_paper_to_paper(raw, "Closed Journal")
        assert paper.pdf_url is None

    def test_openalex_pdf_url_from_primary_location(self):
        """OpenAlex primary_location.pdf_url → Paper.pdf_url."""
        from src.journal_monitor.sources.openalex import _openalex_work_to_paper

        work = {
            "display_name": "OA Paper",
            "authorships": [],
            "publication_year": 2024,
            "primary_location": {
                "source": {"display_name": "OA Journal"},
                "landing_page_url": "https://example.com/landing",
                "pdf_url": "https://example.com/oa.pdf",
            },
            "open_access": {"oa_url": "https://example.com/oa_landing"},
            "biblio": {},
        }
        paper = _openalex_work_to_paper(work, "OA Journal")
        assert paper.pdf_url == "https://example.com/oa.pdf"

    def test_openalex_pdf_url_from_oa_url(self):
        """OpenAlex open_access.oa_url as fallback → Paper.pdf_url."""
        from src.journal_monitor.sources.openalex import _openalex_work_to_paper

        work = {
            "display_name": "OA Paper 2",
            "authorships": [],
            "publication_year": 2024,
            "primary_location": {
                "source": {"display_name": "J"},
                "landing_page_url": "https://example.com",
            },
            "open_access": {"oa_url": "https://example.com/fallback"},
            "biblio": {},
        }
        paper = _openalex_work_to_paper(work, "J")
        assert paper.pdf_url == "https://example.com/fallback"

    def test_crossref_pdf_url_from_link(self):
        """CrossRef link array with application/pdf → Paper.pdf_url."""
        from src.journal_monitor.sources.crossref import _crossref_item_to_paper

        item = {
            "title": ["CR Paper"],
            "author": [],
            "DOI": "10.1234/cr",
            "issued": {"date-parts": [[2024]]},
            "link": [
                {"content-type": "application/pdf", "URL": "https://example.com/cr.pdf"},
                {"content-type": "text/html", "URL": "https://example.com/cr.html"},
            ],
        }
        paper = _crossref_item_to_paper(item, "CR Journal")
        assert paper.pdf_url == "https://example.com/cr.pdf"

    def test_crossref_no_pdf_link(self):
        """CrossRef with no PDF link → pdf_url is None."""
        from src.journal_monitor.sources.crossref import _crossref_item_to_paper

        item = {
            "title": ["No PDF Paper"],
            "author": [],
            "DOI": "10.1234/nopdf",
            "issued": {"date-parts": [[2024]]},
        }
        paper = _crossref_item_to_paper(item, "Journal")
        assert paper.pdf_url is None


# ---------------------------------------------------------------------------
# Unit tests: PDF validation
# ---------------------------------------------------------------------------


class TestPDFValidation:
    """Test PDF download validation logic."""

    def test_safe_filename_from_doi(self):
        """DOI-based filename generation."""
        paper = Paper(
            title="Test",
            journal="J",
            year=2024,
            doi="10.1234/test.paper/v1",
        )
        name = PDFDownloader._safe_filename(paper)
        assert "/" not in name
        assert "10.1234" in name

    def test_safe_filename_from_title(self):
        """Title-based fallback filename."""
        paper = Paper(
            title="A Long Paper Title With Spaces",
            journal="J",
            year=2024,
        )
        name = PDFDownloader._safe_filename(paper)
        assert " " not in name


# ---------------------------------------------------------------------------
# Unit tests: Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Test searcher deduplication logic."""

    def test_dedup_by_doi(self):
        """Papers with same DOI are deduplicated."""
        searcher = ReferenceSearcher()
        papers = [
            Paper(title="Paper A", journal="J", year=2024, doi="10.1234/same"),
            Paper(title="Paper B", journal="J", year=2024, doi="10.1234/same"),
            Paper(title="Paper C", journal="J", year=2024, doi="10.1234/different"),
        ]
        result = searcher._deduplicate(papers)
        assert len(result) == 2
        dois = [p.doi for p in result]
        assert "10.1234/same" in dois
        assert "10.1234/different" in dois

    def test_dedup_with_db(self):
        """Papers existing in DB are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.initialize()

            existing = Paper(
                title="Existing",
                journal="J",
                year=2024,
                doi="10.1234/existing",
            )
            db.insert_paper(existing)

            searcher = ReferenceSearcher(db=db)
            papers = [
                Paper(title="Existing Copy", journal="J", year=2024, doi="10.1234/existing"),
                Paper(title="New Paper", journal="J", year=2024, doi="10.1234/new"),
            ]
            result = searcher._deduplicate(papers)
            assert len(result) == 1
            assert result[0].doi == "10.1234/new"
            db.close()


# ---------------------------------------------------------------------------
# Unit tests: DB pdf_url field
# ---------------------------------------------------------------------------


class TestDBPdfUrl:
    """Test pdf_url field in database operations."""

    def test_paper_model_pdf_url(self):
        """Paper model accepts pdf_url."""
        paper = Paper(
            title="Test",
            journal="J",
            year=2024,
            pdf_url="https://example.com/test.pdf",
        )
        assert paper.pdf_url == "https://example.com/test.pdf"

    def test_insert_and_retrieve_pdf_url(self):
        """pdf_url is persisted and retrieved from DB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.initialize()

            paper = Paper(
                title="PDF Paper",
                journal="J",
                year=2024,
                doi="10.1234/pdftest",
                pdf_url="https://example.com/paper.pdf",
            )
            paper_id = db.insert_paper(paper)
            retrieved = db.get_paper(paper_id)
            assert retrieved is not None
            assert retrieved.pdf_url == "https://example.com/paper.pdf"
            db.close()

    def test_update_paper_pdf(self):
        """update_paper_pdf updates pdf fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.initialize()

            paper = Paper(title="Update Test", journal="J", year=2024, doi="10.1234/upd")
            paper_id = db.insert_paper(paper)

            db.update_paper_pdf(
                paper_id,
                pdf_url="https://example.com/updated.pdf",
                pdf_path="/tmp/updated.pdf",
                status=PaperStatus.PDF_DOWNLOADED,
            )

            retrieved = db.get_paper(paper_id)
            assert retrieved is not None
            assert retrieved.pdf_url == "https://example.com/updated.pdf"
            assert retrieved.pdf_path == "/tmp/updated.pdf"
            assert retrieved.status == PaperStatus.PDF_DOWNLOADED
            db.close()


# ---------------------------------------------------------------------------
# Unit tests: DB wishlist queries
# ---------------------------------------------------------------------------


class TestDBWishlist:
    """Test the papers-needing-PDF queries."""

    def test_get_papers_needing_pdf(self):
        """Papers without pdf_path and with discovered/metadata_only status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.initialize()

            # Paper without PDF — should appear in wishlist
            p1 = Paper(title="No PDF", journal="J", year=2024, doi="10.1/a")
            db.insert_paper(p1)

            # Paper with PDF — should NOT appear
            p2 = Paper(
                title="Has PDF", journal="J", year=2024, doi="10.1/b",
                pdf_path="/tmp/b.pdf", status=PaperStatus.INDEXED,
            )
            db.insert_paper(p2)

            needing = db.get_papers_needing_pdf()
            assert len(needing) == 1
            assert needing[0].title == "No PDF"
            db.close()

    def test_get_paper_by_title_prefix(self):
        """Find paper by title prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.initialize()

            db.insert_paper(Paper(title="Orientalism and Its Critics", journal="J", year=1978))
            result = db.get_paper_by_title_prefix("orientalism")
            assert result is not None
            assert "Orientalism" in result.title

            result2 = db.get_paper_by_title_prefix("nonexistent")
            assert result2 is None
            db.close()


# ---------------------------------------------------------------------------
# Unit tests: AcquisitionReport
# ---------------------------------------------------------------------------


class TestAcquisitionReport:
    """Test the acquisition report dataclass."""

    def test_report_summary(self):
        from src.reference_acquisition.pipeline import AcquisitionReport

        report = AcquisitionReport(
            query="test topic",
            found=50,
            papers_with_pdf_url=20,
            downloaded=15,
            failed_download=5,
            indexed=40,
            failed_index=2,
        )
        summary = report.summary()
        assert "test topic" in summary
        assert "50" in summary
        assert "15" in summary


# ---------------------------------------------------------------------------
# Unit tests: WebSearcher
# ---------------------------------------------------------------------------


class TestWebSearcher:
    """Test web searcher conversion methods."""

    def test_gbooks_to_paper(self):
        """Google Books volume → Paper conversion."""
        from src.reference_acquisition.web_searcher import WebSearcher

        item = {
            "volumeInfo": {
                "title": "Orientalism",
                "subtitle": "Western Conceptions of the Orient",
                "authors": ["Edward W. Said"],
                "publishedDate": "1978",
                "publisher": "Vintage Books",
                "description": "A groundbreaking study.",
                "language": "en",
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9780394740676"}
                ],
                "categories": ["Literary Criticism"],
                "previewLink": "https://books.google.com/preview",
            },
            "accessInfo": {
                "pdf": {"isAvailable": False},
                "epub": {"isAvailable": False},
            },
        }
        paper = WebSearcher._gbooks_to_paper(item)
        assert paper is not None
        assert paper.title == "Orientalism: Western Conceptions of the Orient"
        assert paper.authors == ["Edward W. Said"]
        assert paper.year == 1978
        assert paper.journal == "Vintage Books"

    def test_gbooks_no_title(self):
        """Google Books without title returns None."""
        from src.reference_acquisition.web_searcher import WebSearcher

        item = {"volumeInfo": {}}
        paper = WebSearcher._gbooks_to_paper(item)
        assert paper is None

    def test_openlibrary_to_paper(self):
        """Open Library doc → Paper conversion."""
        from src.reference_acquisition.web_searcher import WebSearcher

        doc = {
            "title": "Heart of Darkness",
            "author_name": ["Joseph Conrad"],
            "first_publish_year": 1899,
            "publisher": ["Blackwood's Magazine"],
            "key": "/works/OL15234W",
            "has_fulltext": True,
            "ia": ["heartdarkness00conr"],
            "language": ["eng"],
        }
        paper = WebSearcher._openlibrary_to_paper(doc)
        assert paper is not None
        assert paper.title == "Heart of Darkness"
        assert paper.year == 1899
        assert paper.pdf_url is not None
        assert "archive.org" in paper.pdf_url

    def test_deduplicate_by_title(self):
        """Title-based deduplication."""
        from src.reference_acquisition.web_searcher import WebSearcher

        papers = [
            Paper(title="The Great Gatsby", journal="Scribner", year=1925),
            Paper(title="the great gatsby", journal="Other", year=1925),
            Paper(title="Heart of Darkness", journal="Blackwood", year=1899),
        ]
        result = WebSearcher._deduplicate_by_title(papers)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Integration tests (real API calls — may be rate limited)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReferenceSearchIntegration:
    """Integration tests that hit real APIs."""

    @pytest.mark.asyncio
    async def test_search_openalex(self):
        """Search OpenAlex for a real topic."""
        searcher = ReferenceSearcher()
        papers = await searcher._search_openalex("comparative literature theory", 5)
        assert len(papers) > 0
        assert papers[0].title

    @pytest.mark.asyncio
    async def test_search_crossref(self):
        """Search CrossRef for a real topic."""
        searcher = ReferenceSearcher()
        papers = await searcher._search_crossref("postcolonial narratology", 5)
        assert len(papers) > 0

    @pytest.mark.asyncio
    async def test_full_search_topic(self):
        """Full multi-API search."""
        searcher = ReferenceSearcher()
        papers = await searcher.search_topic(
            "Chinese comparative literature epistemology",
            max_results_per_source=5,
        )
        assert len(papers) > 0
        # Check that some papers have pdf_url
        pdf_urls = [p for p in papers if p.pdf_url]
        # It's OK if none have PDFs for this query, just check no crash
        assert isinstance(pdf_urls, list)
