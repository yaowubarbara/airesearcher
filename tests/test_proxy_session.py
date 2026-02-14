"""Tests for institutional proxy session management."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.knowledge_base.models import Paper, PaperStatus
from src.reference_acquisition.proxy_session import InstitutionalProxy


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_paper(**kwargs) -> Paper:
    defaults = {
        "id": "test-id-1",
        "title": "Test Paper on Postcolonialism",
        "authors": ["Smith"],
        "journal": "PMLA",
        "year": 2023,
        "doi": "10.1234/test.5678",
        "status": PaperStatus.DISCOVERED,
    }
    defaults.update(kwargs)
    return Paper(**defaults)


def _write_config(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


FULL_CONFIG = """\
proxy:
  enabled: true
  type: ezproxy
  base_url: "https://proxy.university.edu"
credentials:
  username: "testuser"
  password_env: "TEST_PROXY_PASS"
publishers:
  - name: "JSTOR"
    domains: ["jstor.org", "www.jstor.org"]
  - name: "Springer"
    domains: ["link.springer.com", "springer.com"]
  - name: "Elsevier / ScienceDirect"
    domains: ["sciencedirect.com"]
"""

DISABLED_CONFIG = """\
proxy:
  enabled: false
  type: ezproxy
  base_url: "https://proxy.university.edu"
credentials:
  username: "testuser"
  password_env: "TEST_PROXY_PASS"
publishers: []
"""

PREFIX_CONFIG = """\
proxy:
  enabled: true
  type: prefix
  base_url: "https://proxy.university.edu:2048"
credentials:
  username: "testuser"
  password_env: "TEST_PROXY_PASS"
publishers:
  - name: "JSTOR"
    domains: ["jstor.org", "www.jstor.org"]
