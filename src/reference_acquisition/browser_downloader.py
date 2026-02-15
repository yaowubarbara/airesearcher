"""Playwright-based browser agent for downloading PDFs from Sci-Hub and LibGen."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

logger = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_DIR = Path("data/papers")
PDF_MAGIC = b"%PDF"
PAGE_TIMEOUT_MS = 30_000
SCIHUB_MIRRORS = [
    "https://sci-hub.ru",
    "https://sci-hub.ee",
    "https://sci-hub.st",
    "https://sci-hub.se",
]
LIBGEN_MIRRORS = [
    "https://libgen.rs",
    "https://libgen.is",
    "https://libgen.li",
]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MAX_FILENAME_LENGTH = 100


def _sanitize_filename(name: str) -> str:
    """Replace special characters and limit filename length.

    Args:
        name: Raw string to convert into a safe filename.

    Returns:
        Sanitized filename without extension, at most MAX_FILENAME_LENGTH chars.
    """
    # Replace any character that is not alphanumeric, hyphen, dot, or underscore
    safe = re.sub(r"[^\w\-.]", "_", name)
    # Collapse consecutive underscores
    safe = re.sub(r"_+", "_", safe)
    # Strip leading/trailing underscores and dots
    safe = safe.strip("_.")
    if not safe:
        safe = "unnamed_paper"
    return safe[:MAX_FILENAME_LENGTH]


class BrowserDownloader:
    """Download PDFs from Sci-Hub and LibGen using a headless browser.

    Usage::

        downloader = BrowserDownloader("data/papers")
        await downloader._ensure_browser()
        path = await downloader.download_paper("10.1234/example", "Example Paper")
        await downloader.close()

    Or with ``download_batch`` which manages the browser lifecycle
    automatically.
    """

    def __init__(self, download_dir: str = "data/papers") -> None:
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._playwright: Any = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    async def _ensure_browser(self) -> BrowserContext:
        """Launch browser and context if not already running."""
        if self._context is not None:
            return self._context

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            accept_downloads=True,
        )
        return self._context

    async def close(self) -> None:
        """Close browser and release Playwright resources."""
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def download_paper(
        self, doi: str, title: str
    ) -> Optional[str]:
        """Try Sci-Hub first, then LibGen. Return local PDF path or None.

        Args:
            doi: The DOI of the paper (e.g. ``10.1234/example``).
            title: Human-readable title used for the filename.

        Returns:
            Absolute path to the downloaded PDF, or ``None`` on failure.
        """
        if not doi:
            logger.warning("No DOI provided, cannot download")
            return None

        await self._ensure_browser()

        # --- Attempt 1: Sci-Hub (try multiple mirrors) ---
        for mirror in SCIHUB_MIRRORS:
            try:
                path = await self._download_from_scihub(doi, title, base_url=mirror)
                if path:
                    logger.info("Downloaded via Sci-Hub (%s): %s", mirror, path)
                    return path
            except Exception as exc:
                logger.debug("Sci-Hub mirror %s failed for DOI %s: %s", mirror, doi, exc)

        # --- Attempt 2: LibGen (try multiple mirrors) ---
        for mirror in LIBGEN_MIRRORS:
            try:
                path = await self._download_from_libgen(doi, title, base_url=mirror)
                if path:
                    logger.info("Downloaded via LibGen (%s): %s", mirror, path)
                    return path
            except Exception as exc:
                logger.debug("LibGen mirror %s failed for DOI %s: %s", mirror, doi, exc)

        logger.info("All browser download attempts failed for DOI %s", doi)
        return None

    async def download_batch(
        self,
        papers: list[dict],
        progress_callback: Optional[Callable[[str, str, int, int], None]] = None,
    ) -> dict:
        """Download a batch of papers.

        Args:
            papers: List of dicts, each with keys ``id``, ``doi``, ``title``.
            progress_callback: Optional callable invoked after each paper as
                ``callback(paper_id, status, current_index, total)``.

        Returns:
            Dict with ``downloaded`` (int), ``failed`` (int),
            ``paths`` (dict mapping paper id to local path).
        """
        await self._ensure_browser()

        result: dict[str, Any] = {
            "downloaded": 0,
            "failed": 0,
            "paths": {},
        }
        total = len(papers)

        for idx, paper in enumerate(papers):
            paper_id = paper.get("id", f"unknown_{idx}")
            doi = paper.get("doi", "")
            title = paper.get("title", "")

            path = await self.download_paper(doi, title)

            if path:
                result["downloaded"] += 1
                result["paths"][paper_id] = path
                status = "downloaded"
            else:
                result["failed"] += 1
                status = "failed"

            if progress_callback is not None:
                try:
                    progress_callback(paper_id, status, idx + 1, total)
                except Exception:
                    pass

        await self.close()
        return result

    # ------------------------------------------------------------------
    # Sci-Hub
    # ------------------------------------------------------------------

    async def _download_from_scihub(
        self, doi: str, title: str, base_url: str = "https://sci-hub.ru"
    ) -> Optional[str]:
        """Navigate to Sci-Hub and extract the PDF.

        Sci-Hub typically embeds the PDF in an ``<iframe>`` or ``<embed>``
        element with id ``pdf``, or provides a direct ``.pdf`` link.
        """
        assert self._context is not None
        page: Page = await self._context.new_page()
        try:
            url = f"{base_url}/{doi}"
            logger.debug("Navigating to Sci-Hub: %s", url)
            await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")

            # Check for CAPTCHA
            if await self._detect_captcha(page):
                logger.warning(
                    "CAPTCHA detected on Sci-Hub for DOI %s — skipping", doi
                )
                return None

            # Strategy 1: find the PDF iframe/embed src
            pdf_url = await self._extract_scihub_pdf_url(page)
            if pdf_url:
                return await self._download_pdf_from_url(page, pdf_url, title)

            # Strategy 2: intercept a download triggered by clicking a button
            save_button = await page.query_selector("button#save, a[onclick*='download']")
            if save_button:
                return await self._download_via_click(page, save_button, title)

            logger.debug("No PDF element found on Sci-Hub page for DOI %s", doi)
            return None
        finally:
            await page.close()

    async def _extract_scihub_pdf_url(self, page: Page) -> Optional[str]:
        """Try to find a PDF URL in the Sci-Hub page DOM."""
        base = page.url.split("/")[0] + "//" + page.url.split("/")[2]  # derive base from current URL
        # Check <iframe id="pdf"> or <embed id="pdf">
        for selector in ["#pdf", "iframe[src*='.pdf']", "embed[src*='.pdf']"]:
            element = await page.query_selector(selector)
            if element:
                src = await element.get_attribute("src")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = base + src
                    return src

        # Check for a direct <a> link ending in .pdf
        links = await page.query_selector_all("a[href$='.pdf']")
        for link in links:
            href = await link.get_attribute("href")
            if href:
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = base + href
                return href

        return None

    # ------------------------------------------------------------------
    # LibGen
    # ------------------------------------------------------------------

    async def _download_from_libgen(
        self, doi: str, title: str, base_url: str = "https://libgen.rs"
    ) -> Optional[str]:
        """Search LibGen's scimag section by DOI and download the PDF."""
        assert self._context is not None
        page: Page = await self._context.new_page()
        try:
            search_url = f"{base_url}/scimag/?q={doi}"
            logger.debug("Navigating to LibGen: %s", search_url)
            await page.goto(
                search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded"
            )

            # Check for CAPTCHA
            if await self._detect_captcha(page):
                logger.warning(
                    "CAPTCHA detected on LibGen for DOI %s — skipping", doi
                )
                return None

            # LibGen scimag lists results in a table; find download links
            # The GET mirror links usually have a link to a direct download
            download_link = await page.query_selector(
                "table.c a[href*='get.php'], "
                "table.c a[href*='download'], "
                "table a[title='Gen.lib.rus.ec'], "
                "table a[title='Libgen.lc'], "
                "table a[title='Library.lol']"
            )

            if not download_link:
                # Broader fallback: any link in the results table that looks
                # like a mirror
                download_link = await page.query_selector(
                    "table a[href*='library.lol'], "
                    "table a[href*='libgen.lc'], "
                    "table a[href*='gen.lib']"
                )

            if not download_link:
                logger.debug("No download link found on LibGen for DOI %s", doi)
                return None

            href = await download_link.get_attribute("href")
            if not href:
                return None

            # Follow the mirror page to find the actual PDF link
            return await self._follow_libgen_mirror(page, href, title)
        finally:
            await page.close()

    async def _follow_libgen_mirror(
        self, page: Page, mirror_url: str, title: str
    ) -> Optional[str]:
        """Navigate to a LibGen mirror page and find the direct download link."""
        logger.debug("Following LibGen mirror: %s", mirror_url)
        await page.goto(
            mirror_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded"
        )

        # Mirror pages typically have a "GET" button or direct download link
        download_link = await page.query_selector(
            "a[href$='.pdf'], "
            "#download a, "
            "a:has-text('GET'), "
            "a:has-text('Download')"
        )

        if not download_link:
            logger.debug("No direct download link on mirror page")
            return None

        href = await download_link.get_attribute("href")
        if not href:
            return None

        # Make absolute if relative
        if href.startswith("/"):
            from urllib.parse import urljoin

            href = urljoin(mirror_url, href)

        return await self._download_pdf_from_url(page, href, title)

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------

    async def _download_pdf_from_url(
        self, page: Page, pdf_url: str, title: str
    ) -> Optional[str]:
        """Download a PDF from a direct URL using the browser context.

        Uses Playwright's built-in download handling to capture the file,
        then validates and moves it to the target directory.
        """
        dest = self._build_dest_path(title)
        if dest.exists():
            logger.debug("PDF already exists: %s", dest)
            return str(dest)

        try:
            # Start waiting for the download before navigating
            async with page.expect_download(timeout=PAGE_TIMEOUT_MS) as download_info:
                await page.goto(pdf_url, timeout=PAGE_TIMEOUT_MS)
            download = download_info.value

            # Save to a temporary path first, then validate
            tmp_path = dest.with_suffix(".tmp")
            await download.save_as(str(tmp_path))

            if self._validate_pdf(tmp_path):
                tmp_path.rename(dest)
                logger.info("Saved PDF: %s (%d bytes)", dest, dest.stat().st_size)
                return str(dest)
            else:
                tmp_path.unlink(missing_ok=True)
                logger.warning("Downloaded file is not a valid PDF: %s", pdf_url)
                return None
        except Exception:
            # Fallback: try fetching with a new page request via API
            return await self._download_pdf_via_request(pdf_url, title)

    async def _download_pdf_via_request(
        self, pdf_url: str, title: str
    ) -> Optional[str]:
        """Fallback download using the browser context's request API."""
        assert self._context is not None
        dest = self._build_dest_path(title)
        if dest.exists():
            return str(dest)

        try:
            response = await self._context.request.get(
                pdf_url, timeout=PAGE_TIMEOUT_MS
            )
            if response.status != 200:
                logger.warning(
                    "HTTP %d when downloading PDF from %s", response.status, pdf_url
                )
                return None

            data = await response.body()
            if not data or not data[:4].startswith(PDF_MAGIC):
                logger.warning("Response is not a valid PDF: %s", pdf_url)
                return None

            dest.write_bytes(data)
            logger.info("Saved PDF (via request API): %s (%d bytes)", dest, len(data))
            return str(dest)
        except Exception as exc:
            logger.warning("Request-based download failed for %s: %s", pdf_url, exc)
            return None

    async def _download_via_click(
        self, page: Page, element: Any, title: str
    ) -> Optional[str]:
        """Click a button/link and wait for the browser download to start."""
        dest = self._build_dest_path(title)
        if dest.exists():
            return str(dest)

        try:
            async with page.expect_download(timeout=PAGE_TIMEOUT_MS) as download_info:
                await element.click()
            download = download_info.value

            tmp_path = dest.with_suffix(".tmp")
            await download.save_as(str(tmp_path))

            if self._validate_pdf(tmp_path):
                tmp_path.rename(dest)
                logger.info("Saved PDF (via click): %s", dest)
                return str(dest)
            else:
                tmp_path.unlink(missing_ok=True)
                return None
        except Exception as exc:
            logger.warning("Click-download failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # CAPTCHA detection
    # ------------------------------------------------------------------

    async def _detect_captcha(self, page: Page) -> bool:
        """Heuristic check for common CAPTCHA elements on the page."""
        captcha_selectors = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "#captcha",
            ".g-recaptcha",
            "img[alt*='captcha' i]",
            "input[name='captcha']",
        ]
        for selector in captcha_selectors:
            element = await page.query_selector(selector)
            if element:
                return True

        # Check page text for captcha keywords
        try:
            body_text = await page.inner_text("body")
            lower = body_text.lower()
            if "captcha" in lower and ("enter" in lower or "solve" in lower):
                return True
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def _build_dest_path(self, title: str) -> Path:
        """Build the destination file path from a paper title."""
        safe_name = _sanitize_filename(title)
        return self.download_dir / f"{safe_name}.pdf"

    @staticmethod
    def _validate_pdf(path: Path) -> bool:
        """Check that the file at *path* starts with the PDF magic bytes."""
        try:
            with open(path, "rb") as f:
                header = f.read(4)
            return header.startswith(PDF_MAGIC)
        except (OSError, IOError):
            return False
