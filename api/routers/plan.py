"""Research plan endpoints."""
import asyncio
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
    edited_title: Optional[str] = None
    edited_research_question: Optional[str] = None
    edited_gap_description: Optional[str] = None


class PlanFromSessionRequest(BaseModel):
    session_id: str
    journal: str
    language: str = "en"
    reference_ids: Optional[list[str]] = None
    edited_title: Optional[str] = None
    edited_research_question: Optional[str] = None
    edited_gap_description: Optional[str] = None


class RefineRequest(BaseModel):
    feedback: str
    conversation_history: list[dict] = []


class PlanFromUploadsRequest(BaseModel):
    journal: str
    language: str = "en"
    paper_ids: list[str]
    edited_title: Optional[str] = None
    edited_research_question: Optional[str] = None
    edited_gap_description: Optional[str] = None


class PlanFromCustomRequest(BaseModel):
    title: str
    research_question: str
    gap_description: str = ""
    journal: str
    language: str = "en"
    session_id: Optional[str] = None
    reference_ids: Optional[list[str]] = None


class SynthesizeTopicRequest(BaseModel):
    session_id: Optional[str] = None
    paper_ids: Optional[list[str]] = None
    hint: Optional[str] = None


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

        # Apply user edits to the topic before plan generation
        if req.edited_title is not None:
            topic.title = req.edited_title
        if req.edited_research_question is not None:
            topic.research_question = req.edited_research_question
        if req.edited_gap_description is not None:
            topic.gap_description = req.edited_gap_description

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
        from src.research_planner.planner import ResearchPlanner, detect_missing_primary_texts, synthesize_topic_from_papers
        from src.knowledge_base.models import Language

        await task_mgr.update_progress(task_id, 0.1, "Preparing topic...")

        source_ids = req.reference_ids or session["paper_ids"]

        # If user provided edited fields, construct topic directly (skip re-synthesis)
        if req.edited_title is not None:
            from src.knowledge_base.models import TopicProposal
            topic = TopicProposal(
                id=str(uuid.uuid4()),
                title=req.edited_title,
                research_question=req.edited_research_question or "",
                gap_description=req.edited_gap_description or "",
                evidence_paper_ids=source_ids[:20],
                overall_score=0.5,
                status="approved",
            )
        else:
            # Use LLM to synthesize a real TopicProposal from session papers
            topic = await asyncio.to_thread(
                synthesize_topic_from_papers,
                source_ids,
                db,
                llm,
                hint=session["query"],
            )
        topic.target_journals = [req.journal]
        db.insert_topic(topic)

        await task_mgr.update_progress(task_id, 0.2, "Creating research plan...")
        planner = ResearchPlanner(db=db, vector_store=vs, llm_router=llm)
        lang = Language(req.language) if req.language in ("en", "zh", "fr") else Language.EN
        plan = await planner.create_plan(
            topic=topic,
            target_journal=req.journal,
            language=lang,
            skip_acquisition=True,
            selected_paper_ids=req.reference_ids,
        )

        await task_mgr.update_progress(task_id, 0.8, "Detecting missing primary texts...")
        primary_report = detect_missing_primary_texts(plan, db, vs)

        await task_mgr.update_progress(task_id, 1.0, "Plan complete")
        result = plan.model_dump()
        result["primary_text_report"] = primary_report.model_dump()
        return result

    task_id = tm.create_task("plan_from_session", run_plan)
    return {"task_id": task_id}


