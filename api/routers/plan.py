"""Research plan endpoints."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.deps import get_db, get_vs, get_router, get_task_manager

router = APIRouter(tags=["plan"])


class PlanRequest(BaseModel):
    topic_id: str
    journal: str
    language: str = "en"


class PlanFromSessionRequest(BaseModel):
    session_id: str
    journal: str
    language: str = "en"


class RefineRequest(BaseModel):
    feedback: str
    conversation_history: list[dict] = []


class ReadinessCheckRequest(BaseModel):
    session_id: Optional[str] = None
    topic_id: Optional[str] = None
    query: Optional[str] = None


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


@router.post("/plan/from-session")
async def create_plan_from_session(req: PlanFromSessionRequest, db=Depends(get_db), vs=Depends(get_vs), llm=Depends(get_router), tm=Depends(get_task_manager)):
    from api.routers.journals import ACTIVE_JOURNALS
    if req.journal not in ACTIVE_JOURNALS:
        raise HTTPException(400, "Journal not active")

    # Verify session exists
    sessions = db.get_search_sessions()
    session = None
    for s in sessions:
        if s["id"] == req.session_id:
            session = s
            break
    if not session:
        raise HTTPException(404, "Search session not found")

    async def run_plan(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.research_planner.planner import ResearchPlanner, detect_missing_primary_texts
        from src.knowledge_base.models import Language, TopicProposal

        await task_mgr.update_progress(task_id, 0.1, "Creating topic from search session...")

        # Synthesize a TopicProposal from the session query
        topic = TopicProposal(
            id=str(uuid.uuid4()),
            title=session["query"],
            research_question=f"Research based on: {session['query']}",
            gap_description=f"Search session with {len(session['paper_ids'])} papers found",
            evidence_paper_ids=session["paper_ids"][:20],
            target_journals=[req.journal],
            overall_score=0.5,
            status="approved",
        )
        db.insert_topic(topic)

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

    task_id = tm.create_task("plan_from_session", run_plan)
    return {"task_id": task_id}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, db=Depends(get_db)):
    plan = db.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


@router.post("/plans/{plan_id}/refine")
async def refine_plan(
    plan_id: str,
    req: RefineRequest,
    db=Depends(get_db),
    vs=Depends(get_vs),
    llm=Depends(get_router),
    tm=Depends(get_task_manager),
):
    """Refine a plan based on conversational feedback. Uses TaskManager."""
    plan = db.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    async def run_refine(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.research_planner.planner import ResearchPlanner

        await task_mgr.update_progress(task_id, 0.1, "Refining plan...")
        planner = ResearchPlanner(db=db, vector_store=vs, llm_router=llm)

        updated_plan, message = await planner.refine_plan(
            plan_id=plan_id,
            feedback=req.feedback,
            conversation_history=req.conversation_history,
        )

        await task_mgr.update_progress(task_id, 1.0, "Refinement complete")
        return {"plan": updated_plan, "message": message}

    task_id = tm.create_task("refine_plan", run_refine)
    return {"task_id": task_id}


@router.post("/plan/readiness-check")
async def readiness_check(
    req: ReadinessCheckRequest,
    db=Depends(get_db),
    vs=Depends(get_vs),
    llm=Depends(get_router),
):
    """Pre-plan readiness check. Direct response (no TaskManager)."""
    import sys
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.research_planner.readiness_checker import check_readiness

    # Determine query and session paper IDs
    query = req.query
    session_paper_ids = None

    if req.session_id:
        sessions = db.get_search_sessions()
        session = None
        for s in sessions:
            if s["id"] == req.session_id:
                session = s
                break
        if not session:
            raise HTTPException(404, "Search session not found")
        query = query or session["query"]
        session_paper_ids = session.get("paper_ids", [])

    if req.topic_id and not query:
        topics = db.get_topics(limit=1000)
        for t in topics:
            if t.id == req.topic_id:
                query = t.research_question or t.title
                break

    if not query:
        raise HTTPException(400, "No query, session_id, or topic_id provided")

    report = await check_readiness(
        query=query,
        db=db,
        vector_store=vs,
        llm_router=llm,
        session_paper_ids=session_paper_ids,
    )

    return {
        "query": report.query,
        "status": report.status,
        "items": [
            {
                "author": item.author,
                "title": item.title,
                "category": item.category,
                "reason": item.reason,
                "available": item.available,
            }
            for item in report.items
        ],
        "summary": report.summary(),
    }


@router.post("/plans/{plan_id}/theory-supplement")
async def theory_supplement(
    plan_id: str,
    db=Depends(get_db),
    vs=Depends(get_vs),
    llm=Depends(get_router),
    tm=Depends(get_task_manager),
):
    """Supplement a plan with canonical theory works. Uses TaskManager."""
    plan = db.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    async def run_supplement(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.reference_acquisition.theory_supplement import TheorySupplement

        async def progress_cb(progress, message):
            await task_mgr.update_progress(task_id, progress, message)

        supplement = TheorySupplement(db=db, vector_store=vs, llm_router=llm)
        report = await supplement.supplement_plan(
            plan_id=plan_id,
            thesis=plan.get("thesis_statement", ""),
            outline_sections=plan.get("outline", []),
            existing_reference_ids=plan.get("reference_ids", []),
            progress_callback=progress_cb,
        )

        return {
            "plan_id": report.plan_id,
            "total_recommended": report.total_recommended,
            "verified": report.verified,
            "inserted": report.inserted,
            "already_present": report.already_present,
            "items": [
                {
                    "author": v.candidate.author,
                    "title": v.candidate.title,
                    "relevance": v.candidate.relevance,
                    "year": v.candidate.year_hint,
                    "source": v.source,
                    "verified": v.verified,
                    "already_in_db": v.already_in_db,
                    "has_full_text": v.has_full_text,
                }
                for v in report.items
            ],
            "summary": report.summary(),
        }

    task_id = tm.create_task("theory_supplement", run_supplement)
    return {"task_id": task_id}
