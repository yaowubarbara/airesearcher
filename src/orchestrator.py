"""LangGraph orchestrator connecting all modules into a unified workflow.

Implements the full pipeline:
  Journal Monitor → Literature Indexer → Topic Discovery → Research Planner
  → Writing Agent → Reference Verifier → Self-Review → Human Review → Submission
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from langgraph.graph import END, StateGraph

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    Language,
    Manuscript,
    Paper,
    ReflexionEntry,
    ResearchPlan,
    TopicProposal,
)
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class WorkflowPhase(str, Enum):
    MONITOR = "monitor"
    INDEX = "index"
    DISCOVER = "discover"
    ACQUIRE_REFS = "acquire_refs"
    PLAN = "plan"
    WRITE = "write"
    VERIFY = "verify"
    VERIFY_CITATIONS = "verify_citations"
    REVIEW = "review"
    HUMAN_REVIEW = "human_review"
    SUBMIT = "submit"
    DONE = "done"


@dataclass
class WorkflowState:
    """State object passed through the LangGraph workflow."""

    phase: str = WorkflowPhase.MONITOR.value
    # Monitor results
    new_papers: list[dict] = field(default_factory=list)
    monitor_summary: str = ""
    # Topic discovery
    topics: list[dict] = field(default_factory=list)
    selected_topic: Optional[dict] = None
    # Planning
    plan: Optional[dict] = None
    plan_approved: bool = False
    # Writing
    manuscript: Optional[dict] = None
    # Verification
    verification_report: Optional[dict] = None
    citation_verification_report: Optional[dict] = None
    # Review
    review_result: Optional[dict] = None
    review_passed: bool = False
    revision_count: int = 0
    max_revisions: int = 3
    # Human review
    human_approved: bool = False
    human_feedback: str = ""
    # Submission
    submission_ready: bool = False
    formatted_manuscript: str = ""
    cover_letter: str = ""
    # Error tracking
    errors: list[str] = field(default_factory=list)
    # Configuration
    target_journal: str = ""
    target_language: str = "en"


def create_workflow(
    db: Database,
    vector_store: VectorStore,
    llm_router: LLMRouter,
) -> StateGraph:
    """Create the LangGraph workflow connecting all modules.

    Returns a compiled StateGraph that can be invoked with an initial state.
    """
    workflow = StateGraph(WorkflowState)

    # --- Node functions ---

    async def monitor_node(state: WorkflowState) -> dict:
        """Scan journals for new publications."""
        from src.journal_monitor.monitor import run_monitor

        try:
            summary = await run_monitor(db=db)
            new_papers = []
            for result in summary.journal_results:
                for paper in result.papers:
                    new_papers.append(paper.model_dump())
            return {
                "phase": WorkflowPhase.INDEX.value,
                "new_papers": new_papers,
                "monitor_summary": (
                    f"Scanned {summary.journals_scanned} journals, "
                    f"found {summary.total_new} new papers"
                ),
            }
        except Exception as e:
            logger.error("Monitor failed: %s", e)
            return {
                "phase": WorkflowPhase.INDEX.value,
                "errors": state.errors + [f"Monitor: {e}"],
            }

    async def index_node(state: WorkflowState) -> dict:
        """Index newly discovered papers."""
        from src.literature_indexer.indexer import Indexer

        try:
            indexer = Indexer(vector_store=vector_store)
            indexed_count = 0
            for paper_dict in state.new_papers:
                paper = Paper(**paper_dict)
                indexer.index_from_metadata(paper)
                indexed_count += 1
            logger.info("Indexed %d papers", indexed_count)
            return {"phase": WorkflowPhase.DISCOVER.value}
        except Exception as e:
            logger.error("Indexing failed: %s", e)
            return {
                "phase": WorkflowPhase.DISCOVER.value,
                "errors": state.errors + [f"Indexer: {e}"],
            }

    async def discover_node(state: WorkflowState) -> dict:
        """Run topic discovery and gap analysis."""
        from src.topic_discovery.gap_analyzer import analyze_gaps
        from src.topic_discovery.topic_scorer import score_topic

        try:
            papers = db.search_papers(limit=200)
            gaps = await analyze_gaps(papers, llm_router)

            topics = []
            for gap in gaps[:10]:  # Process top 10 gaps
                topic = TopicProposal(
                    title=gap.get("title", "Untitled"),
                    research_question=gap.get("potential_rq", gap.get("description", "")),
                    gap_description=gap.get("description", ""),
                    target_journals=[state.target_journal] if state.target_journal else [],
                )
                scored = score_topic(topic, papers, llm_router)
                topics.append(scored.model_dump())

            # Sort by overall score
            topics.sort(key=lambda t: t.get("overall_score", 0), reverse=True)

            return {
                "phase": WorkflowPhase.PLAN.value,
                "topics": topics,
                "selected_topic": topics[0] if topics else None,
            }
        except Exception as e:
            logger.error("Topic discovery failed: %s", e)
            return {
                "phase": WorkflowPhase.PLAN.value,
                "errors": state.errors + [f"Discovery: {e}"],
            }

    async def acquire_refs_node(state: WorkflowState) -> dict:
        """Acquire references for the selected topic via API search + PDF download."""
        from src.reference_acquisition.pipeline import ReferenceAcquisitionPipeline

        if not state.selected_topic:
            return {"phase": WorkflowPhase.PLAN.value}

        try:
            pipeline = ReferenceAcquisitionPipeline(db, vector_store)
            topic_text = (
                state.selected_topic.get("research_question")
                or state.selected_topic.get("title", "")
            )
            report = await pipeline.acquire_references(topic_text, max_results=50)
            logger.info(
                "Reference acquisition: found=%d, downloaded=%d, indexed=%d",
                report.found,
                report.downloaded,
                report.indexed,
            )
            return {"phase": WorkflowPhase.PLAN.value}
        except Exception as e:
            logger.error("Reference acquisition failed: %s", e)
            return {
                "phase": WorkflowPhase.PLAN.value,
                "errors": state.errors + [f"AcquireRefs: {e}"],
            }

    async def plan_node(state: WorkflowState) -> dict:
        """Create a research plan for the selected topic."""
        from src.research_planner.planner import ResearchPlanner

        if not state.selected_topic:
            return {
                "phase": WorkflowPhase.DONE.value,
                "errors": state.errors + ["No topic selected"],
            }

        try:
            planner = ResearchPlanner(db, vector_store, llm_router)
            topic = TopicProposal(**state.selected_topic)
            language = Language(state.target_language)

            plan = await planner.create_plan(
                topic=topic,
                target_journal=state.target_journal,
                language=language,
                skip_acquisition=True,  # already done in acquire_refs node
            )

            return {
                "phase": WorkflowPhase.WRITE.value,
                "plan": {
                    "id": plan.id,
                    "thesis_statement": plan.thesis_statement,
                    "target_journal": plan.target_journal,
                    "target_language": plan.target_language.value,
                    "outline": [s.model_dump() for s in plan.outline],
                    "reference_ids": plan.reference_ids,
                    "status": plan.status,
                },
                "plan_approved": True,  # Auto-approve for now; human gate comes later
            }
        except Exception as e:
            logger.error("Planning failed: %s", e)
            return {
                "phase": WorkflowPhase.DONE.value,
                "errors": state.errors + [f"Planner: {e}"],
            }

    async def write_node(state: WorkflowState) -> dict:
        """Generate manuscript draft using the writing agent."""
        from src.writing_agent.writer import WritingAgent

        if not state.plan:
            return {
                "phase": WorkflowPhase.DONE.value,
                "errors": state.errors + ["No plan available"],
            }

        try:
            writer = WritingAgent(db, vector_store, llm_router)
            from src.knowledge_base.models import OutlineSection

            plan = ResearchPlan(
                id=state.plan.get("id", ""),
                topic_id="",
                thesis_statement=state.plan["thesis_statement"],
                target_journal=state.plan["target_journal"],
                target_language=Language(state.plan["target_language"]),
                outline=[OutlineSection(**s) for s in state.plan.get("outline", [])],
                reference_ids=state.plan.get("reference_ids", []),
            )

            if state.revision_count > 0 and state.review_result and state.manuscript:
                current_ms = Manuscript(**state.manuscript)
                manuscript = await writer.revise_manuscript(
                    plan, current_ms, state.review_result
                )
            else:
                manuscript = await writer.write_full_manuscript(plan)

            return {
                "phase": WorkflowPhase.VERIFY.value,
                "manuscript": manuscript.model_dump(),
            }
        except Exception as e:
            logger.error("Writing failed: %s", e)
            return {
                "phase": WorkflowPhase.DONE.value,
                "errors": state.errors + [f"Writer: {e}"],
            }

    async def verify_node(state: WorkflowState) -> dict:
        """Verify all references in the manuscript."""
        from src.reference_verifier.verifier import ReferenceVerifier

        if not state.manuscript:
            return {"phase": WorkflowPhase.REVIEW.value}

        try:
            verifier = ReferenceVerifier(db)
            ms = Manuscript(**state.manuscript)
            report = await verifier.verify_manuscript_references(
                manuscript_text=ms.full_text or "",
                reference_ids=ms.reference_ids,
            )

            return {
                "phase": WorkflowPhase.REVIEW.value,
                "verification_report": {
                    "total": report.total_references,
                    "verified": len(report.verified),
                    "unverified": len(report.unverified),
                    "rate": report.verification_rate,
                    "summary": report.summary(),
                },
            }
        except Exception as e:
            logger.error("Verification failed: %s", e)
            return {
                "phase": WorkflowPhase.REVIEW.value,
                "errors": state.errors + [f"Verifier: {e}"],
            }

    async def verify_citations_node(state: WorkflowState) -> dict:
        """Verify inline citations against CrossRef/OpenAlex and annotate manuscript."""
        from src.citation_verifier.pipeline import verify_manuscript_citations

        if not state.manuscript:
            return {"phase": WorkflowPhase.REVIEW.value}

        try:
            ms = Manuscript(**state.manuscript)
            text = ms.full_text or ""

            if not text.strip():
                return {"phase": WorkflowPhase.REVIEW.value}

            annotated_text, report = await verify_manuscript_citations(text)

            # Update manuscript with annotated text
            updated_manuscript = dict(state.manuscript)
            updated_manuscript["full_text"] = annotated_text

            logger.info(
                "Citation verification: %d/%d verified, %d tags inserted",
                report.verified,
                report.total,
                report.work_not_found + report.page_out_of_range,
            )

            return {
                "phase": WorkflowPhase.REVIEW.value,
                "manuscript": updated_manuscript,
                "citation_verification_report": {
                    "total": report.total,
                    "verified": report.verified,
                    "work_not_found": report.work_not_found,
                    "page_unverifiable": report.page_unverifiable,
                    "page_out_of_range": report.page_out_of_range,
                    "summary": report.summary(),
                },
            }
        except Exception as e:
            logger.error("Citation verification failed: %s", e)
            return {
                "phase": WorkflowPhase.REVIEW.value,
                "errors": state.errors + [f"CitationVerifier: {e}"],
            }

    async def review_node(state: WorkflowState) -> dict:
        """Run self-review with multi-agent debate."""
        from src.self_review.reviewer import SelfReviewAgent

        if not state.manuscript:
            return {"phase": WorkflowPhase.HUMAN_REVIEW.value}

        try:
            reviewer = SelfReviewAgent()
            ms = Manuscript(**state.manuscript)

            # Load journal profile
            journal_profile = {}
            profile_path = Path(f"config/reviewer_profiles/{ms.target_journal.lower().replace(' ', '_')}.yaml")
            if profile_path.exists():
                with open(profile_path) as f:
                    journal_profile = yaml.safe_load(f)

            result = await reviewer.review_manuscript(ms, journal_profile, llm_router)

            passed = result.overall_recommendation in ("accept", "minor_revision")

            # Store reflexion memory
            for comment in result.comments:
                entry = ReflexionEntry(
                    category="self_review",
                    observation=comment,
                    source=f"self_review_v{state.revision_count + 1}",
                    manuscript_id=ms.id,
                )
                db.insert_reflexion(entry)

            return {
                "phase": WorkflowPhase.HUMAN_REVIEW.value if passed else WorkflowPhase.WRITE.value,
                "review_result": {
                    "scores": result.scores,
                    "recommendation": result.overall_recommendation,
                    "comments": result.comments,
                    "revision_instructions": result.revision_instructions,
                },
                "review_passed": passed,
                "revision_count": state.revision_count + (0 if passed else 1),
            }
        except Exception as e:
            logger.error("Review failed: %s", e)
            return {
                "phase": WorkflowPhase.HUMAN_REVIEW.value,
                "errors": state.errors + [f"Review: {e}"],
            }

    async def human_review_node(state: WorkflowState) -> dict:
        """Human review gate - waits for user approval.

        In the CLI flow, this is handled by user interaction.
        The node just marks the state as awaiting human input.
        """
        # This is a checkpoint - the workflow pauses here for human input
        return {
            "phase": WorkflowPhase.SUBMIT.value if state.human_approved else WorkflowPhase.HUMAN_REVIEW.value,
        }

    async def submit_node(state: WorkflowState) -> dict:
        """Prepare submission materials."""
        from src.submission_manager.cover_letter import CoverLetterGenerator
        from src.submission_manager.formatter import ManuscriptFormatter

        if not state.manuscript:
            return {"phase": WorkflowPhase.DONE.value}

        try:
            ms = Manuscript(**state.manuscript)
            formatter = ManuscriptFormatter(db)

            # Load journal style profile
            journal_profile = None
            safe_name = ms.target_journal.lower().replace(" ", "_")
            profile_path = Path(f"config/journal_profiles/{safe_name}.yaml")
            if profile_path.exists():
                with open(profile_path) as f:
                    journal_profile = yaml.safe_load(f)

            formatted = formatter.format_manuscript(ms, journal_profile)

            # Generate cover letter
            cover_gen = CoverLetterGenerator(llm_router)
            cover_letter = await cover_gen.generate(ms, journal_profile)

            return {
                "phase": WorkflowPhase.DONE.value,
                "submission_ready": True,
                "formatted_manuscript": formatted,
                "cover_letter": cover_letter,
            }
        except Exception as e:
            logger.error("Submission prep failed: %s", e)
            return {
                "phase": WorkflowPhase.DONE.value,
                "errors": state.errors + [f"Submission: {e}"],
            }

    # --- Build graph ---

    workflow.add_node("monitor", monitor_node)
    workflow.add_node("index", index_node)
    workflow.add_node("discover", discover_node)
    workflow.add_node("acquire_refs", acquire_refs_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("write", write_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("verify_citations", verify_citations_node)
    workflow.add_node("review", review_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("submit", submit_node)

    # --- Edges ---

    workflow.set_entry_point("monitor")

    workflow.add_edge("monitor", "index")
    workflow.add_edge("index", "discover")
    workflow.add_edge("discover", "acquire_refs")
    workflow.add_edge("acquire_refs", "plan")
    workflow.add_edge("plan", "write")
    workflow.add_edge("write", "verify")
    workflow.add_edge("verify", "verify_citations")
    workflow.add_edge("verify_citations", "review")

    # Review can loop back to write or proceed to human review
    def review_router(state: WorkflowState) -> str:
        if state.review_passed or state.revision_count >= state.max_revisions:
            return "human_review"
        return "write"

    workflow.add_conditional_edges("review", review_router, {
        "human_review": "human_review",
        "write": "write",
    })

    # Human review gate
    def human_review_router(state: WorkflowState) -> str:
        if state.human_approved:
            return "submit"
        return END  # Pause workflow, waiting for human input

    workflow.add_conditional_edges("human_review", human_review_router, {
        "submit": "submit",
        END: END,
    })

    workflow.add_edge("submit", END)

    return workflow.compile()
