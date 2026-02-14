"""CLI entry point for the AI Academic Research Agent."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.knowledge_base.db import Database
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter

console = Console()
logger = logging.getLogger("ai_researcher")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def get_db() -> Database:
    db = Database()
    db.initialize()
    return db


def get_router(db: Database) -> LLMRouter:
    return LLMRouter(db=db)


def get_vs() -> VectorStore:
    return VectorStore()


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(verbose: bool) -> None:
    """AI Academic Research Agent for Comparative Literature."""
    setup_logging(verbose)


# --- Monitor commands ---


@main.command()
@click.option("--since", default=None, help="Since date (YYYY-MM-DD)")
def monitor(since: str | None) -> None:
    """Scan journals for new publications."""
    from src.journal_monitor.monitor import run_monitor

    async def _run():
        db = get_db()
        try:
            summary = await run_monitor(db=db, since_date=since)
            console.print(Panel(f"[bold]Journal Monitor Results[/bold]"))
            table = Table()
            table.add_column("Journal")
            table.add_column("Found")
            table.add_column("New")
            table.add_column("Sources")
            for result in summary.journal_results:
                table.add_row(
                    result.journal_name,
                    str(result.papers_found),
                    str(result.papers_new),
                    ", ".join(result.sources_queried),
                )
            console.print(table)
            console.print(
                f"\n[green]Total: {summary.total_found} found, "
                f"{summary.total_new} new[/green]"
            )
        finally:
            db.close()

    asyncio.run(_run())


# --- Index commands ---


@main.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option("--paper-id", default=None, help="Paper ID (auto-generated if not set)")
def index(pdf_path: str, paper_id: str | None) -> None:
    """Index a PDF paper into the knowledge base."""
    from src.literature_indexer.indexer import Indexer

    db = get_db()
    vs = get_vs()
    try:
        indexer = Indexer(vector_store=vs)
        import uuid
        pid = paper_id or str(uuid.uuid4())
        parsed = indexer.index_paper(pdf_path, pid)
        console.print(f"[green]Indexed: {parsed.title or 'Unknown title'}[/green]")
        console.print(f"  Sections: {len(parsed.sections)}")
        console.print(f"  Quotations: {len(parsed.quotations)}")
        console.print(f"  References: {len(parsed.references)}")
    finally:
        db.close()


# --- Topic discovery ---


@main.command()
@click.option("--limit", default=5, help="Number of topics to generate")
def discover(limit: int) -> None:
    """Discover research gaps and propose topics."""
    from src.topic_discovery.gap_analyzer import analyze_gaps
    from src.topic_discovery.topic_scorer import score_topic

    async def _run():
        db = get_db()
        router = get_router(db)
        try:
            papers = db.search_papers(limit=200)
            if not papers:
                console.print("[yellow]No papers in database. Run 'monitor' first.[/yellow]")
                return

            console.print(f"Analyzing {len(papers)} papers for research gaps...")
            gaps = await analyze_gaps(papers, router)

            table = Table(title="Research Gap Proposals")
            table.add_column("#", width=3)
            table.add_column("Title")
            table.add_column("Score", width=6)
            table.add_column("Research Question")

            from src.knowledge_base.models import TopicProposal
            for i, gap in enumerate(gaps[:limit]):
                topic = TopicProposal(
                    title=gap.get("title", "Untitled"),
                    research_question=gap.get("potential_rq", ""),
                    gap_description=gap.get("description", ""),
                )
                scored = score_topic(topic, papers, router)
                db.insert_topic(scored)
                table.add_row(
                    str(i + 1),
                    scored.title[:50],
                    f"{scored.overall_score:.2f}",
                    scored.research_question[:80],
                )

            console.print(table)
        finally:
            db.close()

    asyncio.run(_run())


# --- Plan ---


@main.command()
@click.argument("topic_id")
@click.option("--journal", required=True, help="Target journal name")
@click.option("--language", default="en", type=click.Choice(["en", "zh", "fr"]))
def plan(topic_id: str, journal: str, language: str) -> None:
    """Create a research plan for a topic."""
    from src.knowledge_base.models import Language
    from src.research_planner.planner import ResearchPlanner

    async def _run():
        db = get_db()
        vs = get_vs()
        router = get_router(db)
        try:
            topics = db.get_topics()
            topic = next((t for t in topics if t.id == topic_id), None)
            if not topic:
                console.print(f"[red]Topic {topic_id} not found[/red]")
                return

            planner = ResearchPlanner(db, vs, router)
            result = await planner.create_plan(
                topic=topic,
                target_journal=journal,
                language=Language(language),
            )

            console.print(Panel(f"[bold]Research Plan Created[/bold]"))
            console.print(f"Thesis: {result.thesis_statement}")
            console.print(f"References: {len(result.reference_ids)}")
            console.print(f"\nOutline:")
            for i, section in enumerate(result.outline):
                console.print(f"  {i+1}. {section.title} (~{section.estimated_words} words)")
                console.print(f"     Argument: {section.argument[:100]}...")
        finally:
            db.close()

    asyncio.run(_run())


# --- Write ---


@main.command()
@click.argument("plan_id")
def write(plan_id: str) -> None:
    """Generate a manuscript from a research plan."""
    from src.writing_agent.writer import WritingAgent

    async def _run():
        db = get_db()
        vs = get_vs()
        router = get_router(db)
        try:
            plan_data = db.get_plan(plan_id)
            if not plan_data:
                console.print(f"[red]Plan {plan_id} not found[/red]")
                return

            import json
            from src.knowledge_base.models import Language, OutlineSection, ResearchPlan
            plan_obj = ResearchPlan(
                id=plan_data["id"],
                topic_id=plan_data["topic_id"],
                thesis_statement=plan_data["thesis_statement"],
                target_journal=plan_data["target_journal"],
                target_language=Language(plan_data["target_language"]),
                outline=[OutlineSection(**s) for s in json.loads(plan_data["outline"])],
                reference_ids=json.loads(plan_data["reference_ids"]),
            )

            writer = WritingAgent(db, vs, router)
            console.print("Writing manuscript (this may take a while)...")
            manuscript = await writer.write_full_manuscript(plan_obj)

            console.print(Panel(f"[bold green]Manuscript Generated[/bold green]"))
            console.print(f"Title: {manuscript.title[:80]}")
            console.print(f"Sections: {len(manuscript.sections)}")
            console.print(f"Word count: {manuscript.word_count}")
            console.print(f"ID: {manuscript.id}")
        finally:
            db.close()

    asyncio.run(_run())


# --- Verify ---


@main.command()
@click.argument("manuscript_id")
def verify(manuscript_id: str) -> None:
    """Verify all references in a manuscript."""
    from src.reference_verifier.verifier import ReferenceVerifier

    async def _run():
        db = get_db()
        try:
            # Load manuscript from DB
            row = db.conn.execute(
                "SELECT * FROM manuscripts WHERE id = ?", (manuscript_id,)
            ).fetchone()
            if not row:
                console.print(f"[red]Manuscript {manuscript_id} not found[/red]")
                return

            import json
            verifier = ReferenceVerifier(db)
            report = await verifier.verify_manuscript_references(
                manuscript_text=row["full_text"] or "",
                reference_ids=json.loads(row["reference_ids"]),
            )

            console.print(report.summary())
            await verifier.close()
        finally:
            db.close()

    asyncio.run(_run())


# --- Review ---


@main.command()
@click.argument("manuscript_id")
def review(manuscript_id: str) -> None:
    """Run self-review on a manuscript."""
    from src.self_review.reviewer import SelfReviewAgent

    async def _run():
        db = get_db()
        router = get_router(db)
        try:
            row = db.conn.execute(
                "SELECT * FROM manuscripts WHERE id = ?", (manuscript_id,)
            ).fetchone()
            if not row:
                console.print(f"[red]Manuscript {manuscript_id} not found[/red]")
                return

            import json
            ms = Manuscript(
                id=row["id"],
                plan_id=row["plan_id"],
                title=row["title"],
                target_journal=row["target_journal"],
                language=Language(row["language"]),
                sections=json.loads(row["sections"]),
                full_text=row["full_text"],
                abstract=row["abstract"],
                word_count=row["word_count"],
                version=row["version"],
            )

            reviewer = SelfReviewAgent()
            result = await reviewer.review_manuscript(ms, {}, router)

            console.print(Panel(f"[bold]Self-Review Results[/bold]"))
            console.print(f"Recommendation: {result.overall_recommendation}")

            table = Table(title="Scores")
            for key, value in result.scores.items():
                table.add_row(key, f"{value:.1f}")
            console.print(table)

            if result.comments:
                console.print("\n[bold]Comments:[/bold]")
                for c in result.comments:
                    console.print(f"  - {c}")
        finally:
            db.close()

    asyncio.run(_run())

    from src.knowledge_base.models import Language, Manuscript


# --- Format / Submit ---


@main.command()
@click.argument("manuscript_id")
@click.option("--output", "-o", default="output/manuscript.txt", help="Output file path")
def format_manuscript(manuscript_id: str, output: str) -> None:
    """Format a manuscript for submission."""
    from src.submission_manager.formatter import ManuscriptFormatter

    db = get_db()
    try:
        row = db.conn.execute(
            "SELECT * FROM manuscripts WHERE id = ?", (manuscript_id,)
        ).fetchone()
        if not row:
            console.print(f"[red]Manuscript {manuscript_id} not found[/red]")
            return

        import json
        from src.knowledge_base.models import Language

        ms = Manuscript(
            id=row["id"],
            plan_id=row["plan_id"],
            title=row["title"],
            target_journal=row["target_journal"],
            language=Language(row["language"]),
            sections=json.loads(row["sections"]),
            full_text=row["full_text"],
            abstract=row["abstract"],
            keywords=json.loads(row["keywords"]) if row["keywords"] else [],
            reference_ids=json.loads(row["reference_ids"]) if row["reference_ids"] else [],
            word_count=row["word_count"],
        )

        formatter = ManuscriptFormatter(db)
        output_path = formatter.export_to_file(ms, output)
        console.print(f"[green]Manuscript exported to: {output_path}[/green]")
    finally:
        db.close()


# --- Run full pipeline ---


@main.command()
@click.option("--journal", required=True, help="Target journal name")
@click.option("--language", default="en", type=click.Choice(["en", "zh", "fr"]))
def pipeline(journal: str, language: str) -> None:
    """Run the full research pipeline from monitoring to submission."""
    from src.orchestrator import WorkflowState, create_workflow

    async def _run():
        db = get_db()
        vs = get_vs()
        router = get_router(db)
        try:
            workflow = create_workflow(db, vs, router)
            initial_state = WorkflowState(
                target_journal=journal,
                target_language=language,
            )
            console.print(Panel("[bold]Starting Full Research Pipeline[/bold]"))
            console.print(f"Target journal: {journal}")
            console.print(f"Language: {language}")
            console.print()

            result = await workflow.ainvoke(initial_state)
            state = result if isinstance(result, WorkflowState) else WorkflowState(**result)

            if state.errors:
                console.print("[yellow]Warnings/Errors:[/yellow]")
                for err in state.errors:
                    console.print(f"  [red]- {err}[/red]")

            if state.submission_ready:
                console.print("[bold green]Submission materials ready![/bold green]")
            elif state.manuscript:
                console.print("[yellow]Manuscript generated, awaiting human review.[/yellow]")
                console.print("Run 'review' and 'format-manuscript' commands to continue.")
            else:
                console.print("[yellow]Pipeline completed at discovery phase.[/yellow]")
                console.print("Run 'discover' to see proposed topics.")
        finally:
            db.close()

    asyncio.run(_run())


# --- Stats ---


@main.command()
def stats() -> None:
    """Show database and usage statistics."""
    db = get_db()
    try:
        paper_count = db.count_papers()
        topic_count = len(db.get_topics())
        reflexion_count = len(db.get_reflexion_memories())
        usage = db.get_llm_usage_summary()

        console.print(Panel("[bold]Research Agent Statistics[/bold]"))
        console.print(f"Papers indexed: {paper_count}")
        console.print(f"Topics proposed: {topic_count}")
        console.print(f"Reflexion memories: {reflexion_count}")

        if usage:
            table = Table(title="LLM Usage")
            table.add_column("Model:Task")
            table.add_column("Calls")
            table.add_column("Tokens")
            table.add_column("Cost (USD)")
            for key, data in usage.items():
                table.add_row(
                    key,
                    str(data.get("calls", 0)),
                    str(data.get("tokens", 0)),
                    f"${data.get('cost', 0):.4f}",
                )
            console.print(table)
    finally:
        db.close()


# --- Learn journal style ---


@main.command()
@click.argument("journal_name")
@click.argument("pdf_paths", nargs=-1, type=click.Path(exists=True))
def learn_style(journal_name: str, pdf_paths: tuple[str, ...]) -> None:
    """Learn a journal's style from sample papers."""
    from src.journal_style_learner.learner import JournalStyleLearner
    from src.literature_indexer.pdf_parser import parse_pdf

    async def _run():
        db = get_db()
        router = get_router(db)
        try:
            if not pdf_paths:
                console.print("[red]Provide at least one PDF path[/red]")
                return

            sample_texts = []
            for pdf_path in pdf_paths:
                parsed = parse_pdf(pdf_path)
                if parsed.full_text:
                    sample_texts.append(parsed.full_text)

            learner = JournalStyleLearner()
            profile = await learner.learn_style(journal_name, sample_texts, router)

            console.print(f"[green]Style profile learned for: {journal_name}[/green]")
            console.print(f"Citation style: {profile.get('formatting', {}).get('citation_style', 'unknown')}")
        finally:
            db.close()

    asyncio.run(_run())


