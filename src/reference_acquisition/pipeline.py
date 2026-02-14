"""Orchestrate search -> download -> index for reference acquisition."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import PaperStatus
from src.knowledge_base.vector_store import VectorStore
from src.literature_indexer.indexer import Indexer

from .downloader import PDFDownloader
from .oa_resolver import OAResolver
from .proxy_session import InstitutionalProxy
from .searcher import ReferenceSearcher
from .web_searcher import WebSearcher

logger = logging.getLogger(__name__)


@dataclass
class AcquisitionReport:
    """Statistics from a reference acquisition run."""

    query: str = ""
    found: int = 0
    downloaded: int = 0
    indexed: int = 0
    failed_download: int = 0
    failed_index: int = 0
    skipped_existing: int = 0
    papers_with_pdf_url: int = 0
    oa_resolved: int = 0
    proxy_downloaded: int = 0
    paper_ids: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Reference Acquisition: query='{self.query}'\n"
            f"  Found: {self.found} | With PDF URL: {self.papers_with_pdf_url}\n"
            f"  Downloaded: {self.downloaded} | OA resolved: {self.oa_resolved}"
            f" | Proxy: {self.proxy_downloaded}\n"
            f"  Failed: {self.failed_download}\n"
            f"  Indexed: {self.indexed} | Failed index: {self.failed_index}\n"
            f"  Skipped (existing): {self.skipped_existing}"
        )


class ReferenceAcquisitionPipeline:
    """Full pipeline: search -> insert -> download -> index."""

    def __init__(
        self,
        db: Database,
        vector_store: VectorStore,
        download_dir: Optional[str] = None,
        proxy: Optional[InstitutionalProxy] = None,
    ):
        self.db = db
        self.vs = vector_store
        self.searcher = ReferenceSearcher(db=db)
        self.web_searcher = WebSearcher()
        # Auto-load proxy if not explicitly provided
        if proxy is None:
            _proxy = InstitutionalProxy()
            self.proxy = _proxy if _proxy.is_configured else None
        else:
            self.proxy = proxy
        self.downloader = PDFDownloader(
            download_dir=download_dir or "data/papers",
            proxy=self.proxy,
        )
        self.indexer = Indexer(vector_store=vector_store)
        self.oa_resolver = OAResolver()

    async def acquire_references(
        self,
        topic: str,
        max_results: int = 50,
    ) -> AcquisitionReport:
        """Search for papers, download PDFs, and index into knowledge base.

        Args:
            topic: Research topic / keywords to search.
            max_results: Max results per API source.

        Returns:
            AcquisitionReport with statistics.
        """
        report = AcquisitionReport(query=topic)

        # Step 1: Search
        papers = await self.searcher.search_topic(
            topic, max_results_per_source=max_results
        )
        report.found = len(papers)
        report.papers_with_pdf_url = sum(1 for p in papers if p.pdf_url)

        if not papers:
            logger.info("No papers found for topic: %s", topic)
            return report

        # Step 2: Insert papers into DB
        for paper in papers:
            try:
                paper_id = self.db.insert_paper(paper)
                paper.id = paper_id
                report.paper_ids.append(paper_id)
            except Exception:
                logger.debug("Failed to insert paper: %s", paper.title[:60], exc_info=True)

        # Step 3: Download PDFs for papers that have pdf_url
        papers_with_url = [p for p in papers if p.pdf_url]
        downloaded_ids: set[str] = set()
        for paper in papers_with_url:
            pdf_path = await self.downloader.download_pdf(paper)
            if pdf_path:
                report.downloaded += 1
                downloaded_ids.add(paper.id or "")
                self.db.update_paper_pdf(
                    paper.id or "",
                    pdf_url=paper.pdf_url,
                    pdf_path=pdf_path,
                    status=PaperStatus.PDF_DOWNLOADED,
                )
                # Step 4: Index the downloaded PDF
                try:
                    self.indexer.index_paper(pdf_path, paper.id or "")
                    self.db.update_paper_status(
                        paper.id or "", PaperStatus.INDEXED
                    )
                    report.indexed += 1
                except Exception:
                    logger.warning(
                        "Failed to index PDF for %s",
                        paper.title[:60],
                        exc_info=True,
                    )
                    report.failed_index += 1
            else:
                report.failed_download += 1

        # Step 3.5: OA resolution for papers without PDF or failed downloads
        papers_needing_oa = [
            p for p in papers
            if (p.id or "") not in downloaded_ids
        ]
        for paper in papers_needing_oa:
            try:
                resolved_url = await self.oa_resolver.resolve_pdf_url(paper)
                if resolved_url:
                    pdf_path = await self.downloader.download_with_fallback(
                        paper, [resolved_url]
                    )
                    if pdf_path:
                        report.oa_resolved += 1
                        report.downloaded += 1
                        downloaded_ids.add(paper.id or "")
                        self.db.update_paper_pdf(
                            paper.id or "",
                            pdf_url=resolved_url,
                            pdf_path=pdf_path,
                            status=PaperStatus.PDF_DOWNLOADED,
                        )
                        try:
                            self.indexer.index_paper(pdf_path, paper.id or "")
                            self.db.update_paper_status(
                                paper.id or "", PaperStatus.INDEXED
                            )
                            report.indexed += 1
                        except Exception:
                            logger.warning(
                                "Failed to index OA-resolved PDF for %s",
                                paper.title[:60],
                                exc_info=True,
                            )
                            report.failed_index += 1
            except Exception:
                logger.debug(
                    "OA resolution failed for %s",
                    paper.title[:60],
                    exc_info=True,
                )

        # Step 3.75: Institutional proxy download for remaining papers with DOIs
        if self.proxy and self.proxy.is_configured:
            papers_needing_proxy = [
                p for p in papers
                if (p.id or "") not in downloaded_ids and p.doi
            ]
            for paper in papers_needing_proxy:
                try:
                    pdf_path = await self.downloader.download_via_proxy(paper)
                    if pdf_path:
                        report.proxy_downloaded += 1
                        report.downloaded += 1
                        downloaded_ids.add(paper.id or "")
                        self.db.update_paper_pdf(
                            paper.id or "",
                            pdf_url=f"https://doi.org/{paper.doi}",
                            pdf_path=pdf_path,
                            status=PaperStatus.PDF_DOWNLOADED,
                        )
                        try:
                            self.indexer.index_paper(pdf_path, paper.id or "")
                            self.db.update_paper_status(
                                paper.id or "", PaperStatus.INDEXED
                            )
                            report.indexed += 1
                        except Exception:
                            logger.warning(
                                "Failed to index proxy-downloaded PDF for %s",
                                paper.title[:60],
                                exc_info=True,
                            )
                            report.failed_index += 1
                except Exception:
                    logger.debug(
                        "Proxy download failed for %s",
                        paper.title[:60],
                        exc_info=True,
                    )

        # Step 5: Index metadata-only papers (no PDF available)
        papers_without_pdf = [
            p for p in papers
            if (p.id or "") not in downloaded_ids
        ]
        for paper in papers_without_pdf:
            try:
                self.indexer.index_from_metadata(paper)
                report.indexed += 1
            except Exception:
                logger.debug(
                    "Failed to index metadata for %s",
                    paper.title[:60],
                    exc_info=True,
                )
                report.failed_index += 1

        logger.info(report.summary())
        return report

    async def acquire_broad_references(
        self,
        queries: list[str],
        max_results: int = 20,
    ) -> AcquisitionReport:
        """Search web sources (Google Books, Open Library) for broader references.

        Use this for novels, classic theory, literary criticism, etc. that
        may not appear in academic journal APIs.

        Args:
            queries: List of search queries (e.g. ["Heart of Darkness Conrad",
                "Orientalism Edward Said", "后殖民理论"]).
            max_results: Max results per query.

        Returns:
            AcquisitionReport with statistics.
        """
        report = AcquisitionReport(query="; ".join(queries))

        all_papers: list = []
        for query in queries:
            papers = await self.web_searcher.search_all(query, max_results)
            all_papers.extend(papers)

        report.found = len(all_papers)
        report.papers_with_pdf_url = sum(1 for p in all_papers if p.pdf_url)

        # Insert and index
        for paper in all_papers:
            try:
                paper_id = self.db.insert_paper(paper)
                paper.id = paper_id
                report.paper_ids.append(paper_id)
            except Exception:
                logger.debug("Failed to insert: %s", paper.title[:60], exc_info=True)

            # Download PDF if available
            if paper.pdf_url:
                pdf_path = await self.downloader.download_pdf(paper)
                if pdf_path:
                    report.downloaded += 1
                    self.db.update_paper_pdf(
                        paper.id or "",
                        pdf_url=paper.pdf_url,
                        pdf_path=pdf_path,
                        status=PaperStatus.PDF_DOWNLOADED,
                    )
                    try:
                        self.indexer.index_paper(pdf_path, paper.id or "")
                        self.db.update_paper_status(paper.id or "", PaperStatus.INDEXED)
                        report.indexed += 1
                    except Exception:
                        report.failed_index += 1
                else:
                    report.failed_download += 1
            else:
                # Index from metadata
                try:
                    self.indexer.index_from_metadata(paper)
                    report.indexed += 1
                except Exception:
                    report.failed_index += 1

        logger.info(report.summary())
        return report
