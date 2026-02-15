"""Orchestrate search -> download -> index for reference acquisition."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

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
    local_hits: int = 0
    paper_ids: list[str] = field(default_factory=list)
    top_paper_ids: list[str] = field(default_factory=list)
    expanded_queries: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Reference Acquisition: query='{self.query}'\n"
            f"  Expanded queries: {len(self.expanded_queries)}\n"
            f"  Found: {self.found} | With PDF URL: {self.papers_with_pdf_url}"
            f" | Local KB hits: {self.local_hits}\n"
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
        llm_router: Optional[Any] = None,
    ):
        self.db = db
        self.vs = vector_store
        self.llm_router = llm_router
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
        progress_callback: Optional[Any] = None,
        index_metadata_only: bool = False,
    ) -> AcquisitionReport:
        """Search for papers, download PDFs, and index into knowledge base.

        Args:
            topic: Research topic / keywords to search.
            max_results: Max results per API source.

        Returns:
            AcquisitionReport with statistics.
        """
        report = AcquisitionReport(query=topic)

        async def _progress(frac: float, msg: str) -> None:
            if progress_callback:
                await progress_callback(frac, msg)

        # Step 1: Search — use LLM-expanded multi-language queries if router available
        if self.llm_router:
            all_papers, top_papers = await self.searcher.search_topic_expanded(
                topic,
                llm_router=self.llm_router,
                max_results_per_source=max_results,
                progress_callback=_progress,
            )
        else:
            await _progress(0.1, "Searching (no LLM expansion)...")
            all_papers = await self.searcher.search_topic(
                topic, max_results_per_source=max_results
            )
            top_papers = all_papers  # no filtering without LLM

        # Step 1.5: Also search locally indexed papers in ChromaDB
        await _progress(0.60, "Searching local knowledge base...")
        local_hits = await self.searcher.search_local(topic, self.vs, n_results=20)
        local_paper_ids = {h["paper_id"] for h in local_hits}
        report.local_hits = len(local_paper_ids)

        report.found = len(all_papers)
        report.papers_with_pdf_url = sum(1 for p in all_papers if p.pdf_url)

        if not all_papers:
            logger.info("No papers found for topic: %s", topic)
            return report

        await _progress(0.62, f"Saving {len(all_papers)} papers to DB...")

        # Step 2a: Insert ALL papers into DB (metadata is cheap)
        for paper in all_papers:
            try:
                paper_id = self.db.insert_paper(paper)
                paper.id = paper_id
                report.paper_ids.append(paper_id)
            except Exception:
                logger.debug("Failed to insert paper: %s", paper.title[:60], exc_info=True)

        # Step 2b: Only proceed with top papers for download/indexing
        # (Remaining papers are in SQLite for ReferenceSelector to use)
        report.top_paper_ids = [p.id for p in top_papers if p.id]
        papers = top_papers
        if len(all_papers) > len(papers):
            logger.info(
                "All %d papers stored in DB; top %d selected for download/indexing",
                len(all_papers), len(papers),
            )
        await _progress(0.65, f"Downloading top {len(papers)} papers...")

        # ---- Phase allocation (real progress based on paper count) ----
        # Search+local:  0-65%  (handled above)
        # PDF download:  65-75% (papers with direct URL)
        # OA resolution: 75-90% (heaviest — per-paper API calls)
        # Proxy:         90-95%
        # Metadata idx:  95-99%
        total = len(papers) or 1  # avoid division by zero

        # Step 3: Download PDFs for papers that have pdf_url
        papers_with_url = [p for p in papers if p.pdf_url]
        downloaded_ids: set[str] = set()
        for i, paper in enumerate(papers_with_url):
            await _progress(
                0.65 + 0.10 * (i / max(len(papers_with_url), 1)),
                f"Downloading PDF {i+1}/{len(papers_with_url)}: {paper.title[:40]}..."
            )
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
        for i, paper in enumerate(papers_needing_oa):
            await _progress(
                0.75 + 0.15 * (i / max(len(papers_needing_oa), 1)),
                f"OA resolving {i+1}/{len(papers_needing_oa)}: {paper.title[:40]}..."
            )
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
            for i, paper in enumerate(papers_needing_proxy):
                await _progress(
                    0.90 + 0.05 * (i / max(len(papers_needing_proxy), 1)),
                    f"Proxy download {i+1}/{len(papers_needing_proxy)}: {paper.title[:40]}..."
                )
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
        # Skip by default — embedding each paper's metadata is slow and
        # rate-limited; the metadata is already in SQLite for keyword lookup.
        if index_metadata_only:
            papers_without_pdf = [
                p for p in papers
                if (p.id or "") not in downloaded_ids
            ]
            for i, paper in enumerate(papers_without_pdf):
                if i % 10 == 0:
                    await _progress(
                        0.95 + 0.04 * (i / max(len(papers_without_pdf), 1)),
                        f"Indexing metadata {i+1}/{len(papers_without_pdf)}..."
                    )
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
        else:
            skipped = len([p for p in papers if (p.id or "") not in downloaded_ids])
            if skipped:
                logger.info("Skipped metadata-only indexing for %d papers (no PDF)", skipped)

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