@main.command(name="search-references")
@click.argument("topic")
@click.option("--max-results", default=30, help="Max results per API source")
@click.option("--wishlist", "-w", default="data/wishlist.json", help="Path to save wishlist JSON")
def search_references(topic: str, max_results: int, wishlist: str) -> None:
    """Search for references and generate a PDF wishlist.

    Searches academic APIs, auto-downloads what it can, and outputs a
    wishlist of papers that still need PDFs. You can then:

      1. Check the wishlist:  ai-researcher wishlist
      2. Download PDFs yourself and put them in data/papers/
      3. Index them:  ai-researcher index-folder data/papers/
    """
    import json as _json
    from src.reference_acquisition.pipeline import ReferenceAcquisitionPipeline

    async def _run():
        db = get_db()
        vs = get_vs()
        try:
            pipeline = ReferenceAcquisitionPipeline(db, vs)
            console.print(f"Searching for references: [bold]{topic}[/bold]\n")
            report = await pipeline.acquire_references(topic, max_results=max_results)

            # Summary table
            table = Table(title="Reference Acquisition Report")
            table.add_column("Metric", style="bold")
            table.add_column("Count", justify="right")
            table.add_row("Papers found", str(report.found))
            table.add_row("Auto-downloaded PDFs", str(report.downloaded))
            table.add_row("Indexed (full text + metadata)", str(report.indexed))
            table.add_row("Still need PDF", str(report.found - report.downloaded))
            console.print(table)

            # Generate wishlist: papers that still need PDFs
            needing = db.get_papers_needing_pdf()
            if needing:
                console.print(f"\n[bold yellow]Papers still needing PDF ({len(needing)}):[/bold yellow]")
                wl_table = Table(show_lines=True)
                wl_table.add_column("#", width=3)
                wl_table.add_column("Title", max_width=50)
                wl_table.add_column("Authors", max_width=25)
                wl_table.add_column("Year", width=5)
                wl_table.add_column("DOI", max_width=30)

                wishlist_data = []
                for i, p in enumerate(needing):
                    wl_table.add_row(
                        str(i + 1),
                        p.title[:50],
                        ", ".join(p.authors[:2]) if p.authors else "-",
                        str(p.year),
                        p.doi or "-",
                    )
                    wishlist_data.append({
                        "id": p.id,
                        "title": p.title,
                        "authors": p.authors,
                        "year": p.year,
                        "doi": p.doi,
                        "journal": p.journal,
                        "url": p.url,
                        "pdf_url": p.pdf_url,
                    })
                console.print(wl_table)

                # Save wishlist JSON
                wl_path = Path(wishlist)
                wl_path.parent.mkdir(parents=True, exist_ok=True)
                wl_path.write_text(_json.dumps(wishlist_data, indent=2, ensure_ascii=False))
                console.print(f"\n[green]Wishlist saved to: {wl_path}[/green]")

                console.print(
                    "\n[bold]Next steps:[/bold]\n"
                    "  1. Download PDFs yourself (university library, etc.)\n"
                    "  2. Put them in [cyan]data/papers/[/cyan]\n"
                    "  3. Run: [cyan]ai-researcher index-folder data/papers/[/cyan]\n"
                    "  Or index one at a time: [cyan]ai-researcher index <pdf_path>[/cyan]"
                )
            else:
                console.print("\n[green]All papers have been indexed![/green]")
        finally:
            db.close()

    asyncio.run(_run())


