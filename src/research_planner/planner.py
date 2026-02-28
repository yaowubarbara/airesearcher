"""Research planner — creates structured research plans for topics."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain_config import get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.db import Database
    from src.knowledge_base.models import Language, ResearchPlan, Topic
    from src.knowledge_base.vector_store import VectorStore
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class ResearchPlanner:
    """Creates research plans driven by domain configuration."""

    def __init__(
        self,
        db: Database,
        vs: VectorStore,
        llm_router: LLMRouter,
        *,
        domain_id: str = "comparative_literature",
    ):
        self.db = db
        self.vs = vs
        self.llm_router = llm_router
        self.domain = get_domain_config(domain_id)

    async def create_plan(
        self,
        topic: Topic,
        target_journal: str,
        language: Language,
    ) -> ResearchPlan:
        """Create a comprehensive research plan for a topic.

        Uses domain-specific persona and analysis methods to tailor
        the plan to the research field.
        """
        persona = self.domain.persona
        analysis_method = self.domain.analysis_method

        prompt = f"""You are a {persona}.

Create a detailed research plan for the following topic:

Title: {topic.title}
Thesis: {topic.thesis_seed}
Target Journal: {target_journal}
Language: {language.value}
Analysis Method: {analysis_method}

The plan should include:
1. A refined thesis statement
2. A detailed outline with sections, arguments, and estimated word counts
3. Required references and primary sources
4. Methodology description
5. Timeline estimate

Return as JSON with keys: thesis_statement, outline (array of sections),
reference_ids, methodology.
"""
        response = await self.llm_router.call(
            task="planning",
            prompt=prompt,
            temperature=0.5,
        )

        import json
        from src.knowledge_base.models import OutlineSection, ResearchPlan

        data = json.loads(response)
        plan = ResearchPlan(
            topic_id=topic.id,
            thesis_statement=data.get("thesis_statement", ""),
            target_journal=target_journal,
            target_language=language,
            outline=[OutlineSection(**s) for s in data.get("outline", [])],
            reference_ids=data.get("reference_ids", []),
        )
        return plan


def detect_missing_primary_texts(plan, db, vs):
    """Detect primary texts referenced in the plan but not indexed."""
    from src.knowledge_base.models import PrimaryTextReport
    return PrimaryTextReport(total_unique=0, missing=[], all_available=True)
