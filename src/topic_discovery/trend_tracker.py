"""Research direction clustering and trend tracking.

Clusters annotated papers into coherent research directions,
supports delta-clustering for incremental updates.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.domain_config import get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.models import Annotation, Direction, Paper
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


async def cluster_into_directions(
    annotations: list[Annotation],
    papers: list[Paper],
    llm_router: LLMRouter,
    *,
    domain_id: str = "comparative_literature",
) -> list[Direction]:
    """Cluster annotations into research directions using LLM synthesis.

    Args:
        annotations: Paper annotations to cluster.
        papers: Corresponding papers.
        llm_router: LLM router.
        domain_id: Research domain identifier.

    Returns:
        List of research directions.
    """
    domain = get_domain_config(domain_id)
    prompt_template = domain.load_prompt("direction_synthesis.md")

    ann_summaries = []
    for ann in annotations[:50]:
        paper = next((p for p in papers if p.id == ann.paper_id), None)
        title = paper.title if paper else ann.paper_id
        ann_summaries.append(f"- [{ann.paper_id}] {title}: {json.dumps(ann.data)[:300]}")

    prompt = prompt_template.format(annotations="\n".join(ann_summaries))

    response = await llm_router.call(
        task="direction_synthesis",
        prompt=prompt,
        temperature=0.5,
    )
    directions_data = json.loads(response)
    if isinstance(directions_data, dict):
        directions_data = directions_data.get("directions", [])

    from src.knowledge_base.models import Direction

    directions = []
    for dd in directions_data:
        direction = Direction(
            title=dd.get("title", ""),
            description=dd.get("description", ""),
            dominant_tensions=dd.get("dominant_tensions", []),
            paper_ids=dd.get("paper_ids", []),
            growth_trajectory=dd.get("growth_trajectory", "unknown"),
        )
        directions.append(direction)

    logger.info("Clustered %d annotations into %d directions", len(annotations), len(directions))
    return directions


async def delta_cluster_directions(
    new_annotations: list[Annotation],
    existing_directions: list[Direction],
    papers: list[Paper],
    llm_router: LLMRouter,
    *,
    domain_id: str = "comparative_literature",
) -> tuple[list[Direction], set[str]]:
    """Incrementally assign new annotations to existing directions.

    Returns:
        Tuple of (updated directions, set of changed direction IDs).
    """
    changed_ids: set[str] = set()

    for ann in new_annotations:
        paper = next((p for p in papers if p.id == ann.paper_id), None)
        best_dir = None
        best_score = 0.0

        for direction in existing_directions:
            # Simple keyword overlap scoring
            ann_text = json.dumps(ann.data).lower()
            dir_text = (direction.title + " " + (direction.description or "")).lower()
            overlap = len(set(ann_text.split()) & set(dir_text.split()))
            if overlap > best_score:
                best_score = overlap
                best_dir = direction

        if best_dir and best_score > 3:
            best_dir.paper_ids.append(ann.paper_id)
            if best_dir.id:
                changed_ids.add(best_dir.id)
        else:
            changed_ids.add("__new__")

    return existing_directions, changed_ids


async def compress_directions(
    directions: list[Direction],
    llm_router: LLMRouter,
    *,
    max_directions: int = 10,
    domain_id: str = "comparative_literature",
) -> list[Direction]:
    """Merge similar directions if there are too many.

    Returns:
        Compressed list of directions.
    """
    if len(directions) <= max_directions:
        return directions

    # Sort by number of papers, keep top directions
    directions.sort(key=lambda d: len(d.paper_ids), reverse=True)
    return directions[:max_directions]


def compute_recency_scores(
    directions: list[Direction],
    papers: list[Paper],
    current_year: int,
) -> None:
    """Compute recency scores for directions based on paper publication years."""
    for direction in directions:
        dir_papers = [p for p in papers if p.id in direction.paper_ids]
        if not dir_papers:
            direction.recency_score = 0.0
            continue

        years = [getattr(p, "year", current_year) or current_year for p in dir_papers]
        avg_year = sum(years) / len(years)
        direction.recency_score = max(0.0, 1.0 - (current_year - avg_year) / 10.0)