@main.command(name="search-books")
@click.argument("queries", nargs=-1, required=True)
@click.option("--max-results", default=20, help="Max results per query")
def search_books(queries: tuple[str, ...], max_results: int) -> None:
    """Search Google Books & Open Library for novels, theory, and criticism.

    Provide one or more search queries as arguments. Example:

        ai-researcher search-books "Heart of Darkness Conrad" "Orientalism Said"
    """
    import json as _json
    from src.reference_acquisition.pipeline import ReferenceAcquisitionPipeline

    async def _run():
        db = get_db()
        vs = get_vs()
        try:
            pipeline = ReferenceAcquisitionPipeline(db, vs)
            console.print(f"Searching books/web for: {', '.join(queries)}")
            report = await pipeline.acquire_broad_references(
                list(queries), max_results=max_results
            )

            table = Table(title="Web Reference Acquisition Report")
            table.add_column("Metric", style="bold")
            table.add_column("Count", justify="right")
            table.add_row("Books/texts found", str(report.found))
            table.add_row("Downloaded", str(report.downloaded))
            table.add_row("Indexed", str(report.indexed))
            table.add_row("Still need PDF", str(report.found - report.downloaded))
            console.print(table)

            needing = db.get_papers_needing_pdf()
            if needing:
                console.print(
                    f"\n[yellow]{len(needing)} papers/books still need PDFs.[/yellow]\n"
                    "Run [cyan]ai-researcher wishlist[/cyan] to see the full list."
                )
        finally:
            db.close()

    asyncio.run(_run())


