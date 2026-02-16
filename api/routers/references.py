"""Reference acquisition and upload endpoints."""
import time
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from api.deps import get_db, get_vs, get_router, get_task_manager

router = APIRouter(tags=["references"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "papers"


class SearchRequest(BaseModel):
    topic: str
    max_results: int = 50


@router.post("/references/search")
async def search_references(req: SearchRequest, db=Depends(get_db), vs=Depends(get_vs), llm=Depends(get_router), tm=Depends(get_task_manager)):
    async def run_search(task_mgr, task_id):
        import sys
        from pathlib import Path as P
        PROJECT_ROOT = P(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.reference_acquisition.pipeline import ReferenceAcquisitionPipeline

        async def on_progress(frac: float, msg: str) -> None:
            await task_mgr.update_progress(task_id, frac, msg)

        pipeline = ReferenceAcquisitionPipeline(db=db, vector_store=vs, llm_router=llm)
        report = await pipeline.acquire_references(
            topic=req.topic,
            max_results=req.max_results,
            progress_callback=on_progress,
        )
        # Persist search session to SQLite
        session_id = f"s_{int(time.time()*1000)}"
        db.insert_search_session(
            session_id=session_id,
            query=req.topic,
            paper_ids=report.paper_ids,
            found=report.found,
            downloaded=report.downloaded,
            indexed=report.indexed,
            top_paper_ids=report.top_paper_ids or None,
        )
        await task_mgr.update_progress(task_id, 1.0, "Search complete")
        return {
            "query": report.query,
            "found": report.found,
            "downloaded": report.downloaded,
            "indexed": report.indexed,
            "oa_resolved": report.oa_resolved,
            "local_hits": report.local_hits,
            "summary": report.summary(),
        }

    task_id = tm.create_task("ref_search", run_search)
    return {"task_id": task_id}


@router.post("/references/upload")
async def upload_pdf(file: UploadFile = File(...), db=Depends(get_db), vs=Depends(get_vs)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    # Index the uploaded PDF
    try:
        import sys
        from pathlib import Path as P
        PROJECT_ROOT = P(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.literature_indexer.indexer import Indexer
        indexer = Indexer(vector_store=vs)
        result = indexer.index_paper(str(dest), None)
        return {"filename": file.filename, "path": str(dest), "indexed": True, "details": str(result)}
    except Exception as e:
        return {"filename": file.filename, "path": str(dest), "indexed": False, "error": str(e)}


@router.get("/references/sessions")
async def get_sessions(db=Depends(get_db)):
    """Return recent search session summaries for plan context."""
    from src.knowledge_base.models import PaperStatus
    sessions = db.get_search_sessions()[:10]
    result = []
    for s in sessions:
        # Count how many of this session's papers are indexed
        indexed_count = 0
        for pid in s["paper_ids"]:
            paper = db.get_paper(pid)
            if paper and paper.status == PaperStatus.INDEXED:
                indexed_count += 1
        result.append({
            "id": s["id"],
            "query": s["query"],
            "total_papers": len(s["paper_ids"]),
            "indexed_count": indexed_count,
            "created_at": s["created_at"],
        })
    return {"sessions": result}


@router.get("/references/wishlist")
async def get_wishlist(db=Depends(get_db)):
    """Return papers needing PDFs, grouped by search session.

    Sessions are read from SQLite (persistent across restarts).
    Returns sessions in reverse chronological order (newest first).
    Papers not belonging to any session go into an "Earlier searches" group.
    """
    all_needing = db.get_papers_needing_pdf(limit=2000)
    needing_ids = {p.id for p in all_needing}
    needing_map = {p.id: p for p in all_needing}

    def _paper_dict(p, recommended: bool = False):
        return {
            "id": p.id,
            "title": p.title,
            "authors": p.authors,
            "year": p.year,
            "doi": p.doi,
            "journal": p.journal,
            "recommended": recommended,
        }

    groups = []
    claimed_ids: set[str] = set()

    # Build groups from DB-persisted search sessions (newest first)
    sessions = db.get_search_sessions()
    for session in sessions:
        recommended_set = set(session.get("recommended_ids", []))
        session_needing = [
            pid for pid in session["paper_ids"]
            if pid in needing_ids and pid not in claimed_ids
        ]
        if not session_needing:
            continue
        claimed_ids.update(session_needing)
        ts = session["created_at"]
        try:
            from datetime import datetime
            timestamp = datetime.fromisoformat(ts).timestamp()
        except Exception:
            timestamp = 0
        # Build paper list: recommended first, then metadata-only
        papers_rec = [
            _paper_dict(needing_map[pid], recommended=True)
            for pid in session_needing
            if pid in needing_map and pid in recommended_set
        ]
        papers_meta = [
            _paper_dict(needing_map[pid], recommended=False)
            for pid in session_needing
            if pid in needing_map and pid not in recommended_set
        ]
        groups.append({
            "id": session["id"],
            "query": session["query"],
            "timestamp": timestamp,
            "total_found": session["found"],
            "downloaded": session["downloaded"],
            "needing_pdf": len(session_needing),
            "recommended_count": len(papers_rec),
            "papers": papers_rec + papers_meta,
        })

    # Remaining papers not in any session
    unclaimed = [p for p in all_needing if p.id not in claimed_ids]
    if unclaimed:
        groups.append({
            "id": "other",
            "query": "Earlier searches",
            "timestamp": 0,
            "total_found": len(unclaimed),
            "downloaded": 0,
            "needing_pdf": len(unclaimed),
            "recommended_count": 0,
            "papers": [_paper_dict(p) for p in unclaimed],
        })

    total = sum(g["needing_pdf"] for g in groups)
    return {
        "total_count": total,
        "groups": groups,
    }


@router.get("/references/downloaded")
async def get_downloaded(db=Depends(get_db)):
    """Return downloaded/indexed papers, grouped by search session."""
    from src.knowledge_base.models import PaperStatus
    all_downloaded = db.search_papers(status=PaperStatus.INDEXED, limit=2000)
    all_downloaded += db.search_papers(status=PaperStatus.PDF_DOWNLOADED, limit=2000)
    downloaded_ids = {p.id for p in all_downloaded}
    downloaded_map = {p.id: p for p in all_downloaded}

    def _paper_dict(p):
        return {
            "id": p.id,
            "title": p.title,
            "authors": p.authors,
            "year": p.year,
            "doi": p.doi,
            "journal": p.journal,
            "status": p.status.value,
            "pdf_path": p.pdf_path,
        }

    groups = []
    claimed_ids: set[str] = set()

    sessions = db.get_search_sessions()
    for session in sessions:
        session_downloaded = [
            pid for pid in session["paper_ids"]
            if pid in downloaded_ids and pid not in claimed_ids
        ]
        if not session_downloaded:
            continue
        claimed_ids.update(session_downloaded)
        ts = session["created_at"]
        try:
            from datetime import datetime
            timestamp = datetime.fromisoformat(ts).timestamp()
        except Exception:
            timestamp = 0
        groups.append({
            "id": session["id"],
            "query": session["query"],
            "timestamp": timestamp,
            "paper_count": len(session_downloaded),
            "papers": [_paper_dict(downloaded_map[pid]) for pid in session_downloaded if pid in downloaded_map],
        })

    # Remaining papers not in any session
    unclaimed = [p for p in all_downloaded if p.id not in claimed_ids]
    if unclaimed:
        groups.append({
            "id": "other",
            "query": "Other downloads",
            "timestamp": 0,
            "paper_count": len(unclaimed),
            "papers": [_paper_dict(p) for p in unclaimed],
        })

    total = sum(g["paper_count"] for g in groups)
    return {
        "total_count": total,
        "groups": groups,
    }


@router.get("/references/pdf/{paper_id}")
async def get_pdf(paper_id: str, db=Depends(get_db)):
    """Serve a downloaded PDF for in-browser viewing."""
    paper = db.get_paper(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    if not paper.pdf_path:
        raise HTTPException(404, "No PDF available for this paper")
    pdf_file = Path(paper.pdf_path)
    if not pdf_file.is_file():
        raise HTTPException(404, "PDF file not found on disk")
    return FileResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=\"{pdf_file.name}\""},
    )


class BrowserDownloadRequest(BaseModel):
    session_id: Optional[str] = None
    limit: int = 20


@router.post("/references/browser-download")
async def browser_download(req: BrowserDownloadRequest, db=Depends(get_db), vs=Depends(get_vs), tm=Depends(get_task_manager)):
    """Use Playwright browser to download PDFs from Sci-Hub/LibGen."""
    async def run_download(task_mgr, task_id):
        import sys
        from pathlib import Path as P
        PROJECT_ROOT = P(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.reference_acquisition.browser_downloader import BrowserDownloader
        from src.knowledge_base.models import PaperStatus
        from src.literature_indexer.indexer import Indexer

        await task_mgr.update_progress(task_id, 0.05, "Finding papers to download...")

        # Get recommended papers with DOIs that need PDFs
        if req.session_id:
            paper_ids = db.get_session_paper_ids(req.session_id)
            # Filter for recommended only
            sessions = db.get_search_sessions()
            recommended_set = set()
            for s in sessions:
                if s["id"] == req.session_id:
                    recommended_set = set(s.get("recommended_ids", []))
                    break
            paper_ids = [pid for pid in paper_ids if pid in recommended_set] if recommended_set else paper_ids
        else:
            all_needing = db.get_papers_needing_pdf(limit=500)
            paper_ids = [p.id for p in all_needing]

        # Get paper objects with DOIs, skip junk titles
        from src.literature_indexer.indexer import is_junk_title
        papers_to_download = []
        for pid in paper_ids:
            p = db.get_paper(pid)
            if p and p.doi and not p.pdf_path and not is_junk_title(p.title):
                papers_to_download.append({"id": p.id, "doi": p.doi, "title": p.title})
            if len(papers_to_download) >= req.limit:
                break

        if not papers_to_download:
            await task_mgr.update_progress(task_id, 1.0, "No papers with DOIs found to download")
            return {"downloaded": 0, "failed": 0, "total": 0}

        await task_mgr.update_progress(task_id, 0.1, f"Launching browser for {len(papers_to_download)} papers...")

        def on_progress(paper_id: str, status: str, current: int, total: int):
            import asyncio
            frac = current / max(total, 1)
            msg = f"[{current}/{total}] {status}: {paper_id[:30]}"
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(task_mgr.update_progress(task_id, 0.1 + frac * 0.8, msg))
            except Exception:
                pass

        downloader = BrowserDownloader(download_dir=str(UPLOAD_DIR))
        try:
            result = await downloader.download_batch(papers_to_download, progress_callback=on_progress)
        finally:
            await downloader.close()

        # Index downloaded PDFs
        await task_mgr.update_progress(task_id, 0.92, "Indexing downloaded PDFs...")
        indexer = Indexer(vector_store=vs)
        indexed = 0
        for paper_id, pdf_path in result.get("paths", {}).items():
            try:
                db.update_paper_pdf(paper_id, pdf_path=pdf_path, status=PaperStatus.PDF_DOWNLOADED)
                indexer.index_paper(pdf_path, paper_id)
                db.update_paper_status(paper_id, PaperStatus.INDEXED)
                indexed += 1
            except Exception:
                pass

        await task_mgr.update_progress(task_id, 1.0, f"Done: {result['downloaded']} downloaded, {indexed} indexed")
        return {
            "downloaded": result["downloaded"],
            "indexed": indexed,
            "failed": result["failed"],
            "total": len(papers_to_download),
        }

    task_id = tm.create_task("browser_download", run_download)
    return {"task_id": task_id}
