"""Usage statistics endpoint."""
from fastapi import APIRouter, Depends
from api.deps import get_db

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(db=Depends(get_db)):
    usage = db.get_llm_usage_summary()
    paper_count = db.count_papers()
    topics = db.get_topics(limit=1000)
    return {
        "papers_indexed": paper_count,
        "topics_discovered": len(topics),
        "llm_usage": usage,
    }