@main.command()
def wishlist() -> None:
    """Show papers/books that still need PDFs.

    These are references the system found via API search but couldn't
    auto-download. Download the PDFs yourself and put them in data/papers/,
    then run: ai-researcher index-folder data/papers/
    """
    db = get_db()
    try:
        needing = db.get_papers_needing_pdf(limit=500)
        if not needing:
            console.print("[green]All papers have PDFs or are indexed![/green]")
            return

        console.print(Panel(f"[bold]PDF Wishlist — {len(needing)} papers need full text[/bold]"))

        table = Table(show_lines=True)
        table.add_column("#", width=4)
        table.add_column("Title", max_width=50)
        table.add_column("Authors", max_width=25)
        table.add_column("Year", width=5)
        table.add_column("DOI / URL")

        for i, p in enumerate(needing):
            doi_or_url = p.doi or p.url or "-"
            if p.doi:
                doi_or_url = f"https://doi.org/{p.doi}"
            table.add_row(
                str(i + 1),
                p.title[:50],
                ", ".join(p.authors[:2]) if p.authors else "-",
                str(p.year),
                doi_or_url[:50],
            )
        console.print(table)

        console.print(
            "\n[bold]How to provide PDFs:[/bold]\n"
            "  1. Download from your university library, Sci-Hub, or publisher\n"
            "  2. Put PDF files into [cyan]data/papers/[/cyan]\n"
            "  3. Run [cyan]ai-researcher index-folder data/papers/[/cyan]\n"
            "\n  The system will match filenames containing DOIs to the right papers.\n"
            "  Or index individually: [cyan]ai-researcher index path/to/paper.pdf --paper-id <ID>[/cyan]"
        )
    finally:
        db.close()


