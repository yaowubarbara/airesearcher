"""Manuscript writing endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from api.deps import get_db, get_vs, get_router, get_task_manager

router = APIRouter(tags=["write"])


@router.post("/write/{plan_id}")
async def start_writing(plan_id: str, db=Depends(get_db), vs=Depends(get_vs), llm=Depends(get_router), tm=Depends(get_task_manager)):
    plan_data = db.get_plan(plan_id)
    if not plan_data:
        raise HTTPException(404, "Plan not found")

    async def run_write(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.writing_agent.writer import WritingAgent
        from src.knowledge_base.models import ResearchPlan, OutlineSection, Language

        await task_mgr.update_progress(task_id, 0.05, "Preparing plan...")
        # Reconstruct ResearchPlan from DB data
        outline_data = plan_data.get("outline", [])
        outline = []
        for s in outline_data:
            if isinstance(s, dict):
                outline.append(OutlineSection(**s))
            else:
                outline.append(s)

        lang_str = plan_data.get("target_language", "en")
        lang = Language(lang_str) if lang_str in ("en", "zh", "fr") else Language.EN

        plan = ResearchPlan(
            id=plan_id,
            topic_id=plan_data.get("topic_id", ""),
            thesis_statement=plan_data.get("thesis_statement", ""),
            target_journal=plan_data.get("target_journal", ""),
            target_language=lang,
            outline=outline,
            reference_ids=plan_data.get("reference_ids", []),
            status=plan_data.get("status", "draft"),
        )

        await task_mgr.update_progress(task_id, 0.1, "Starting manuscript generation...")
        agent = WritingAgent(db=db, vector_store=vs, llm_router=llm)

        # Write with progress updates
        total_sections = len(plan.outline)
        ms = await agent.write_full_manuscript(plan)

        await task_mgr.update_progress(task_id, 1.0, "Manuscript complete")
        return ms.model_dump()

    task_id = tm.create_task("write", run_write)
    return {"task_id": task_id}


@router.get("/manuscripts/{ms_id}")
async def get_manuscript(ms_id: str, db=Depends(get_db)):
    # Search for manuscript in DB
    import sys
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    cursor = db.conn.execute(
        "SELECT * FROM manuscripts WHERE id = ?", (ms_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Manuscript not found")

    import json
    columns = [desc[0] for desc in cursor.description]
    data = dict(zip(columns, row))
    # Parse JSON fields
    for field in ("sections", "keywords", "reference_ids", "review_scores"):
        if field in data and isinstance(data[field], str):
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return data