"""


# ---------------------------------------------------------------------------
# Config loading tests
# ---------------------------------------------------------------------------


class TestConfigLoading:
    def test_missing_config_file(self, tmp_path):
        proxy = InstitutionalProxy(config_path=tmp_path / "nonexistent.yaml")
        assert not proxy.is_configured

    def test_disabled_config(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, DISABLED_CONFIG)
        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)
            assert not proxy.is_configured

    def test_fully_configured(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, FULL_CONFIG)
        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)
            assert proxy.is_configured
            assert proxy.base_url == "https://proxy.university.edu"
            assert proxy.username == "testuser"
            assert proxy.password == "secret"
            assert proxy.proxy_type == "ezproxy"

    def test_missing_password_env(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, FULL_CONFIG)
        with patch.dict(os.environ, {}, clear=True):
            # Ensure env var is NOT set
            os.environ.pop("TEST_PROXY_PASS", None)
            proxy = InstitutionalProxy(config_path=cfg)
            assert not proxy.is_configured

    def test_missing_username(self, tmp_path):
        config = FULL_CONFIG.replace('username: "testuser"', 'username: ""')
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, config)
        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)
            assert not proxy.is_configured


# ---------------------------------------------------------------------------
# Publisher domain matching
# ---------------------------------------------------------------------------


class TestNeedsProxy:
    def setup_method(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w")
        self._tmp.write(FULL_CONFIG)
        self._tmp.close()
        self.proxy = InstitutionalProxy(config_path=Path(self._tmp.name))

    def teardown_method(self):
        os.unlink(self._tmp.name)

    def test_jstor_needs_proxy(self):
        assert self.proxy.needs_proxy("https://www.jstor.org/stable/12345")

    def test_jstor_subdomain(self):
        assert self.proxy.needs_proxy("https://jstor.org/stable/12345")

    def test_springer_needs_proxy(self):
        assert self.proxy.needs_proxy("https://link.springer.com/article/10.1007/s123")

    def test_sciencedirect_needs_proxy(self):
        assert self.proxy.needs_proxy("https://www.sciencedirect.com/science/article/pii/123")

    def test_arxiv_does_not_need_proxy(self):
        assert not self.proxy.needs_proxy("https://arxiv.org/pdf/2301.12345.pdf")

    def test_empty_url(self):
        assert not self.proxy.needs_proxy("")

    def test_invalid_url(self):
        assert not self.proxy.needs_proxy("not-a-url")


# ---------------------------------------------------------------------------
# URL rewriting
# ---------------------------------------------------------------------------


class TestURLRewriting:
    def test_query_string_mode(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, FULL_CONFIG)
        proxy = InstitutionalProxy(config_path=cfg)

        result = proxy.rewrite_url("https://www.jstor.org/stable/12345")
        assert result == (
            "https://proxy.university.edu/login?url="
            "https%3A%2F%2Fwww.jstor.org%2Fstable%2F12345"
        )

    def test_prefix_mode(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, PREFIX_CONFIG)
        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)

            result = proxy.rewrite_url("https://www.jstor.org/stable/12345")
            assert "www-jstor-org" in result
            assert "proxy.university.edu" in result
            assert "/stable/12345" in result

    def test_rewrite_empty_base_url(self, tmp_path):
        config = FULL_CONFIG.replace(
            'base_url: "https://proxy.university.edu"',
            'base_url: ""',
        )
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, config)
        proxy = InstitutionalProxy(config_path=cfg)
        # Should return original URL unchanged
        url = "https://www.jstor.org/stable/12345"
        assert proxy.rewrite_url(url) == url


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_not_configured(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, DISABLED_CONFIG)
        proxy = InstitutionalProxy(config_path=cfg)
        result = await proxy.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_success(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, FULL_CONFIG)
        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)

            mock_response = MagicMock()
            mock_response.status_code = 302
            mock_response.text = "Welcome"

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.cookies = {"ezproxy": "abc123"}

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await proxy.login()
                assert result is True
            await proxy.close()

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, FULL_CONFIG)
        with patch.dict(os.environ, {"TEST_PROXY_PASS": "wrong"}):
            proxy = InstitutionalProxy(config_path=cfg)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "Invalid login credentials. Please try again."

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.cookies = {}
            mock_client.aclose = AsyncMock()

            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await proxy.login()
                assert result is False
            await proxy.close()


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


class TestDownload:
    @pytest.mark.asyncio
    async def test_download_pdf_success(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        _write_config(cfg, FULL_CONFIG)
        dest = tmp_path / "output.pdf"

        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)
            proxy._logged_in = True

            pdf_data = b"%PDF-1.4 fake content" + b"\x00" * 1000

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=False)

            async def fake_aiter(*args, **kwargs):
                yield pdf_data
            mock_response.aiter_bytes = fake_aiter

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_response)
            proxy._session = mock_client

            result = await proxy.download_pdf(
                "https://www.jstor.org/stable/12345", dest
            )
            assert result == str(dest)
            assert dest.exists()
            await proxy.close()

    @pytest.mark.asyncio
    async def test_download_not_pdf(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        _write_config(cfg, FULL_CONFIG)
        dest = tmp_path / "output.pdf"

        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)
            proxy._logged_in = True

            html_data = b"<html>Login required</html>"

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=False)

            async def fake_aiter(*args, **kwargs):
                yield html_data
            mock_response.aiter_bytes = fake_aiter

            mock_client = AsyncMock()
            mock_client.stream = MagicMock(return_value=mock_response)
            proxy._session = mock_client

            result = await proxy.download_pdf(
                "https://www.jstor.org/stable/12345", dest
            )
            assert result is None
            assert not dest.exists()
            await proxy.close()

    @pytest.mark.asyncio
    async def test_download_existing_file(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        _write_config(cfg, FULL_CONFIG)
        dest = tmp_path / "output.pdf"
        dest.write_bytes(b"%PDF-1.4 existing")

        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)
            result = await proxy.download_pdf(
                "https://www.jstor.org/stable/12345", dest
            )
            assert result == str(dest)
            await proxy.close()


# ---------------------------------------------------------------------------
# Config save/update
# ---------------------------------------------------------------------------


class TestConfigUpdate:
    def test_update_and_save(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        proxy = InstitutionalProxy(config_path=cfg)
        proxy.update_config(
            base_url="https://proxy.test.edu",
            username="alice",
            password_env="MY_PASS",
        )
        proxy.save_config()

        assert cfg.exists()
        # Reload and verify
        proxy2 = InstitutionalProxy(config_path=cfg)
        assert proxy2.base_url == "https://proxy.test.edu"
        assert proxy2.username == "alice"
        assert proxy2._config["proxy"]["enabled"] is True

    def test_test_connection_not_configured(self, tmp_path):
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, DISABLED_CONFIG)
        proxy = InstitutionalProxy(config_path=cfg)
        result = proxy.test_connection()
        assert "Not configured" in result


# ---------------------------------------------------------------------------
# Pipeline integration (mock)
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    def test_acquisition_report_proxy_field(self):
        from src.reference_acquisition.pipeline import AcquisitionReport
        report = AcquisitionReport()
        assert report.proxy_downloaded == 0
        report.proxy_downloaded = 5
        assert "Proxy: 5" in report.summary()

    def test_downloader_accepts_proxy(self, tmp_path):
        from src.reference_acquisition.downloader import PDFDownloader
        cfg = tmp_path / "proxy.yaml"
        _write_config(cfg, FULL_CONFIG)
        with patch.dict(os.environ, {"TEST_PROXY_PASS": "secret"}):
            proxy = InstitutionalProxy(config_path=cfg)
            downloader = PDFDownloader(proxy=proxy)
            assert downloader.proxy is proxy