@main.command(name="resolve-oa")
@click.option("--limit", "-n", default=50, help="Max papers to resolve")
@click.option("--dry-run", is_flag=True, help="Show found URLs without downloading")
def resolve_oa(limit: int, dry_run: bool) -> None:
    """Resolve OA PDF URLs for papers missing full text.

    Queries Unpaywall, CORE, arXiv, Europe PMC, and DOI content
    negotiation to find free PDF downloads. Downloads and indexes
    any resolved papers automatically.

    Use --dry-run to preview what would be downloaded.
    """
    from src.reference_acquisition.oa_resolver import OAResolver

    async def _run():
        db = get_db()
        vs = get_vs()
        try:
            from src.knowledge_base.models import PaperStatus
            from src.literature_indexer.indexer import Indexer
            from src.reference_acquisition.downloader import PDFDownloader

            papers = db.get_papers_needing_pdf(limit=limit)
            if not papers:
                console.print("[green]No papers need PDFs![/green]")
                return

            console.print(f"Resolving OA URLs for [bold]{len(papers)}[/bold] papers...\n")

            resolver = OAResolver()
            downloader = PDFDownloader()
            indexer = Indexer(vector_store=vs)

            resolved = 0
            downloaded = 0
            indexed = 0

            table = Table(title="OA Resolution Results")
            table.add_column("#", width=4)
            table.add_column("Title", max_width=40)
            table.add_column("Source", width=15)
            table.add_column("URL", max_width=50)
            table.add_column("Status", width=12)

            for i, paper in enumerate(papers):
                url = await resolver.resolve_pdf_url(paper)
                if url:
                    resolved += 1
                    # Determine source from URL
                    source = "unknown"
                    if "unpaywall" in url or "doi.org" not in url:
                        if "arxiv.org" in url:
                            source = "arXiv"
                        elif "europepmc" in url:
                            source = "Europe PMC"
                        elif "core.ac.uk" in url:
                            source = "CORE"
                        else:
                            source = "Unpaywall"

                    if dry_run:
                        table.add_row(
                            str(i + 1),
                            paper.title[:40],
                            source,
                            url[:50],
                            "[yellow]dry-run[/yellow]",
                        )
                    else:
                        pdf_path = await downloader.download_with_fallback(paper, [url])
                        if pdf_path:
                            downloaded += 1
                            db.update_paper_pdf(
                                paper.id or "",
                                pdf_url=url,
                                pdf_path=pdf_path,
                                status=PaperStatus.PDF_DOWNLOADED,
                            )
                            try:
                                indexer.index_paper(pdf_path, paper.id or "")
                                db.update_paper_status(paper.id or "", PaperStatus.INDEXED)
                                indexed += 1
                                status = "[green]indexed[/green]"
                            except Exception:
                                status = "[yellow]downloaded[/yellow]"
                        else:
                            status = "[red]dl failed[/red]"

                        table.add_row(
                            str(i + 1),
                            paper.title[:40],
                            source,
                            url[:50],
                            status,
                        )
                else:
                    table.add_row(
                        str(i + 1),
                        paper.title[:40],
                        "-",
                        "-",
                        "[dim]no OA[/dim]",
                    )

            console.print(table)

            console.print(f"\n[bold]Summary:[/bold]")
            console.print(f"  Papers checked: {len(papers)}")
            console.print(f"  OA URLs found: {resolved}")
            if not dry_run:
                console.print(f"  Downloaded: {downloaded}")
                console.print(f"  Indexed: {indexed}")

            await resolver.close()
        finally:
            db.close()

    asyncio.run(_run())


