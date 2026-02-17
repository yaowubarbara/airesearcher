"""Topic discovery endpoints — P-ontology annotation, direction clustering, topic generation."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.deps import get_db, get_vs, get_router, get_task_manager

router = APIRouter(tags=["discover"])


class DiscoverRequest(BaseModel):
    journal: str
    limit: int = 200


@router.post("/discover")
async def start_discovery(req: DiscoverRequest, db=Depends(get_db), llm_router=Depends(get_router), tm=Depends(get_task_manager)):
    from api.routers.journals import ACTIVE_JOURNALS
    if req.journal not in ACTIVE_JOURNALS:
        raise HTTPException(400, "Journal not active")

    async def run_discover(task_mgr, task_id):
        import sys
        from datetime import datetime
        from pathlib import Path
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from src.topic_discovery.gap_analyzer import annotate_corpus
        from src.topic_discovery.trend_tracker import (
            cluster_into_directions,
            compute_recency_scores,
            compress_directions,
            delta_cluster_directions,
        )
        from src.topic_discovery.topic_scorer import generate_topics_for_direction

        await task_mgr.update_progress(task_id, 0.1, "Loading papers...")
        papers = db.search_papers(journal=req.journal, limit=req.limit)
        if len(papers) < 50:
            papers = db.search_papers(limit=req.limit)

        # Step 1: Annotate
        await task_mgr.update_progress(task_id, 0.2, "Annotating papers with P-ontology...")
        annotations = await annotate_corpus(papers, llm_router, db)
        total_ann = len(annotations)
        await task_mgr.update_progress(task_id, 0.6, f"Annotated {total_ann} papers")

        # Step 2: Cluster (full or delta)
        existing_directions = db.get_directions(limit=100)
        import asyncio
        all_topics = []
        current_year = datetime.utcnow().year

        if not existing_directions:
            # Full clustering from scratch
            await task_mgr.update_progress(task_id, 0.7, "Clustering into directions...")
            db.delete_all_directions_and_topics()
            directions = await cluster_into_directions(annotations, papers, llm_router)
            directions = await compress_directions(directions, llm_router, max_directions=10)
            compute_recency_scores(directions, papers, current_year)

            # Insert directions
            for direction in directions:
                dir_id = db.insert_direction(direction)
                direction.id = dir_id

            # Generate topics for ALL directions
            changed_dir_ids = {d.id for d in directions if d.id}
        else:
            # Delta clustering: find unassigned annotations
            await task_mgr.update_progress(task_id, 0.7, "Delta-clustering new annotations...")
            assigned_paper_ids = set()
            for d in existing_directions:
                assigned_paper_ids.update(d.paper_ids)
            new_annotations = [a for a in annotations if a.paper_id not in assigned_paper_ids]

            if new_annotations:
                directions, changed_ids = await delta_cluster_directions(
                    new_annotations, existing_directions, papers, llm_router,
                )
            else:
                directions = existing_directions
                changed_ids = set()

            directions = await compress_directions(directions, llm_router, max_directions=10)
            compute_recency_scores(directions, papers, current_year)

            # Persist all directions (update existing, insert new)
            for direction in directions:
                dir_id = db.insert_direction(direction)
                direction.id = dir_id

            # Determine which directions need topic regeneration
            changed_dir_ids = set()
            for d in directions:
                if d.id and (d.id in changed_ids or not d.topic_ids):
                    changed_dir_ids.add(d.id)
            # New directions (those that had "__new__" marker)
            if "__new__" in changed_ids:
                for d in directions:
                    if d.id and not d.topic_ids:
                        changed_dir_ids.add(d.id)

        # Step 3: Generate topics for changed directions only
        dirs_needing_topics = [d for d in directions if d.id in changed_dir_ids]
        if dirs_needing_topics:
            await task_mgr.update_progress(
                task_id, 0.8,
                f"Generating topics for {len(dirs_needing_topics)} directions..."
            )

            # Delete old topics for changed directions
            for d in dirs_needing_topics:
                if d.id:
                    db.delete_topics_for_direction(d.id)

            async def _gen_topics(direction):
                return direction, await generate_topics_for_direction(
                    direction, papers, annotations, llm_router
                )

            results = await asyncio.gather(
                *[_gen_topics(d) for d in dirs_needing_topics],
                return_exceptions=True,
            )

            for r in results:
                if isinstance(r, Exception):
                    continue
                direction, topics = r
                topic_ids = []
                for topic in topics:
                    topic.direction_id = direction.id
                    topic.target_journals = [req.journal]
                    tid = db.insert_topic(topic)
                    topic.id = tid
                    topic_ids.append(tid)
                    all_topics.append(topic.model_dump())

                direction.topic_ids = topic_ids
                db.insert_direction(direction)

        await task_mgr.update_progress(task_id, 1.0, "Discovery complete")
        return {
            "directions": [d.model_dump() for d in directions],
            "topics": all_topics,
        }

    task_id = tm.create_task("discover", run_discover)
    return {"task_id": task_id}


@router.get("/discover/status")
async def annotation_status(db=Depends(get_db)):
    """Return annotation/direction/topic counts."""
    total_papers = db.count_papers()
    papers_with_abstract = db.conn.execute(
        "SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != ''"
    ).fetchone()[0]
    annotated = db.count_annotations()
    unannotated = papers_with_abstract - annotated
    directions = len(db.get_directions(limit=100))
    topics = len(db.get_topics(limit=500))
    return {
        "total_papers": total_papers,
        "papers_with_abstract": papers_with_abstract,
        "annotated": annotated,
        "unannotated": max(0, unannotated),
        "directions": directions,
        "topics": topics,
    }


@router.get("/directions")
async def list_directions(limit: int = 20, db=Depends(get_db)):
    directions = db.get_directions(limit=limit)
    return {"directions": [d.model_dump() for d in directions]}


@router.get("/directions/{direction_id}")
async def get_direction_with_topics(direction_id: str, db=Depends(get_db)):
    direction = db.get_direction(direction_id)
    if not direction:
        raise HTTPException(404, "Direction not found")
    topics = db.get_topics_by_direction(direction_id, limit=20)
    return {
        "direction": direction.model_dump(),
        "topics": [t.model_dump() for t in topics],
    }


@router.get("/corpus-studied")
async def get_corpus_studied():
    """Return authors and works already studied in the corpus papers."""
    from api.corpus_data import CORPUS_STUDIED
    return {"items": CORPUS_STUDIED}


@router.get("/topics")
async def list_topics(status: Optional[str] = None, direction_id: Optional[str] = None, limit: int = 20, db=Depends(get_db)):
    if direction_id:
        topics = db.get_topics_by_direction(direction_id, limit=limit)
    else:
        topics = db.get_topics(status=status, limit=limit)
    return {"topics": [t.model_dump() for t in topics]}
