"""Topic generation from research directions using domain-specific prompts."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.domain_config import get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.models import Annotation, Direction, Paper, Topic
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


async def generate_topics_for_direction(
    direction: Direction,
    papers: list[Paper],
    annotations: list[Annotation],
    llm_router: LLMRouter,
    *,
    domain_id: str = "comparative_literature",
) -> list[Topic]:
    """Generate publishable research topics for a direction.

    Args:
        direction: The research direction to generate topics for.
        papers: All papers in the corpus.
        annotations: All annotations.
        llm_router: LLM router.
        domain_id: Research domain identifier.

    Returns:
        List of generated topics.
    """
    domain = get_domain_config(domain_id)
    prompt_template = domain.load_prompt("topic_generation.md")

    # Build paper summaries for the direction
    dir_papers = [p for p in papers if p.id in direction.paper_ids]
    paper_summaries = "\n".join(
        f"- {p.title}: {(p.abstract or '')[:200]}" for p in dir_papers[:20]
    )

    prompt = prompt_template.format(
        direction_title=direction.title,
        direction_description=direction.description or "",
        tensions="; ".join(direction.dominant_tensions[:5]),
        paper_summaries=paper_summaries,
    )

    try:
        response = await llm_router.call(
            task="topic_generation",
            prompt=prompt,
            temperature=0.7,
        )
        topics_data = json.loads(response)
        if isinstance(topics_data, dict):
            topics_data = topics_data.get("topics", [])

        from src.knowledge_base.models import Topic

        topics = []
        for td in topics_data:
            topic = Topic(
                title=td.get("title", ""),
                thesis_seed=td.get("thesis_seed", ""),
                direction_id=direction.id,
                novelty=td.get("novelty", ""),
                feasibility=td.get("feasibility", ""),
            )
            topics.append(topic)

        logger.info(
            "Generated %d topics for direction: %s", len(topics), direction.title
        )
        return topics
    except Exception as e:
        logger.error("Topic generation failed for %s: %s", direction.title, e)
        return []
