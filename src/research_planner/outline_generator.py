"""Outline generator — creates detailed paper outlines."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain_config import get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.models import ResearchPlan
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


async def generate_outline(
    plan: ResearchPlan,
    llm_router: LLMRouter,
    *,
    domain_id: str = "comparative_literature",
) -> list[dict]:
    """Generate a detailed outline from a research plan.

    Uses domain persona for field-appropriate section structure.
    """
    domain = get_domain_config(domain_id)

    prompt = f"""You are a {domain.persona}.

Based on the following research plan, generate a detailed paper outline:

Thesis: {plan.thesis_statement}
Target Journal: {plan.target_journal}
Analysis Method: {domain.analysis_method}

For each section, provide:
- title: Section heading
- argument: Key argument or content
- estimated_words: Target word count
- key_references: References to include
- method_notes: Specific analytical methods to use

Return as a JSON array of section objects.
"""
    response = await llm_router.call(task="outline", prompt=prompt, temperature=0.5)
    import json
    return json.loads(response)
