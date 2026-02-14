"""Institutional proxy session for accessing paywalled PDFs via EZproxy."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

import httpx
import yaml

from src.knowledge_base.models import Paper
from src.reference_acquisition.downloader import MAX_PDF_SIZE, PDF_MAGIC

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/proxy.yaml")


class InstitutionalProxy:
    """Manages authenticated sessions through university EZproxy."""

    def __init__(self, config_path: Path | str = DEFAULT_CONFIG_PATH):
        self._config_path = Path(config_path)
        self._config: dict = {}
        self._session: Optional[httpx.AsyncClient] = None
        self._logged_in = False
        self._load_config()

    def _load_config(self) -> None:
        """Load proxy configuration from YAML file."""
        if not self._config_path.exists():
            logger.debug("Proxy config not found: %s", self._config_path)
            self._config = {}
            return
        with open(self._config_path) as f:
            self._config = yaml.safe_load(f) or {}

    @property
    def is_configured(self) -> bool:
        """True if proxy is enabled and all required fields are set."""
        proxy = self._config.get("proxy", {})
        creds = self._config.get("credentials", {})
        if not proxy.get("enabled"):
            return False
        if not proxy.get("base_url"):
            return False
        if not creds.get("username"):
            return False
        password_env = creds.get("password_env", "INSTITUTIONAL_PASSWORD")
        if not os.environ.get(password_env):
            return False
        return True

    @property
    def base_url(self) -> str:
        return self._config.get("proxy", {}).get("base_url", "").rstrip("/")

    @property
    def proxy_type(self) -> str:
        return self._config.get("proxy", {}).get("type", "ezproxy")

    @property
    def username(self) -> str:
        return self._config.get("credentials", {}).get("username", "")

    @property
    def password(self) -> str:
        env_var = self._config.get("credentials", {}).get(
            "password_env", "INSTITUTIONAL_PASSWORD"
        )
        return os.environ.get(env_var, "")

    @property
    def publisher_domains(self) -> set[str]:
        """All publisher domains that need proxy access."""
        domains: set[str] = set()
        for pub in self._config.get("publishers", []):
            for d in pub.get("domains", []):
                domains.add(d.lower())
        return domains

    def needs_proxy(self, url: str) -> bool:
        """Check if URL domain matches any publisher in config."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            host = host.lower()
        except Exception:
            return False

        for domain in self.publisher_domains:
            if host == domain or host.endswith("." + domain):
                return True
        return False

    def rewrite_url(self, url: str) -> str:
        """Rewrite a URL to go through the EZproxy.

        Supports two modes:
        - Query string: {base_url}/login?url={original_url}
        - Prefix: replace host with host-with-dashes.proxy.uni.edu
        """
        if not self.base_url:
            return url

        parsed_base = urlparse(self.base_url)

        # Prefix mode: detected if base_url has a port or contains "proxy" path
        # For prefix mode: www.jstor.org -> www-jstor-org.proxy.uni.edu
        if self._is_prefix_mode():
            parsed_target = urlparse(url)
            target_host = parsed_target.hostname or ""
            dashed_host = target_host.replace(".", "-")
            proxy_host = parsed_base.hostname or ""
            port = parsed_base.port
            new_host = f"{dashed_host}.{proxy_host}"
            if port:
                new_host = f"{new_host}:{port}"
            scheme = parsed_target.scheme or "https"
            path = parsed_target.path or ""
            query = f"?{parsed_target.query}" if parsed_target.query else ""
            fragment = f"#{parsed_target.fragment}" if parsed_target.fragment else ""
            return f"{scheme}://{new_host}{path}{query}{fragment}"

        # Default: query string mode
        return f"{self.base_url}/login?url={quote(url, safe='')}"

    def _is_prefix_mode(self) -> bool:
        """Detect if the EZproxy uses prefix mode (host rewriting)."""
        proxy_type = self.proxy_type
        if proxy_type == "prefix":
            return True
        # Heuristic: if base_url has a port, likely prefix mode
        parsed = urlparse(self.base_url)
        return parsed.port is not None

    async def login(self) -> bool:
        """Authenticate with EZproxy. Returns True on success."""
        if self._logged_in and self._session:
            return True

        if not self.is_configured:
            logger.warning("Proxy not configured — cannot login")
            return False

        # Create a persistent session
        self._session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            },
        )

        login_url = f"{self.base_url}/login"
        try:
            resp = await self._session.post(
                login_url,
                data={"user": self.username, "pass": self.password},
            )
            # EZproxy returns 302 on success (redirect to menu/logged-in page)
            # or 200 with login form again on failure.
            # Check for session cookie as a success indicator.
            cookies = dict(self._session.cookies)
            if cookies or resp.status_code in (200, 302):
                # Check for common failure indicators in response body
                body = resp.text.lower()
                if "invalid" in body and "login" in body:
                    logger.warning("EZproxy login appears to have failed (invalid credentials)")
                    await self._close_session()
                    return False

                self._logged_in = True
                logger.info("EZproxy login successful")
                return True
            else:
                logger.warning("EZproxy login failed: HTTP %d", resp.status_code)
                await self._close_session()
                return False
        except Exception as e:
            logger.warning("EZproxy login error: %s", e)
            await self._close_session()
            return False

    async def get_authenticated_client(self) -> Optional[httpx.AsyncClient]:
        """Return client with session cookies, auto-login if needed."""
        if not self._logged_in:
            success = await self.login()
            if not success:
                return None
        return self._session

    async def download_pdf(self, url: str, dest: Path) -> Optional[str]:
        """Download a PDF through the proxy with authenticated session.

        Args:
            url: Original publisher URL (will be rewritten through proxy).
            dest: Destination file path.

        Returns:
            Local file path on success, None on failure.
        """
        if dest.exists():
            logger.debug("PDF already exists: %s", dest)
            return str(dest)

        client = await self.get_authenticated_client()
        if not client:
            return None

        proxy_url = self.rewrite_url(url) if self.needs_proxy(url) else url

        try:
            async with client.stream("GET", proxy_url) as response:
                if response.status_code != 200:
                    logger.warning(
                        "Proxy download HTTP %d for %s", response.status_code, proxy_url
                    )
                    return None

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_PDF_SIZE:
                        logger.warning("PDF exceeded size limit via proxy: %s", url)
                        return None
                    chunks.append(chunk)

                data = b"".join(chunks)

            # Validate PDF
            if not data[:4].startswith(PDF_MAGIC):
                logger.warning(
                    "Proxy download is not a valid PDF (got %r): %s",
                    data[:20],
                    url,
                )
                return None

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            logger.info("Downloaded via proxy: %s (%d bytes)", dest, len(data))
            return str(dest)
        except Exception as e:
            logger.warning("Proxy download failed for %s: %s", url, e)
            return None

    async def download_paper(
        self, paper: Paper, download_dir: Path
    ) -> Optional[str]:
        """Download a paper's PDF through institutional proxy.

        Resolves the DOI to a publisher URL, then downloads through proxy.

        Args:
            paper: Paper with DOI.
            download_dir: Directory to save PDFs.

        Returns:
            Local file path on success, None on failure.
        """
        if not paper.doi:
            return None

        safe_name = re.sub(r"[^\w\-.]", "_", paper.doi)
        dest = download_dir / f"{safe_name}.pdf"

        if dest.exists():
            return str(dest)

        # Resolve DOI to publisher URL
        doi_url = f"https://doi.org/{paper.doi}"

        try:
            # Follow DOI redirect to get the actual publisher URL
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True
            ) as tmp_client:
                resp = await tmp_client.head(doi_url)
                publisher_url = str(resp.url)
        except Exception:
            publisher_url = doi_url

        # Only use proxy if the publisher needs it
        if not self.needs_proxy(publisher_url):
            logger.debug("Publisher %s doesn't need proxy", publisher_url)
            return None

        return await self.download_pdf(publisher_url, dest)

    async def _close_session(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.aclose()
            self._session = None
        self._logged_in = False

    async def close(self) -> None:
        """Close the proxy session."""
        await self._close_session()

    def save_config(self) -> None:
        """Write current config back to YAML file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)

    def update_config(
        self,
        base_url: str,
        username: str,
        password_env: str = "INSTITUTIONAL_PASSWORD",
        proxy_type: str = "ezproxy",
    ) -> None:
        """Update proxy configuration programmatically."""
        if "proxy" not in self._config:
            self._config["proxy"] = {}
        if "credentials" not in self._config:
            self._config["credentials"] = {}

        self._config["proxy"]["enabled"] = True
        self._config["proxy"]["type"] = proxy_type
        self._config["proxy"]["base_url"] = base_url
        self._config["credentials"]["username"] = username
        self._config["credentials"]["password_env"] = password_env

        # Ensure publishers section exists
        if "publishers" not in self._config:
            self._config["publishers"] = _default_publishers()

    def test_connection(self) -> str:
        """Return a summary string of the current config for display."""
        if not self.is_configured:
            missing = []
            proxy = self._config.get("proxy", {})
            creds = self._config.get("credentials", {})
            if not proxy.get("enabled"):
                missing.append("proxy.enabled is false")
            if not proxy.get("base_url"):
                missing.append("proxy.base_url is empty")
            if not creds.get("username"):
                missing.append("credentials.username is empty")
            pw_env = creds.get("password_env", "INSTITUTIONAL_PASSWORD")
            if not os.environ.get(pw_env):
                missing.append(f"env var {pw_env} not set")
            return f"Not configured: {', '.join(missing)}"

        return (
            f"Configured: {self.proxy_type} at {self.base_url}\n"
            f"  Username: {self.username}\n"
            f"  Publishers: {len(self._config.get('publishers', []))} configured"
        )


def _default_publishers() -> list[dict]:
    """Return default publisher list."""
    return [
        {"name": "JSTOR", "domains": ["jstor.org", "www.jstor.org"]},
        {"name": "Project MUSE", "domains": ["muse.jhu.edu"]},
        {"name": "Springer", "domains": ["link.springer.com", "springer.com", "springerlink.com"]},
        {"name": "Elsevier / ScienceDirect", "domains": ["sciencedirect.com", "elsevier.com"]},
        {"name": "Wiley", "domains": ["onlinelibrary.wiley.com", "wiley.com"]},
        {"name": "Taylor & Francis", "domains": ["tandfonline.com"]},
        {"name": "Cambridge University Press", "domains": ["cambridge.org"]},
        {"name": "Oxford University Press", "domains": ["academic.oup.com", "oup.com"]},
        {"name": "Duke University Press", "domains": ["read.dukeupress.edu", "dukeupress.edu"]},
        {"name": "SAGE", "domains": ["journals.sagepub.com", "sagepub.com"]},
        {"name": "De Gruyter", "domains": ["degruyter.com"]},
    ]
