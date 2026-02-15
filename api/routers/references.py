"""Reference acquisition and upload endpoints."""
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from api.deps import get_db, get_vs, get_task_manager

router = APIRouter(tags=["references"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "papers"


class SearchRequest(BaseModel):
    topic: str
    max_results: int = 50


@router.post("/references/search")
async def search_references(req: SearchRequest, db=Depends(get_db), vs=Depends(get_vs), tm=Depends(get_task_manager)):
    async def run_search(task_mgr, task_id):
        import sys
        from pathlib import Path as P
        PROJECT_ROOT = P(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.reference_acquisition.pipeline import ReferenceAcquisitionPipeline

        await task_mgr.update_progress(task_id, 0.1, "Starting reference search...")
        pipeline = ReferenceAcquisitionPipeline(db=db, vector_store=vs)
        report = await pipeline.acquire_references(topic=req.topic, max_results=req.max_results)
        await task_mgr.update_progress(task_id, 1.0, "Search complete")
        return {
            "query": report.query,
            "found": report.found,
            "downloaded": report.downloaded,
            "indexed": report.indexed,
            "oa_resolved": report.oa_resolved,
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


@router.get("/references/wishlist")
async def get_wishlist(db=Depends(get_db)):
    papers = db.get_papers_needing_pdf(limit=200)
    return {
        "count": len(papers),
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "doi": p.doi,
                "journal": p.journal,
            }
            for p in papers
        ],
    }