@main.command(name="index-folder")
@click.argument("folder", type=click.Path(exists=True, file_okay=False))
@click.option("--match-db/--no-match-db", default=True, help="Try to match PDFs to existing DB papers")
def index_folder(folder: str, match_db: bool) -> None:
    """Batch-index all PDFs in a folder into the knowledge base.

    Scans the folder for *.pdf files, tries to match each to an existing
    paper record by DOI in filename, then indexes into ChromaDB.

    Example:
        ai-researcher index-folder data/papers/
    """
    import re
    import uuid

    from src.knowledge_base.models import PaperStatus
    from src.literature_indexer.indexer import Indexer

    db = get_db()
    vs = get_vs()
    try:
        indexer = Indexer(vector_store=vs)
        folder_path = Path(folder)
        pdfs = sorted(folder_path.glob("*.pdf"))

        if not pdfs:
            console.print(f"[yellow]No PDF files found in {folder}[/yellow]")
            return

        console.print(f"Found [bold]{len(pdfs)}[/bold] PDFs in {folder}\n")

        indexed = 0
        skipped = 0
        failed = 0

        for pdf in pdfs:
            fname = pdf.stem

            # Try to match to existing paper in DB
            paper_id = None
            if match_db:
                # Try DOI-based matching: filenames like "10.1234_something"
                doi_candidate = re.sub(r"_", "/", fname, count=1)
                paper = db.get_paper_by_doi(doi_candidate)
                if paper:
                    paper_id = paper.id
                    if paper.status in (PaperStatus.INDEXED, PaperStatus.PDF_DOWNLOADED, PaperStatus.ANALYZED):
                        console.print(f"  [dim]Skip (already indexed): {pdf.name}[/dim]")
                        skipped += 1
                        continue

            if not paper_id:
                paper_id = str(uuid.uuid4())

            try:
                parsed = indexer.index_paper(str(pdf), paper_id)
                # Update DB record
                db.update_paper_pdf(
                    paper_id,
                    pdf_path=str(pdf),
                    status=PaperStatus.INDEXED,
                )
                console.print(f"  [green]Indexed:[/green] {pdf.name} -> {parsed.title or fname}")
                indexed += 1
            except Exception as e:
                console.print(f"  [red]Failed:[/red] {pdf.name}: {e}")
                failed += 1

        console.print(
            f"\n[bold]Results:[/bold] {indexed} indexed, {skipped} skipped, {failed} failed"
        )
    finally:
        db.close()


