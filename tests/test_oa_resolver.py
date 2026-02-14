"""Tests for the multi-source OA resolver."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge_base.models import Paper, PaperStatus
from src.reference_acquisition.oa_resolver import (
    OAResolver,
    _extract_arxiv_id,
    _jaccard_similarity,
)


# ---------------------------------------------------------------------------
# Helper to create test papers
# ---------------------------------------------------------------------------


def _make_paper(**kwargs) -> Paper:
    defaults = {
        "id": "test-id-1",
        "title": "Attention Is All You Need",
        "authors": ["Vaswani"],
        "journal": "NeurIPS",
        "year": 2017,
        "doi": "10.5555/3295222.3295349",
        "status": PaperStatus.DISCOVERED,
    }
    defaults.update(kwargs)
    return Paper(**defaults)


# ---------------------------------------------------------------------------
# Unit tests: Jaccard similarity
# ---------------------------------------------------------------------------


class TestJaccardSimilarity:
    def test_identical_strings(self):
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert _jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        sim = _jaccard_similarity("attention is all you need", "attention mechanisms in neural networks")
        assert 0.0 < sim < 1.0

    def test_empty_string(self):
        assert _jaccard_similarity("", "hello") == 0.0
        assert _jaccard_similarity("hello", "") == 0.0

    def test_case_insensitive(self):
        assert _jaccard_similarity("Hello World", "hello world") == 1.0


# ---------------------------------------------------------------------------
# Unit tests: arXiv ID extraction
# ---------------------------------------------------------------------------


class TestArxivIdExtraction:
    def test_from_external_ids(self):
        paper = _make_paper(external_ids={"ArXiv": "1706.03762"})
        assert _extract_arxiv_id(paper) == "1706.03762"

    def test_from_doi(self):
        paper = _make_paper(doi="10.48550/arXiv.2301.12345")
        assert _extract_arxiv_id(paper) == "2301.12345"

    def test_from_doi_with_version(self):
        paper = _make_paper(doi="10.48550/arXiv.2301.12345v2")
        assert _extract_arxiv_id(paper) == "2301.12345v2"

    def test_from_url(self):
        paper = _make_paper(url="https://arxiv.org/abs/2301.12345")
        assert _extract_arxiv_id(paper) == "2301.12345"

    def test_from_pdf_url(self):
        paper = _make_paper(url="https://arxiv.org/pdf/2301.12345")
        assert _extract_arxiv_id(paper) == "2301.12345"

    def test_no_arxiv_id(self):
        paper = _make_paper(external_ids={}, doi="10.1234/test", url="https://example.com")
        assert _extract_arxiv_id(paper) is None

    def test_empty_external_ids(self):
        paper = _make_paper(external_ids={})
        assert _extract_arxiv_id(paper) is None


# ---------------------------------------------------------------------------
# Unit tests: Unpaywall response parsing
# ---------------------------------------------------------------------------


class TestUnpaywallParsing:
    @pytest.mark.asyncio
    async def test_best_oa_location(self):
        resolver = OAResolver()
        mock_client = AsyncMock()
        mock_client.get_oa_urls = AsyncMock(return_value=["https://example.com/paper.pdf"])
        resolver._unpaywall = mock_client

        paper = _make_paper(doi="10.1234/test")
        url = await resolver._try_unpaywall(paper.doi)
        assert url == "https://example.com/paper.pdf"

    @pytest.mark.asyncio
    async def test_no_oa(self):
        resolver = OAResolver()
        mock_client = AsyncMock()
        mock_client.get_oa_urls = AsyncMock(return_value=[])
        resolver._unpaywall = mock_client

        url = await resolver._try_unpaywall("10.1234/closed")
        assert url is None

    @pytest.mark.asyncio
    async def test_unpaywall_error(self):
        resolver = OAResolver()
        mock_client = AsyncMock()
        mock_client.get_oa_urls = AsyncMock(side_effect=Exception("API error"))
        resolver._unpaywall = mock_client

        url = await resolver._try_unpaywall("10.1234/error")
        assert url is None


# ---------------------------------------------------------------------------
# Unit tests: CORE search
# ---------------------------------------------------------------------------


class TestCORESearch:
    @pytest.mark.asyncio
    async def test_doi_search_success(self):
        resolver = OAResolver()
        mock_client = AsyncMock()
        mock_client.search_by_doi = AsyncMock(return_value="https://core.ac.uk/download/pdf/123.pdf")
        mock_client.search_by_title = AsyncMock(return_value=[])
        resolver._core = mock_client

        paper = _make_paper(doi="10.1234/test")
        url = await resolver._try_core(paper)
        assert url == "https://core.ac.uk/download/pdf/123.pdf"

    @pytest.mark.asyncio
    async def test_title_search_high_similarity(self):
        resolver = OAResolver()
        mock_client = AsyncMock()
        mock_client.search_by_doi = AsyncMock(return_value=None)
        mock_client.search_by_title = AsyncMock(return_value=[
            {
                "title": "Attention Is All You Need",
                "downloadUrl": "https://core.ac.uk/download/456.pdf",
            }
        ])
        resolver._core = mock_client

        paper = _make_paper(title="Attention Is All You Need")
        url = await resolver._try_core(paper)
        assert url == "https://core.ac.uk/download/456.pdf"

    @pytest.mark.asyncio
    async def test_title_search_low_similarity_rejected(self):
        resolver = OAResolver()
        mock_client = AsyncMock()
        mock_client.search_by_doi = AsyncMock(return_value=None)
        mock_client.search_by_title = AsyncMock(return_value=[
            {
                "title": "Completely Different Paper About Cooking",
                "downloadUrl": "https://core.ac.uk/download/wrong.pdf",
            }
        ])
        resolver._core = mock_client

        paper = _make_paper(title="Attention Is All You Need")
        url = await resolver._try_core(paper)
        assert url is None


# ---------------------------------------------------------------------------
# Unit tests: arXiv resolution
# ---------------------------------------------------------------------------


class TestArxivResolution:
    def test_arxiv_url_construction(self):
        resolver = OAResolver()
        paper = _make_paper(external_ids={"ArXiv": "1706.03762"})
        url = resolver._try_arxiv(paper)
        assert url == "https://arxiv.org/pdf/1706.03762.pdf"

    def test_no_arxiv_returns_none(self):
        resolver = OAResolver()
        paper = _make_paper(external_ids={})
        url = resolver._try_arxiv(paper)
        assert url is None


# ---------------------------------------------------------------------------
# Unit tests: Europe PMC
# ---------------------------------------------------------------------------


class TestEuropePMC:
    @pytest.mark.asyncio
    async def test_pmcid_found(self):
        resolver = OAResolver()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resultList": {
                "result": [{"pmcid": "PMC1234567"}]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            paper = _make_paper(doi="10.1234/test")
            url = await resolver._try_europepmc(paper)
            assert url is not None
            assert "PMC1234567" in url

    @pytest.mark.asyncio
    async def test_no_pmcid(self):
        resolver = OAResolver()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resultList": {"result": [{"title": "Some paper"}]}
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            paper = _make_paper(doi="10.1234/test")
            url = await resolver._try_europepmc(paper)
            assert url is None

    @pytest.mark.asyncio
    async def test_pmid_from_external_ids(self):
        resolver = OAResolver()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resultList": {
                "result": [{"pmcid": "PMC9999999"}]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            paper = _make_paper(doi=None, external_ids={"PMID": "12345678"})
            url = await resolver._try_europepmc(paper)
            assert url is not None
            assert "PMC9999999" in url


# ---------------------------------------------------------------------------
# Unit tests: Priority order
# ---------------------------------------------------------------------------


class TestPriorityOrder:
    @pytest.mark.asyncio
    async def test_stops_at_first_success(self):
        """Should stop after Unpaywall succeeds, not call CORE/arXiv."""
        resolver = OAResolver()

        mock_unpaywall = AsyncMock()
        mock_unpaywall.get_oa_urls = AsyncMock(return_value=["https://unpaywall.org/paper.pdf"])
        resolver._unpaywall = mock_unpaywall

        mock_core = AsyncMock()
        mock_core.search_by_doi = AsyncMock(return_value="https://core.ac.uk/paper.pdf")
        resolver._core = mock_core

        paper = _make_paper(doi="10.1234/test")
        url = await resolver.resolve_pdf_url(paper)

        assert url == "https://unpaywall.org/paper.pdf"
        # CORE should not have been called
        mock_core.search_by_doi.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_through_to_core(self):
        """If Unpaywall fails, should try CORE."""
        resolver = OAResolver()

        mock_unpaywall = AsyncMock()
        mock_unpaywall.get_oa_urls = AsyncMock(return_value=[])
        resolver._unpaywall = mock_unpaywall

        mock_core = AsyncMock()
        mock_core.search_by_doi = AsyncMock(return_value="https://core.ac.uk/paper.pdf")
        resolver._core = mock_core

        paper = _make_paper(doi="10.1234/test")
        url = await resolver.resolve_pdf_url(paper)

        assert url == "https://core.ac.uk/paper.pdf"

    @pytest.mark.asyncio
    async def test_falls_through_to_arxiv(self):
        """If Unpaywall and CORE fail, should try arXiv."""
        resolver = OAResolver()

        mock_unpaywall = AsyncMock()
        mock_unpaywall.get_oa_urls = AsyncMock(return_value=[])
        resolver._unpaywall = mock_unpaywall

        mock_core = AsyncMock()
        mock_core.search_by_doi = AsyncMock(return_value=None)
        mock_core.search_by_title = AsyncMock(return_value=[])
        resolver._core = mock_core

        paper = _make_paper(
            doi="10.1234/test",
            external_ids={"ArXiv": "1706.03762"},
        )
        url = await resolver.resolve_pdf_url(paper)

        assert url == "https://arxiv.org/pdf/1706.03762.pdf"


# ---------------------------------------------------------------------------
# Unit tests: Batch resolution
# ---------------------------------------------------------------------------


class TestBatchResolution:
    @pytest.mark.asyncio
    async def test_resolve_many(self):
        resolver = OAResolver()

        # Mock resolve_pdf_url to return URL for first paper only
        call_count = 0
        async def mock_resolve(paper):
            nonlocal call_count
            call_count += 1
            if paper.doi == "10.1234/found":
                return "https://example.com/found.pdf"
            return None

        resolver.resolve_pdf_url = mock_resolve

        papers = [
            _make_paper(id="p1", doi="10.1234/found"),
            _make_paper(id="p2", doi="10.1234/notfound"),
        ]
        results = await resolver.resolve_many(papers)

        assert results["p1"] == "https://example.com/found.pdf"
        assert results["p2"] is None
        assert call_count == 2


# ---------------------------------------------------------------------------
# Unit tests: download_with_fallback
# ---------------------------------------------------------------------------


class TestDownloadWithFallback:
    @pytest.mark.asyncio
    async def test_first_url_succeeds(self):
        from src.reference_acquisition.downloader import PDFDownloader

        downloader = PDFDownloader()
        paper = _make_paper()

        with patch.object(downloader, "download_pdf", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = "/path/to/paper.pdf"

            result = await downloader.download_with_fallback(
                paper, ["https://url1.com/a.pdf", "https://url2.com/b.pdf"]
            )

            assert result == "/path/to/paper.pdf"
            assert mock_dl.call_count == 1

    @pytest.mark.asyncio
    async def test_second_url_succeeds(self):
        from src.reference_acquisition.downloader import PDFDownloader

        downloader = PDFDownloader()
        paper = _make_paper()

        with patch.object(downloader, "download_pdf", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = [None, "/path/to/paper.pdf"]

            result = await downloader.download_with_fallback(
                paper, ["https://url1.com/a.pdf", "https://url2.com/b.pdf"]
            )

            assert result == "/path/to/paper.pdf"
            assert mock_dl.call_count == 2

    @pytest.mark.asyncio
    async def test_all_urls_fail(self):
        from src.reference_acquisition.downloader import PDFDownloader

        downloader = PDFDownloader()
        paper = _make_paper()

        with patch.object(downloader, "download_pdf", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = None

            result = await downloader.download_with_fallback(
                paper, ["https://url1.com/a.pdf", "https://url2.com/b.pdf"]
            )

            assert result is None
            assert mock_dl.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_url_list(self):
        from src.reference_acquisition.downloader import PDFDownloader

        downloader = PDFDownloader()
        paper = _make_paper()

        result = await downloader.download_with_fallback(paper, [])
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests: UnpaywallClient
# ---------------------------------------------------------------------------


class TestUnpaywallClient:
    @pytest.mark.asyncio
    async def test_get_oa_urls_best_location(self):
        from src.utils.api_clients import UnpaywallClient

        client = UnpaywallClient(email="test@test.com")

        with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "best_oa_location": {"url_for_pdf": "https://best.pdf"},
                "oa_locations": [
                    {"url_for_pdf": "https://best.pdf"},
                    {"url_for_pdf": "https://alt.pdf"},
                ],
            }
            urls = await client.get_oa_urls("10.1234/test")
            assert urls == ["https://best.pdf", "https://alt.pdf"]

    @pytest.mark.asyncio
    async def test_get_oa_urls_no_pdf(self):
        from src.utils.api_clients import UnpaywallClient

        client = UnpaywallClient(email="test@test.com")

        with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "best_oa_location": None,
                "oa_locations": [],
            }
            urls = await client.get_oa_urls("10.1234/closed")
            assert urls == []

    @pytest.mark.asyncio
    async def test_get_oa_urls_api_error(self):
        from src.utils.api_clients import UnpaywallClient

        client = UnpaywallClient(email="test@test.com")

        with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("API error")
            urls = await client.get_oa_urls("10.1234/error")
            assert urls == []


# ---------------------------------------------------------------------------
# Unit tests: COREClient
# ---------------------------------------------------------------------------


class TestCOREClient:
    @pytest.mark.asyncio
    async def test_search_by_doi(self):
        from src.utils.api_clients import COREClient

        client = COREClient()

        with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "results": [{"downloadUrl": "https://core.ac.uk/dl/123.pdf"}]
            }
            url = await client.search_by_doi("10.1234/test")
            assert url == "https://core.ac.uk/dl/123.pdf"

    @pytest.mark.asyncio
    async def test_search_by_doi_not_found(self):
        from src.utils.api_clients import COREClient

        client = COREClient()

        with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"results": []}
            url = await client.search_by_doi("10.1234/missing")
            assert url is None

    @pytest.mark.asyncio
    async def test_search_by_title(self):
        from src.utils.api_clients import COREClient

        client = COREClient()

        with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "results": [
                    {"title": "Test Paper", "downloadUrl": "https://core.ac.uk/dl/456.pdf"},
                    {"title": "No URL Paper"},
                ]
            }
            results = await client.search_by_title("Test Paper")
            assert len(results) == 1
            assert results[0]["downloadUrl"] == "https://core.ac.uk/dl/456.pdf"


# ---------------------------------------------------------------------------
# Unit tests: external_ids in Paper model
# ---------------------------------------------------------------------------


class TestExternalIds:
    def test_paper_external_ids_default_empty(self):
        paper = _make_paper()
        assert paper.external_ids == {}

    def test_paper_external_ids_populated(self):
        paper = _make_paper(external_ids={"ArXiv": "1706.03762", "PMID": "12345"})
        assert paper.external_ids["ArXiv"] == "1706.03762"
        assert paper.external_ids["PMID"] == "12345"

    def test_s2_paper_populates_external_ids(self):
        from src.journal_monitor.sources.semantic_scholar import _s2_paper_to_paper

        raw = {
            "title": "Test",
            "authors": [],
            "year": 2024,
            "venue": "Test",
            "externalIds": {
                "DOI": "10.1234/test",
                "ArXiv": "2301.12345",
                "PMID": "99999",
                "CorpusId": 12345,
            },
            "paperId": "abc",
        }
        paper = _s2_paper_to_paper(raw, "Test")
        assert paper.external_ids["ArXiv"] == "2301.12345"
        assert paper.external_ids["PMID"] == "99999"
        assert paper.external_ids["CorpusId"] == "12345"


# ---------------------------------------------------------------------------
# Integration tests (require network, marked for optional execution)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestOAResolverIntegration:
    """Integration tests that make real API calls. Run with: pytest -m integration"""

    @pytest.mark.asyncio
    async def test_unpaywall_real_doi(self):
        """Test Unpaywall with a known OA paper (arXiv)."""
        from src.utils.api_clients import UnpaywallClient

        client = UnpaywallClient()
        try:
            urls = await client.get_oa_urls("10.48550/arXiv.1706.03762")
            # This DOI should have OA URLs
            assert isinstance(urls, list)
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_resolve_arxiv_paper(self):
        """Test full resolution for a known arXiv paper."""
        resolver = OAResolver()
        paper = _make_paper(
            title="Attention Is All You Need",
            doi="10.48550/arXiv.1706.03762",
            external_ids={"ArXiv": "1706.03762"},
        )
        try:
            url = await resolver.resolve_pdf_url(paper)
            assert url is not None
        finally:
            await resolver.close()

    @pytest.mark.asyncio
    async def test_europepmc_real_doi(self):
        """Test Europe PMC with a known PMC paper."""
        resolver = OAResolver()
        # A well-known OA paper with PMC
        paper = _make_paper(
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            doi="10.18653/v1/N19-1423",
        )
        try:
            url = await resolver._try_europepmc(paper)
            # May or may not find a PMCID — just ensure no crash
            assert url is None or isinstance(url, str)
        finally:
            await resolver.close()