@router.post("/plan/from-uploads")
async def create_plan_from_uploads(req: PlanFromUploadsRequest, db=Depends(get_db), vs=Depends(get_vs), llm=Depends(get_router), tm=Depends(get_task_manager)):
    from api.routers.journals import ACTIVE_JOURNALS
    if req.journal not in ACTIVE_JOURNALS:
        raise HTTPException(400, "Journal not active")
    if not req.paper_ids:
        raise HTTPException(400, "At least one paper_id is required")

    async def run_plan(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.research_planner.planner import ResearchPlanner, detect_missing_primary_texts, synthesize_topic_from_papers
        from src.knowledge_base.models import Language

        await task_mgr.update_progress(task_id, 0.1, "Preparing topic...")

        # If user provided edited fields, construct topic directly (skip re-synthesis)
        if req.edited_title is not None:
            from src.knowledge_base.models import TopicProposal
            topic = TopicProposal(
                id=str(uuid.uuid4()),
                title=req.edited_title,
                research_question=req.edited_research_question or "",
                gap_description=req.edited_gap_description or "",
                evidence_paper_ids=req.paper_ids[:20],
                overall_score=0.5,
                status="approved",
            )
        else:
            # LLM-powered topic synthesis from the uploaded corpus
            topic = await asyncio.to_thread(
                synthesize_topic_from_papers,
                req.paper_ids,
                db,
                llm,
            )
        topic.target_journals = [req.journal]
        db.insert_topic(topic)

        # Create a tracking session for these uploads
        session_id = str(uuid.uuid4())
        db.insert_search_session(
            session_id=session_id,
            query=f"[corpus] {topic.title}",
            paper_ids=req.paper_ids,
            found=len(req.paper_ids),
            indexed=len(req.paper_ids),
        )

        await task_mgr.update_progress(task_id, 0.3, "Creating research plan...")
        planner = ResearchPlanner(db=db, vector_store=vs, llm_router=llm)
        lang = Language(req.language) if req.language in ("en", "zh", "fr") else Language.EN
        plan = await planner.create_plan(
            topic=topic,
            target_journal=req.journal,
            language=lang,
            skip_acquisition=True,
            selected_paper_ids=req.paper_ids,
        )

        await task_mgr.update_progress(task_id, 0.8, "Detecting missing primary texts...")
        primary_report = detect_missing_primary_texts(plan, db, vs)

        await task_mgr.update_progress(task_id, 1.0, "Plan complete")
        result = plan.model_dump()
        result["primary_text_report"] = primary_report.model_dump()
        result["synthesized_topic"] = {
            "title": topic.title,
            "research_question": topic.research_question,
            "gap_description": topic.gap_description,
        }
        return result

    task_id = tm.create_task("plan_from_uploads", run_plan)
    return {"task_id": task_id}


@router.post("/plan/from-custom")
async def create_plan_from_custom(req: PlanFromCustomRequest, db=Depends(get_db), vs=Depends(get_vs), llm=Depends(get_router), tm=Depends(get_task_manager)):
    """Create a plan from a user-defined topic, optionally linked to a search session's references."""
    from api.routers.journals import ACTIVE_JOURNALS
    if req.journal not in ACTIVE_JOURNALS:
        raise HTTPException(400, "Journal not active")
    if not req.title.strip():
        raise HTTPException(400, "Title is required")

    # If session_id provided, resolve paper_ids from it
    selected_paper_ids = req.reference_ids
    if req.session_id and not selected_paper_ids:
        sessions = db.get_search_sessions()
        for s in sessions:
            if s["id"] == req.session_id:
                selected_paper_ids = s["paper_ids"]
                break

    async def run_plan(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.research_planner.planner import ResearchPlanner, detect_missing_primary_texts
        from src.knowledge_base.models import Language, TopicProposal

        await task_mgr.update_progress(task_id, 0.1, "Creating topic...")
        topic = TopicProposal(
            id=str(uuid.uuid4()),
            title=req.title.strip(),
            research_question=req.research_question.strip(),
            gap_description=req.gap_description.strip(),
            evidence_paper_ids=(selected_paper_ids or [])[:20],
            overall_score=0.5,
            status="approved",
        )
        topic.target_journals = [req.journal]
        db.insert_topic(topic)

        await task_mgr.update_progress(task_id, 0.2, "Creating research plan...")
        planner = ResearchPlanner(db=db, vector_store=vs, llm_router=llm)
        lang = Language(req.language) if req.language in ("en", "zh", "fr") else Language.EN
        plan = await planner.create_plan(
            topic=topic,
            target_journal=req.journal,
            language=lang,
            skip_acquisition=True,
            selected_paper_ids=selected_paper_ids,
        )

        await task_mgr.update_progress(task_id, 0.8, "Detecting missing primary texts...")
        primary_report = detect_missing_primary_texts(plan, db, vs)

        await task_mgr.update_progress(task_id, 1.0, "Plan complete")
        result = plan.model_dump()
        result["primary_text_report"] = primary_report.model_dump()
        return result

    task_id = tm.create_task("plan_from_custom", run_plan)
    return {"task_id": task_id}


@router.post("/plan/synthesize-topic")
async def synthesize_topic(req: SynthesizeTopicRequest, db=Depends(get_db), llm=Depends(get_router), tm=Depends(get_task_manager)):
    """Synthesize a topic from papers without creating a plan. Returns title/research_question/gap_description."""
    if not req.session_id and not req.paper_ids:
        raise HTTPException(400, "Either session_id or paper_ids is required")

    # Resolve paper_ids from session if needed
    hint = req.hint or ""
    if req.session_id:
        sessions = db.get_search_sessions()
        session = None
        for s in sessions:
            if s["id"] == req.session_id:
                session = s
                break
        if not session:
            raise HTTPException(404, "Search session not found")
        paper_ids = req.paper_ids or session["paper_ids"]
        hint = hint or session["query"]
    else:
        paper_ids = req.paper_ids

    async def run_synthesize(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.research_planner.planner import synthesize_topic_from_papers

        await task_mgr.update_progress(task_id, 0.2, "Synthesizing topic...")
        topic = await asyncio.to_thread(
            synthesize_topic_from_papers,
            paper_ids,
            db,
            llm,
            hint=hint,
        )
        await task_mgr.update_progress(task_id, 1.0, "Topic synthesized")
        return {
            "title": topic.title,
            "research_question": topic.research_question,
            "gap_description": topic.gap_description,
            "source_paper_ids": topic.evidence_paper_ids or paper_ids[:20],
        }

    task_id = tm.create_task("synthesize_topic", run_synthesize)
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
