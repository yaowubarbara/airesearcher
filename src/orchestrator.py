"""Workflow orchestrator — manages the full research pipeline.

Coordinates: monitor → discover → plan → write → review → submit
Each step receives and passes along the domain_id for domain-aware processing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.domain_config import DEFAULT_DOMAIN, get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.db import Database
    from src.knowledge_base.vector_store import VectorStore
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


@dataclass
class WorkflowState:
    """State object passed through the research pipeline."""

    target_journal: str = ""
    target_language: str = "en"
    domain_id: str = DEFAULT_DOMAIN

    # Pipeline results
    papers: list = field(default_factory=list)
    annotations: list = field(default_factory=list)
    directions: list = field(default_factory=list)
    topics: list = field(default_factory=list)
    selected_topic: Any = None
    plan: Any = None
    manuscript: Any = None
    review_result: Any = None
    submission_ready: bool = False
    errors: list[str] = field(default_factory=list)


def create_workflow(
    db: Database,
    vs: VectorStore,
    llm_router: LLMRouter,
):
    """Create a LangGraph-style workflow for the research pipeline.

    The workflow is domain-aware: each node reads domain_id from the state
    and uses the appropriate domain configuration.
    """

    async def discover_node(state: WorkflowState) -> WorkflowState:
        """Run topic discovery with domain-specific annotation."""
        from src.topic_discovery.gap_analyzer import annotate_corpus
        from src.topic_discovery.topic_scorer import generate_topics_for_direction
        from src.topic_discovery.trend_tracker import (
            cluster_into_directions,
            compress_directions,
            compute_recency_scores,
        )
        from datetime import datetime

        domain = get_domain_config(state.domain_id)
        logger.info("Running discovery for domain: %s", domain.name)

        papers = db.search_papers(journal=state.target_journal, limit=200)
        state.papers = papers

        annotations = await annotate_corpus(
            papers, llm_router, db, domain_id=state.domain_id
        )
        state.annotations = annotations

        directions = await cluster_into_directions(
            annotations, papers, llm_router, domain_id=state.domain_id
        )
        directions = await compress_directions(
            directions, llm_router, domain_id=state.domain_id
        )
        compute_recency_scores(directions, papers, datetime.utcnow().year)
        state.directions = directions

        all_topics = []
        for d in directions:
            topics = await generate_topics_for_direction(
                d, papers, annotations, llm_router, domain_id=state.domain_id
            )
            all_topics.extend(topics)
        state.topics = all_topics

        return state

    async def plan_node(state: WorkflowState) -> WorkflowState:
        """Create a research plan for the best topic."""
        from src.knowledge_base.models import Language
        from src.research_planner.planner import ResearchPlanner

        if not state.topics:
            state.errors.append("No topics discovered")
            return state

        state.selected_topic = state.topics[0]
        planner = ResearchPlanner(
            db, vs, llm_router, domain_id=state.domain_id
        )
        state.plan = await planner.create_plan(
            topic=state.selected_topic,
            target_journal=state.target_journal,
            language=Language(state.target_language),
        )
        return state

    class SimpleWorkflow:
        """Simple sequential workflow executor."""

        def __init__(self, nodes):
            self.nodes = nodes

        async def ainvoke(self, state: WorkflowState) -> WorkflowState:
            for node_fn in self.nodes:
                try:
                    state = await node_fn(state)
                except Exception as e:
                    state.errors.append(f"{node_fn.__name__}: {e}")
                    logger.error("Workflow error in %s: %s", node_fn.__name__, e)
            return state

    return SimpleWorkflow([discover_node, plan_node])
