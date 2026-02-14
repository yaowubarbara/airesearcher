"""Download open-access PDFs for papers."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx

from src.knowledge_base.models import Paper

if TYPE_CHECKING:
    from src.reference_acquisition.proxy_session import InstitutionalProxy

logger = logging.getLogger(__name__)

DEFAULT_DOWNLOAD_DIR = Path("data/papers")
MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB
PDF_MAGIC = b"%PDF"
CONCURRENT_DOWNLOADS = 3


class PDFDownloader:
    """Download OA PDFs with size limits and validation."""

    def __init__(
        self,
        download_dir: Path | str = DEFAULT_DOWNLOAD_DIR,
        proxy: Optional["InstitutionalProxy"] = None,
    ):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(CONCURRENT_DOWNLOADS)
        self.proxy = proxy

    async def download_pdf(self, paper: Paper) -> Optional[str]:
        """Download the PDF for a paper if it has a pdf_url.

        Args:
            paper: Paper with pdf_url set.

        Returns:
            Local file path on success, None on failure.
        """
        if not paper.pdf_url:
            return None

        async with self._semaphore:
            try:
                return await self._do_download(paper)
            except Exception as e:
                logger.warning(
                    "Failed to download PDF for '%s': %s",
                    paper.title[:60],
                    e,
                )
                return None

    async def _do_download(self, paper: Paper) -> Optional[str]:
        """Perform the actual download with validation."""
        url = paper.pdf_url
        # Build filename from DOI or paper ID
        safe_name = self._safe_filename(paper)
        dest = self.download_dir / f"{safe_name}.pdf"

        if dest.exists():
            logger.debug("PDF already exists: %s", dest)
            return str(dest)

        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,*/*",
            },
        ) as client:
            # HEAD request to check size
            try:
                head = await client.head(url)
                content_length = int(head.headers.get("content-length", 0))
                if content_length > MAX_PDF_SIZE:
                    logger.warning(
                        "PDF too large (%d bytes) for %s", content_length, url
                    )
                    return None
            except (httpx.HTTPError, ValueError):
                pass  # Proceed anyway; some servers don't support HEAD

            # Stream download
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    logger.warning("HTTP %d for %s", response.status_code, url)
                    return None

                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_PDF_SIZE:
                        logger.warning("PDF exceeded size limit during download: %s", url)
                        return None
                    chunks.append(chunk)

                data = b"".join(chunks)

            # Validate PDF magic bytes
            if not data[:4].startswith(PDF_MAGIC):
                logger.warning("Downloaded file is not a valid PDF: %s", url)
                return None

            dest.write_bytes(data)
            logger.info("Downloaded PDF: %s (%d bytes)", dest, len(data))
            return str(dest)

    @staticmethod
    def _safe_filename(paper: Paper) -> str:
        """Generate a safe filename from DOI or paper ID."""
        if paper.doi:
            # Replace slashes and other problematic chars
            return re.sub(r"[^\w\-.]", "_", paper.doi)
        if paper.id:
            return paper.id
        if paper.semantic_scholar_id:
            return f"s2_{paper.semantic_scholar_id}"
        if paper.openalex_id:
            return f"oa_{paper.openalex_id}"
        # Fallback: sanitize title
        return re.sub(r"[^\w\-.]", "_", paper.title[:60])

    async def download_with_fallback(
        self, paper: Paper, pdf_urls: list[str]
    ) -> Optional[str]:
        """Try downloading from multiple URLs in sequence, return first success.

        Args:
            paper: Paper metadata (used for filename generation).
            pdf_urls: Ordered list of candidate PDF URLs to try.

        Returns:
            Local file path on first successful download, None if all fail.
        """
        for url in pdf_urls:
            # Temporarily set pdf_url for the download attempt
            original_url = paper.pdf_url
            paper.pdf_url = url
            try:
                result = await self.download_pdf(paper)
                if result:
                    return result
            finally:
                paper.pdf_url = original_url
        return None

    async def download_via_proxy(self, paper: Paper) -> Optional[str]:
        """Try downloading a paper's PDF through the institutional proxy.

        Args:
            paper: Paper with DOI (required for proxy download).

        Returns:
            Local file path on success, None on failure.
        """
        if not self.proxy or not self.proxy.is_configured:
            return None
        if not paper.doi:
            return None

        async with self._semaphore:
            try:
                return await self.proxy.download_paper(paper, self.download_dir)
            except Exception as e:
                logger.warning(
                    "Proxy download failed for '%s': %s",
                    paper.title[:60],
                    e,
                )
                return None

    async def download_many(self, papers: list[Paper]) -> dict[str, Optional[str]]:
        """Download PDFs for multiple papers concurrently.

        Returns:
            Dict mapping paper title to local path (or None on failure).
        """
        tasks = [self.download_pdf(p) for p in papers]
        results = await asyncio.gather(*tasks)
        return {
            paper.title: path
            for paper, path in zip(papers, results)
        }
