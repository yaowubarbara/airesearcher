"""Research plan endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.deps import get_db, get_vs, get_router, get_task_manager

router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    topic_id: str
    journal: str
    language: str = "en"


@router.post("/plan")
async def create_plan(req: PlanRequest, db=Depends(get_db), vs=Depends(get_vs), llm=Depends(get_router), tm=Depends(get_task_manager)):
    from api.routers.journals import ACTIVE_JOURNALS
    if req.journal not in ACTIVE_JOURNALS:
        raise HTTPException(400, "Journal not active")

    async def run_plan(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.research_planner.planner import ResearchPlanner, detect_missing_primary_texts
        from src.knowledge_base.models import Language

        await task_mgr.update_progress(task_id, 0.1, "Loading topic...")
        topics = db.get_topics(limit=1000)
        topic = None
        for t in topics:
            if t.id == req.topic_id:
                topic = t
                break
        if not topic:
            raise ValueError(f"Topic {req.topic_id} not found")

        await task_mgr.update_progress(task_id, 0.2, "Creating research plan...")
        planner = ResearchPlanner(db=db, vector_store=vs, llm_router=llm)
        lang = Language(req.language) if req.language in ("en", "zh", "fr") else Language.EN
        plan = await planner.create_plan(
            topic=topic,
            target_journal=req.journal,
            language=lang,
            skip_acquisition=True,
        )

        await task_mgr.update_progress(task_id, 0.8, "Detecting missing primary texts...")
        primary_report = detect_missing_primary_texts(plan, db, vs)

        await task_mgr.update_progress(task_id, 1.0, "Plan complete")
        result = plan.model_dump()
        result["primary_text_report"] = primary_report.model_dump()
        return result

    task_id = tm.create_task("plan", run_plan)
    return {"task_id": task_id}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, db=Depends(get_db)):
    plan = db.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan
