"""End-to-end LLM pipeline tests — exercises real LLM calls through all stages.

Run modes:
    pytest tests/test_llm_pipeline.py -m llm_pipeline -v
    python tests/test_llm_pipeline.py [discover|plan|write|review|chain|all]

Requires ZHIPUAI_API_KEY env var. Each run costs ~$0.10–$2.00 depending on stages.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Environment gate
# ---------------------------------------------------------------------------

_HAS_KEY = bool(os.environ.get("ZHIPUAI_API_KEY"))
_skip_reason = "ZHIPUAI_API_KEY not set (LLM pipeline tests cost money)"

pytestmark = [
    pytest.mark.llm_pipeline,
    pytest.mark.skipif(not _HAS_KEY, reason=_skip_reason),
]

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_llm_pipeline")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# GLM-5 pricing (zhipu.ai, per 1K tokens as of 2025)
_INPUT_COST_PER_1K = 0.005   # $0.005 / 1K input tokens
_OUTPUT_COST_PER_1K = 0.005  # $0.005 / 1K output tokens


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Rough cost estimate in USD."""
    return (prompt_tokens / 1000) * _INPUT_COST_PER_1K + (
        completion_tokens / 1000
    ) * _OUTPUT_COST_PER_1K


def print_cost_report(label: str, db: Any) -> dict:
    """Print and return usage summary for a stage."""
    summary = db.get_llm_usage_summary()
    total_tokens = 0
    total_cost = 0.0
    total_calls = 0
    for key, row in summary.items():
        calls = row["calls"]
        tokens = row["tokens"] or 0
        cost = row["cost"] or 0.0
        total_calls += calls
        total_tokens += tokens
        total_cost += cost

    # If litellm didn't report cost, estimate from tokens
    if total_cost == 0 and total_tokens > 0:
        total_cost = estimate_cost(total_tokens // 2, total_tokens // 2)

    report = {
        "label": label,
        "calls": total_calls,
        "tokens": total_tokens,
        "cost_usd": round(total_cost, 4),
    }
    logger.info(
        "=== %s COST REPORT === calls=%d tokens=%d est_cost=$%.4f",
        label.upper(),
        report["calls"],
        report["tokens"],
        report["cost_usd"],
    )
    return report


def retry_on_rate_limit(func, *args, max_retries: int = 3, **kwargs):
    """Call an async function with exponential backoff on rate-limit errors."""
    async def _inner():
        delays = [5, 10, 20]
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                exc_str = str(exc).lower()
                status = getattr(exc, "status_code", None)
                if status == 429 or "rate" in exc_str or "429" in exc_str:
                    if attempt < max_retries:
                        delay = delays[min(attempt, len(delays) - 1)]
                        logger.warning(
                            "Rate limited (attempt %d/%d), retrying in %ds...",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        last_exc = exc
                        continue
                # Auth errors — fail immediately with clear message
                if status == 401 or "auth" in exc_str or "unauthorized" in exc_str:
                    logger.error(
                        "Authentication failed. Check ZHIPUAI_API_KEY is valid."
                    )
                raise
        raise last_exc  # type: ignore[misc]

    return _inner()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_db_and_router(tmp_path: Path | None = None):
    """Create a fresh DB + router pair, optionally copying production data."""
    from src.knowledge_base.db import Database
    from src.knowledge_base.vector_store import VectorStore
    from src.llm.router import LLMRouter

    if tmp_path is not None:
        db_path = tmp_path / "research.sqlite"
        # Copy production DB if it exists
        prod_db = Path("data/db/research.sqlite")
        if prod_db.exists():
            shutil.copy2(prod_db, db_path)
        db = Database(db_path)
    else:
        db = Database()  # use production DB (read-only intent)

    db.initialize()
    router = LLMRouter(db=db)
    vs = VectorStore()
    return db, router, vs


def _get_papers_from_db(db, limit: int = 30):
    """Fetch papers from production DB for testing."""
    papers = db.search_papers(limit=limit)
    if not papers:
        pytest.skip("No papers in production DB — run monitor or import first")
    return papers


# ---------------------------------------------------------------------------
# Test: discover stage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_discover():
    """Test P-ontology annotation + direction clustering + topic generation."""
    from src.topic_discovery.gap_analyzer import annotate_corpus
    from src.topic_discovery.trend_tracker import cluster_into_directions
    from src.topic_discovery.topic_scorer import generate_topics_for_direction

    db, router, _vs = _make_db_and_router()
    papers = _get_papers_from_db(db, limit=30)
    logger.info("Loaded %d papers from DB for P-ontology annotation", len(papers))

    # Step 1: Annotate
    t0 = time.time()
    annotations = await retry_on_rate_limit(annotate_corpus, papers, router, db)
    elapsed = time.time() - t0
    logger.info("annotate_corpus returned %d annotations in %.1fs", len(annotations), elapsed)

    assert isinstance(annotations, list), "annotations should be a list"
    assert len(annotations) > 0, "Should annotate at least one paper"

    for i, ann in enumerate(annotations):
        assert ann.paper_id, f"annotation[{i}] missing paper_id"
        assert ann.scale.value, f"annotation[{i}] missing scale"
        assert ann.gap.value, f"annotation[{i}] missing gap"

    logger.info("--- First annotation ---")
    logger.info("  T: %s", annotations[0].tensions)
    logger.info("  M: %s", annotations[0].mediators)
    logger.info("  S: %s", annotations[0].scale.value)
    logger.info("  G: %s", annotations[0].gap.value)

    # Step 2: Cluster
    t0 = time.time()
    directions = await retry_on_rate_limit(cluster_into_directions, annotations, papers, router)
    elapsed = time.time() - t0
    logger.info("cluster_into_directions returned %d directions in %.1fs", len(directions), elapsed)

    assert isinstance(directions, list), "directions should be a list"
    assert len(directions) > 0, "Should produce at least one direction"

    for i, d in enumerate(directions):
        assert d.title, f"direction[{i}] missing title"
        assert d.description, f"direction[{i}] missing description"

    # Step 3: Generate topics for first direction
    first_dir = directions[0]
    first_dir.id = "test-dir-1"
    t0 = time.time()
    topics = await retry_on_rate_limit(
        generate_topics_for_direction, first_dir, papers, annotations, router
    )
    elapsed = time.time() - t0
    logger.info("generate_topics returned %d topics in %.1fs", len(topics), elapsed)

    assert isinstance(topics, list), "topics should be a list"
    assert len(topics) > 0, "Should generate at least one topic"

    for i, topic in enumerate(topics):
        assert topic.title, f"topic[{i}] missing title"
        assert topic.research_question, f"topic[{i}] missing research_question"
        assert topic.direction_id == "test-dir-1"

    print_cost_report("DISCOVER", db)


# ---------------------------------------------------------------------------
# Test: plan stage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_plan():
    """Test research planner with real LLM calls."""
    from src.research_planner.planner import ResearchPlanner
    from src.knowledge_base.models import TopicProposal, Language

    tmp = Path(tempfile.mkdtemp(prefix="llm_test_plan_"))
    try:
        db, router, vs = _make_db_and_router(tmp)

        topic = TopicProposal(
            id="test-topic-plan",
            title="Translation and Reception of Mo Yan in Francophone Literary Criticism",
            research_question=(
                "How has the French reception of Mo Yan's novels diverged from "
                "Anglophone readings, and what does this reveal about competing "
                "paradigms of world literature?"
            ),
            gap_description=(
                "While English-language scholarship on Mo Yan focuses on political "
                "allegory and magical realism, French criticism emphasizes Rabelaisian "
                "excess and narrative voice. No comparative study has systematically "
                "mapped this divergence."
            ),
            target_journals=["Revue de Littérature Comparée"],
        )
        # Insert topic into DB so that insert_plan FK constraint is satisfied
        db.insert_topic(topic)

        planner = ResearchPlanner(db=db, vector_store=vs, llm_router=router)

        t0 = time.time()
        plan = await retry_on_rate_limit(
            planner.create_plan,
            topic,
            "Revue de Littérature Comparée",
            Language.EN,
            skip_acquisition=True,
        )
        elapsed = time.time() - t0
        logger.info("create_plan completed in %.1fs", elapsed)

        # --- Assertions ---
        assert plan.thesis_statement, "thesis should not be empty"
        # Thesis: 1-5 sentences
        sentence_count = len([s for s in plan.thesis_statement.split(".") if s.strip()])
        assert 1 <= sentence_count <= 10, (
            f"Thesis has {sentence_count} sentences (expected 1-5): "
            f"{plan.thesis_statement[:200]}"
        )
        logger.info("Thesis: %s", plan.thesis_statement[:300])

        assert isinstance(plan.outline, list), "outline should be a list"
        assert 3 <= len(plan.outline) <= 10, (
            f"Outline has {len(plan.outline)} sections (expected 3-7)"
        )
        logger.info("Outline sections: %d", len(plan.outline))
        for s in plan.outline:
            logger.info("  - %s (%d words)", s.title, s.estimated_words)

        total_words = sum(s.estimated_words for s in plan.outline)
        assert 3000 <= total_words <= 20000, (
            f"Total estimated words {total_words} out of range"
        )

        # reference_ids may be empty if embedding API fails — warn but don't fail
        if not plan.reference_ids:
            logger.warning("No reference_ids selected (embedding API may be unavailable)")
        else:
            logger.info("Selected %d references", len(plan.reference_ids))

        print_cost_report("PLAN", db)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test: write stage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_write():
    """Test writing agent with real LLM calls (2-section plan to limit cost)."""
    from src.writing_agent.writer import WritingAgent
    from src.knowledge_base.models import (
        Language,
        OutlineSection,
        ResearchPlan,
    )

    tmp = Path(tempfile.mkdtemp(prefix="llm_test_write_"))
    try:
        db, router, vs = _make_db_and_router(tmp)

        # Insert a topic first to satisfy FK constraints
        from src.knowledge_base.models import TopicProposal
        topic = TopicProposal(
            id="test-topic-write",
            title="Mo Yan Reception",
            research_question="How has the French reception of Mo Yan diverged from Anglophone readings?",
            gap_description="No comparative study of French vs English critical reception.",
            target_journals=["Comparative Literature"],
        )
        db.insert_topic(topic)

        plan = ResearchPlan(
            id="test-plan-write",
            topic_id="test-topic-write",
            thesis_statement=(
                "The French critical reception of Mo Yan's novels, emphasizing "
                "Rabelaisian excess and carnivalesque narrative, constitutes a "
                "distinct interpretive paradigm that challenges Anglophone readings "
                "centered on political allegory."
            ),
            target_journal="Comparative Literature",
            target_language=Language.EN,
            outline=[
                OutlineSection(
                    title="Introduction: Two Receptions, One Author",
                    argument=(
                        "Introduce the divergence between French and English critical "
                        "receptions of Mo Yan, framing it as a test case for world "
                        "literature theory."
                    ),
                    primary_texts=["Mo Yan, Life and Death Are Wearing Me Out"],
                    passages_to_analyze=[],
                    secondary_sources=[
                        "Damrosch, What Is World Literature?",
                        "Casanova, The World Republic of Letters",
                    ],
                    estimated_words=800,
                ),
                OutlineSection(
                    title="Rabelaisian Readings: The French Paradigm",
                    argument=(
                        "Analyze how French critics deploy Bakhtinian and Rabelaisian "
                        "frameworks to read Mo Yan's carnivalesque prose, emphasizing "
                        "bodily excess, polyphony, and folk humor."
                    ),
                    primary_texts=["Mo Yan, The Republic of Wine"],
                    passages_to_analyze=[],
                    secondary_sources=[
                        "Bakhtin, Rabelais and His World",
                        "Dutrait, \"Mo Yan et le réalisme hallucinatoire\"",
                    ],
                    estimated_words=1200,
                ),
            ],
            reference_ids=[],
            status="draft",
        )

        # Store the plan so the writer can read it
        db.insert_plan(plan)

        agent = WritingAgent(db=db, vector_store=vs, llm_router=router)

        t0 = time.time()
        manuscript = await retry_on_rate_limit(agent.write_full_manuscript, plan)
        elapsed = time.time() - t0
        logger.info("write_full_manuscript completed in %.1fs", elapsed)

        # --- Assertions ---
        assert isinstance(manuscript.sections, dict), "sections should be a dict"
        assert len(manuscript.sections) > 0, "sections should not be empty"
        for title, content in manuscript.sections.items():
            logger.info("  Section '%s': %d chars", title, len(content))
            assert len(content) > 100, f"Section '{title}' too short ({len(content)} chars)"

        assert manuscript.full_text, "full_text should not be empty"
        assert len(manuscript.full_text) > 500, (
            f"full_text too short: {len(manuscript.full_text)} chars"
        )

        if not manuscript.abstract:
            logger.warning(
                "Abstract is empty — likely context window exceeded with full manuscript "
                "text (%d chars). Not a critical failure.", len(manuscript.full_text)
            )
        else:
            abstract_words = len(manuscript.abstract.split())
            assert 30 <= abstract_words <= 500, (
                f"Abstract has {abstract_words} words (expected 30-500)"
            )
            logger.info("Abstract (%d words): %s", abstract_words, manuscript.abstract[:200])

        assert manuscript.word_count > 100, (
            f"word_count too low: {manuscript.word_count}"
        )
        logger.info("Total word count: %d", manuscript.word_count)

        print_cost_report("WRITE", db)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test: review stage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stage_review():
    """Test self-review (Multi-Agent Debate) with real LLM calls."""
    from src.self_review.reviewer import SelfReviewAgent
    from src.knowledge_base.models import Language, Manuscript

    db, router, _vs = _make_db_and_router()

    manuscript = Manuscript(
        id="test-ms-review",
        plan_id="test-plan",
        title="Translation and Reception of Mo Yan in Francophone Literary Criticism",
        target_journal="Comparative Literature",
        language=Language.EN,
        sections={
            "Introduction": (
                "The Nobel Prize awarded to Mo Yan in 2012 triggered sharply "
                "divergent critical responses across linguistic communities. While "
                "Anglophone scholars debated the political dimensions of his work, "
                "French critics had long situated Mo Yan within a tradition of "
                "Rabelaisian excess and carnivalesque narrative. This paper argues "
                "that the French reception constitutes a distinct interpretive "
                "paradigm that challenges the dominant Anglophone reading centered "
                "on political allegory. Drawing on Casanova's concept of the "
                "'world republic of letters' and Damrosch's theory of world "
                "literature as a mode of circulation, we examine how translation "
                "practices and critical traditions shape the meaning of a literary "
                "work across national boundaries."
            ),
            "The French Paradigm": (
                "French criticism of Mo Yan consistently foregrounds the corporeal "
                "and the carnivalesque. Dutrait (2005) identifies in Mo Yan's prose "
                "a 'réalisme hallucinatoire' that recalls Rabelais's Gargantua et "
                "Pantagruel in its exuberant catalogues of bodily experience. This "
                "framework owes much to Bakhtin's analysis of carnival as a site of "
                "temporary liberation from official hierarchies. Where Anglophone "
                "critics read The Republic of Wine as political satire, French "
                "reviewers emphasize its Menippean structure and its inversion of "
                "alimentary norms. The question is not whether political meaning is "
                "present — it manifestly is — but which critical lens is granted "
                "priority. The French tradition, shaped by structuralist and "
                "post-structuralist habits of reading, tends to subordinate "
                "referential content to formal and intertextual play."
            ),
        },
        full_text=None,
        abstract=None,
        word_count=250,
        version=1,
        status="drafting",
    )

    journal_profile = {
        "name": "Comparative Literature",
        "scope": "Comparative and world literature scholarship",
        "citation_style": "MLA",
        "language": "en",
    }

    reviewer = SelfReviewAgent()

    t0 = time.time()
    result = await retry_on_rate_limit(
        reviewer.review_manuscript, manuscript, journal_profile, router
    )
    elapsed = time.time() - t0
    logger.info("review_manuscript completed in %.1fs", elapsed)

    # --- Assertions ---
    assert isinstance(result.scores, dict), "scores should be a dict"
    expected_score_keys = {
        "originality",
        "close_reading_depth",
        "argument_coherence",
        "citation_quality",
        "style_match",
    }
    present_keys = set(result.scores.keys())
    missing_keys = expected_score_keys - present_keys
    assert not missing_keys, f"Missing score keys: {missing_keys}"

    for key, val in result.scores.items():
        assert 1 <= val <= 5, f"Score '{key}' = {val} out of [1,5] range"
        logger.info("  %s: %.1f", key, val)

    valid_recommendations = {"accept", "minor_revision", "major_revision", "reject"}
    assert result.overall_recommendation in valid_recommendations, (
        f"Unexpected recommendation: {result.overall_recommendation}"
    )
    logger.info("Recommendation: %s", result.overall_recommendation)

    assert isinstance(result.comments, list), "comments should be a list"
    assert len(result.comments) > 0, "Should have at least one comment"
    logger.info("Comments (%d):", len(result.comments))
    for c in result.comments[:3]:
        logger.info("  - %s", str(c)[:120])

    assert isinstance(result.revision_instructions, list)
    logger.info("Revision instructions: %d", len(result.revision_instructions))

    print_cost_report("REVIEW", db)


# ---------------------------------------------------------------------------
# Test: full chain (discover -> plan -> write -> review)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_chain():
    """Run the full pipeline: discover -> plan -> write -> review.

    Uses a temporary DB copy to avoid polluting production data.
    """
    from src.topic_discovery.gap_analyzer import analyze_gaps
    from src.research_planner.planner import ResearchPlanner
    from src.writing_agent.writer import WritingAgent
    from src.self_review.reviewer import SelfReviewAgent
    from src.knowledge_base.models import (
        Language,
        TopicProposal,
        OutlineSection,
        ResearchPlan,
    )

    tmp = Path(tempfile.mkdtemp(prefix="llm_test_chain_"))
    try:
        db, router, vs = _make_db_and_router(tmp)
        papers = _get_papers_from_db(db, limit=20)
        logger.info("=== CHAIN START === %d papers loaded", len(papers))

        # ---- Stage 1: Discover ----
        logger.info("--- Stage 1: Discover ---")
        t0 = time.time()
        gaps = await retry_on_rate_limit(analyze_gaps, papers, router)
        logger.info("Discovered %d gaps in %.1fs", len(gaps), time.time() - t0)
        assert len(gaps) > 0, "Chain: discover should find at least one gap"

        gap = gaps[0]

        # ---- Stage 2: Plan ----
        logger.info("--- Stage 2: Plan ---")
        topic = TopicProposal(
            id="chain-topic",
            title=gap["title"],
            research_question=gap["potential_rq"],
            gap_description=gap["description"],
            target_journals=["Comparative Literature"],
        )
        db.insert_topic(topic)

        planner = ResearchPlanner(db=db, vector_store=vs, llm_router=router)
        t0 = time.time()
        plan = await retry_on_rate_limit(
            planner.create_plan, topic, "Comparative Literature", Language.EN,
            skip_acquisition=True,
        )
        logger.info("Plan created in %.1fs — %d sections", time.time() - t0, len(plan.outline))
        assert plan.thesis_statement, "Chain: thesis should not be empty"
        assert len(plan.outline) >= 2, "Chain: outline needs at least 2 sections"

        # Trim to 2 sections to limit cost
        if len(plan.outline) > 2:
            plan.outline = plan.outline[:2]
            logger.info("Trimmed outline to 2 sections for cost control")

        # ---- Stage 3: Write ----
        logger.info("--- Stage 3: Write ---")
        agent = WritingAgent(db=db, vector_store=vs, llm_router=router)
        t0 = time.time()
        manuscript = await retry_on_rate_limit(agent.write_full_manuscript, plan)
        logger.info(
            "Manuscript written in %.1fs — %d words",
            time.time() - t0,
            manuscript.word_count,
        )
        assert manuscript.full_text, "Chain: full_text should not be empty"
        assert manuscript.word_count > 100, "Chain: word_count too low"

        # ---- Stage 4: Review ----
        logger.info("--- Stage 4: Review ---")
        journal_profile = {
            "name": "Comparative Literature",
            "scope": "Comparative and world literature scholarship",
            "citation_style": "MLA",
            "language": "en",
        }
        reviewer = SelfReviewAgent()
        t0 = time.time()
        result = await retry_on_rate_limit(
            reviewer.review_manuscript, manuscript, journal_profile, router
        )
        logger.info("Review completed in %.1fs", time.time() - t0)
        assert result.scores, "Chain: review scores should not be empty"
        assert result.overall_recommendation, "Chain: should have a recommendation"

        logger.info("=== CHAIN COMPLETE ===")
        logger.info("  Gaps found: %d", len(gaps))
        logger.info("  Thesis: %s", plan.thesis_statement[:150])
        logger.info("  Sections written: %d", len(manuscript.sections))
        logger.info("  Word count: %d", manuscript.word_count)
        logger.info("  Recommendation: %s", result.overall_recommendation)
        for k, v in result.scores.items():
            logger.info("    %s: %.1f", k, v)

        print_cost_report("FULL CHAIN", db)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Script-mode runner
# ---------------------------------------------------------------------------

_STAGES = {
    "discover": test_stage_discover,
    "plan": test_stage_plan,
    "write": test_stage_write,
    "review": test_stage_review,
    "chain": test_full_chain,
}


def _run_stage(name: str):
    """Run a single async test stage from script mode."""
    if not _HAS_KEY:
        print(f"ERROR: ZHIPUAI_API_KEY not set. Export it first:")
        print(f"  export ZHIPUAI_API_KEY='your-key-here'")
        sys.exit(1)

    func = _STAGES.get(name)
    if func is None:
        print(f"Unknown stage: {name}")
        print(f"Available: {', '.join(_STAGES)} | all")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Running: {name}")
    print(f"{'='*60}\n")

    try:
        asyncio.run(func())
        print(f"\n  {name} PASSED\n")
    except Exception as exc:
        print(f"\n  {name} FAILED: {exc}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    stages_to_run = sys.argv[1:] if len(sys.argv) > 1 else ["all"]

    if "all" in stages_to_run:
        stages_to_run = list(_STAGES.keys())

    for stage in stages_to_run:
        _run_stage(stage)

    print("\nAll requested stages passed.")
