"""Submission formatting endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_db, get_router, get_task_manager

router = APIRouter(tags=["submit"])


@router.post("/submit/{ms_id}")
async def format_submission(ms_id: str, db=Depends(get_db), llm=Depends(get_router), tm=Depends(get_task_manager)):
    async def run_submit(task_mgr, task_id):
        import sys, json
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.submission_manager.formatter import ManuscriptFormatter
        from src.submission_manager.cover_letter import CoverLetterGenerator
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

        await task_mgr.update_progress(task_id, 0.3, "Formatting manuscript...")
        formatter = ManuscriptFormatter(db=db)
        formatted = formatter.format_manuscript(ms)

        await task_mgr.update_progress(task_id, 0.6, "Generating cover letter...")
        cover_gen = CoverLetterGenerator(llm_router=llm)
        cover_letter = await cover_gen.generate(ms)

        await task_mgr.update_progress(task_id, 1.0, "Submission package ready")
        return {
            "formatted_manuscript": formatted,
            "cover_letter": cover_letter,
        }

    task_id = tm.create_task("submit", run_submit)
    return {"task_id": task_id}
