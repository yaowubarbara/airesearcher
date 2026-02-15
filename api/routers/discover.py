"""Topic discovery endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.deps import get_db, get_vs, get_router, get_task_manager

router = APIRouter(tags=["discover"])


class DiscoverRequest(BaseModel):
    journal: str
    limit: int = 5


@router.post("/discover")
async def start_discovery(req: DiscoverRequest, db=Depends(get_db), router=Depends(get_router), tm=Depends(get_task_manager)):
    from api.routers.journals import ACTIVE_JOURNALS
    if req.journal not in ACTIVE_JOURNALS:
        raise HTTPException(400, "Journal not active")

    async def run_discover(task_mgr, task_id):
        import sys
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.topic_discovery.gap_analyzer import analyze_gaps
        from src.topic_discovery.topic_scorer import score_topic
        from src.knowledge_base.models import TopicProposal

        await task_mgr.update_progress(task_id, 0.1, "Loading papers...")
        papers = db.search_papers(journal=req.journal, limit=200)
        if not papers:
            papers = db.search_papers(limit=200)

        await task_mgr.update_progress(task_id, 0.2, "Analyzing research gaps...")
        gaps = await analyze_gaps(papers, router)

        await task_mgr.update_progress(task_id, 0.5, f"Found {len(gaps)} gaps, scoring...")
        topics = []
        for i, gap in enumerate(gaps[:req.limit]):
            topic = TopicProposal(
                title=gap.get("title", ""),
                research_question=gap.get("potential_rq", gap.get("description", "")),
                gap_description=gap.get("description", ""),
                target_journals=[req.journal],
            )
            topic = score_topic(topic, papers, router)
            topic_id = db.insert_topic(topic)
            topic.id = topic_id
            topics.append(topic)
            await task_mgr.update_progress(task_id, 0.5 + 0.4 * (i + 1) / min(len(gaps), req.limit), f"Scored topic {i+1}")

        await task_mgr.update_progress(task_id, 1.0, "Discovery complete")
        return [t.model_dump() for t in topics]

    task_id = tm.create_task("discover", run_discover)
    return {"task_id": task_id}


@router.get("/topics")
async def list_topics(status: Optional[str] = None, limit: int = 20, db=Depends(get_db)):
    topics = db.get_topics(status=status, limit=limit)
    return {"topics": [t.model_dump() for t in topics]}