@main.command(name="config-proxy")
@click.option("--base-url", prompt="EZproxy base URL", help="e.g. https://proxy.university.edu")
@click.option("--username", prompt="Institutional username", help="Your university login")
@click.option(
    "--password-env",
    default="INSTITUTIONAL_PASSWORD",
    help="Env var name for password (default: INSTITUTIONAL_PASSWORD)",
)
@click.option(
    "--proxy-type",
    default="ezproxy",
    type=click.Choice(["ezproxy", "shibboleth_ezproxy", "prefix"]),
    help="Proxy type",
)
def config_proxy(base_url: str, username: str, password_env: str, proxy_type: str) -> None:
    """Configure institutional proxy for paywalled PDF access.

    Run this once to set up your university's EZproxy. The password
    is read from an environment variable (not stored in the config file).

    Example:
        export INSTITUTIONAL_PASSWORD='mypassword'
        ai-researcher config-proxy --base-url https://proxy.uni.edu --username jdoe
    """
    import os

    from src.reference_acquisition.proxy_session import InstitutionalProxy

    proxy = InstitutionalProxy()
    proxy.update_config(
        base_url=base_url.rstrip("/"),
        username=username,
        password_env=password_env,
        proxy_type=proxy_type,
    )
    proxy.save_config()

    console.print(f"\n[green]Proxy config saved to config/proxy.yaml[/green]")
    console.print(f"  Type: {proxy_type}")
    console.print(f"  URL: {base_url}")
    console.print(f"  Username: {username}")
    console.print(f"  Password env: {password_env}")

    if not os.environ.get(password_env):
        console.print(
            f"\n[yellow]Warning: env var {password_env} is not set.[/yellow]\n"
            f"Set it before running proxy-download:\n"
            f"  export {password_env}='your_password'"
        )
    else:
        console.print(f"\n[green]Password env var {password_env} is set.[/green]")

        # Test login
        async def _test():
            try:
                success = await proxy.login()
                if success:
                    console.print("[green]Login test: SUCCESS[/green]")
                else:
                    console.print("[red]Login test: FAILED (check credentials)[/red]")
                await proxy.close()
            except Exception as e:
                console.print(f"[red]Login test error: {e}[/red]")

        console.print("\nTesting login...")
        asyncio.run(_test())


