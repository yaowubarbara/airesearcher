"""Theory supplement — acquires and organizes theoretical references."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain_config import get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.db import Database
    from src.knowledge_base.models import ResearchPlan
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


async def supplement_theory_references(
    plan: ResearchPlan,
    db: Database,
    llm_router: LLMRouter,
    *,
    domain_id: str = "comparative_literature",
) -> list[dict]:
    """Identify and acquire additional theoretical references.

    Uses domain-specific reference blueprint to determine what
    types of references are needed (theoretical works, primary texts,
    datasets, clinical guidelines, etc.)
    """
    domain = get_domain_config(domain_id)

    try:
        blueprint_template = domain.load_prompt("reference_blueprint.md")
    except FileNotFoundError:
        blueprint_template = "List essential references for: {topic_title}\n{topic_description}"

    prompt = blueprint_template.format(
        topic_title=plan.thesis_statement,
        topic_description=f"Target: {plan.target_journal}, Domain: {domain.name}",
    )

    response = await llm_router.call(
        task="reference_supplement",
        prompt=prompt,
        temperature=0.3,
    )

    import json
    try:
        refs = json.loads(response)
        if isinstance(refs, dict):
            refs = refs.get("references", [])
        return refs
    except json.JSONDecodeError:
        logger.warning("Could not parse reference supplement response")
        return []
