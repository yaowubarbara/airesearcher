"""Self-review endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_db, get_vs, get_router, get_task_manager

router = APIRouter(tags=["review"])


@router.post("/review/{ms_id}")
async def start_review(ms_id: str, db=Depends(get_db), llm=Depends(get_router), tm=Depends(get_task_manager)):
    async def run_review(task_mgr, task_id):
        import sys, json
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.self_review.reviewer import SelfReviewAgent
        from src.knowledge_base.models import Manuscript, Language

        await task_mgr.update_progress(task_id, 0.1, "Loading manuscript...")
        cursor = db.conn.execute("SELECT * FROM manuscripts WHERE id = ?", (ms_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Manuscript {ms_id} not found")

        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        for field in ("sections", "keywords", "reference_ids", "review_scores"):
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except (json.JSONDecodeError, TypeError):
                    pass

        lang_str = data.get("language", "en")
        lang = Language(lang_str) if lang_str in ("en", "zh", "fr") else Language.EN
        ms = Manuscript(
            id=ms_id,
            plan_id=data.get("plan_id", ""),
            title=data.get("title", ""),
            target_journal=data.get("target_journal", ""),
            language=lang,
            sections=data.get("sections", {}),
            full_text=data.get("full_text"),
            abstract=data.get("abstract"),
            keywords=data.get("keywords", []),
            reference_ids=data.get("reference_ids", []),
            word_count=data.get("word_count", 0),
            version=data.get("version", 1),
            status=data.get("status", "drafting"),
        )

        await task_mgr.update_progress(task_id, 0.2, "Starting multi-agent review...")
        reviewer = SelfReviewAgent()
        journal_profile = {"name": ms.target_journal}
        result = await reviewer.review_manuscript(ms, journal_profile, llm)

        await task_mgr.update_progress(task_id, 1.0, "Review complete")
        return {
            "scores": result.scores,
            "comments": result.comments,
            "revision_instructions": result.revision_instructions,
            "overall_recommendation": result.overall_recommendation,
        }

    task_id = tm.create_task("review", run_review)
    return {"task_id": task_id}


@router.get("/reviews/{ms_id}")
async def get_review(ms_id: str, db=Depends(get_db)):
    import json
    cursor = db.conn.execute("SELECT review_scores FROM manuscripts WHERE id = ?", (ms_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Manuscript not found")
    scores = row[0]
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except (json.JSONDecodeError, TypeError):
            scores = {}
    return {"ms_id": ms_id, "scores": scores}