@main.command(name="proxy-download")
@click.option("--limit", "-n", default=50, help="Max papers to process")
@click.option("--dry-run", is_flag=True, help="Show rewritten URLs without downloading")
def proxy_download(limit: int, dry_run: bool) -> None:
    """Download paywalled PDFs through institutional proxy.

    Fetches papers that still need PDFs and have DOIs, rewrites their
    publisher URLs through the configured EZproxy, and downloads.

    Configure first with: ai-researcher config-proxy
    """
    from src.reference_acquisition.proxy_session import InstitutionalProxy

    async def _run():
        db = get_db()
        vs = get_vs()
        try:
            proxy = InstitutionalProxy()
            if not proxy.is_configured:
                console.print("[red]Proxy not configured.[/red]")
                console.print(proxy.test_connection())
                console.print("\nRun [cyan]ai-researcher config-proxy[/cyan] first.")
                return

            papers = db.get_papers_needing_pdf(limit=limit)
            papers_with_doi = [p for p in papers if p.doi]
            if not papers_with_doi:
                console.print("[green]No papers with DOIs need PDFs![/green]")
                return

            console.print(f"Processing [bold]{len(papers_with_doi)}[/bold] papers via proxy...\n")

            if not dry_run:
                success = await proxy.login()
                if not success:
                    console.print("[red]Proxy login failed. Check credentials.[/red]")
                    await proxy.close()
                    return

            from src.knowledge_base.models import PaperStatus
            from src.literature_indexer.indexer import Indexer
            from src.reference_acquisition.downloader import PDFDownloader

            downloader = PDFDownloader(proxy=proxy)
            indexer = Indexer(vector_store=vs)

            downloaded = 0
            indexed = 0

            table = Table(title="Proxy Download Results")
            table.add_column("#", width=4)
            table.add_column("Title", max_width=40)
            table.add_column("DOI", max_width=30)
            table.add_column("Proxy URL", max_width=40)
            table.add_column("Status", width=12)

            for i, paper in enumerate(papers_with_doi):
                doi_url = f"https://doi.org/{paper.doi}"

                # Resolve DOI to publisher URL for display
                publisher_url = doi_url
                try:
                    async with httpx.AsyncClient(
                        timeout=10.0, follow_redirects=True
                    ) as tmp:
                        resp = await tmp.head(doi_url)
                        publisher_url = str(resp.url)
                except Exception:
                    pass

                proxy_url = proxy.rewrite_url(publisher_url) if proxy.needs_proxy(publisher_url) else publisher_url

                if dry_run:
                    table.add_row(
                        str(i + 1),
                        paper.title[:40],
                        paper.doi[:30] if paper.doi else "-",
                        proxy_url[:40],
                        "[yellow]dry-run[/yellow]",
                    )
                else:
                    pdf_path = await downloader.download_via_proxy(paper)
                    if pdf_path:
                        downloaded += 1
                        db.update_paper_pdf(
                            paper.id or "",
                            pdf_url=publisher_url,
                            pdf_path=pdf_path,
                            status=PaperStatus.PDF_DOWNLOADED,
                        )
                        try:
                            indexer.index_paper(pdf_path, paper.id or "")
                            db.update_paper_status(paper.id or "", PaperStatus.INDEXED)
                            indexed += 1
                            status = "[green]indexed[/green]"
                        except Exception:
                            status = "[yellow]downloaded[/yellow]"
                    else:
                        status = "[red]failed[/red]"

                    table.add_row(
                        str(i + 1),
                        paper.title[:40],
                        paper.doi[:30] if paper.doi else "-",
                        proxy_url[:40],
                        status,
                    )

            console.print(table)

            console.print(f"\n[bold]Summary:[/bold]")
            console.print(f"  Papers processed: {len(papers_with_doi)}")
            if not dry_run:
                console.print(f"  Downloaded: {downloaded}")
                console.print(f"  Indexed: {indexed}")

            await proxy.close()
        finally:
            db.close()

    asyncio.run(_run())


@main.command()
@click.option("--no-immediate", is_flag=True, help="Skip initial run, only schedule future runs")
def scheduler(no_immediate: bool) -> None:
    """Start the periodic monitoring scheduler (runs until Ctrl+C)."""
    from src.scheduler import run_scheduler_blocking

    console.print(Panel("[bold]Starting Periodic Scheduler[/bold]"))
    console.print("The scheduler will run journal monitoring at the interval configured in journals.yaml.")
    console.print("Press Ctrl+C to stop.\n")
    run_scheduler_blocking(run_immediately=not no_immediate)


if __name__ == "__main__":
    main()
