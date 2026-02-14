"""Score and rank topic proposals on novelty, feasibility, journal fit, and timeliness."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime

from src.knowledge_base.models import Paper, TopicProposal
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

# Weights for the overall score (must sum to 1.0).
SCORE_WEIGHTS = {
    "novelty": 0.35,
    "feasibility": 0.25,
    "journal_fit": 0.15,
    "timeliness": 0.25,
}

_RECENCY_WINDOW_YEARS = 5

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_NOVELTY_FEASIBILITY_PROMPT = """\
You are a senior comparative-literature scholar evaluating a proposed research \
topic against an existing corpus of papers.

--- PROPOSED TOPIC ---
Title: {title}
Research question: {research_question}
Gap description: {gap_description}
Target journals: {target_journals}
--- END TOPIC ---

--- RELEVANT CORPUS (up to {corpus_count} papers) ---
{corpus_summary}
--- END CORPUS ---

Evaluate the topic on two dimensions and return a JSON object with exactly \
these keys:

1. "novelty" (float 0-1): How original is this topic relative to the corpus? \
   1.0 = completely unexplored, 0.0 = already thoroughly covered.
2. "novelty_rationale" (string): 1-2 sentence justification.
3. "feasibility" (float 0-1): How feasible is it to execute this research with \
   the available corpus and standard academic resources? Consider availability \
   of primary texts, secondary sources, and methodological clarity. \
   1.0 = highly feasible, 0.0 = practically impossible.
4. "feasibility_rationale" (string): 1-2 sentence justification.

Output ONLY the JSON object, no other text.
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _current_year() -> int:
    return datetime.utcnow().year


def _build_corpus_summary(papers: list[Paper], max_papers: int = 60) -> str:
    lines: list[str] = []
    for p in papers[:max_papers]:
        kw = ", ".join(p.keywords) if p.keywords else "none"
        lines.append(
            f"- [{p.language.value.upper()}] {p.title} | "
            f"{', '.join(p.authors[:3])} | {p.journal} ({p.year}) | kw: {kw}"
        )
    if len(papers) > max_papers:
        lines.append(f"... and {len(papers) - max_papers} more papers")
    return "\n".join(lines)


def _parse_json_object(text: str) -> dict:
    """Robustly extract a JSON object from LLM output."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _compute_timeliness(topic: TopicProposal, papers: list[Paper]) -> float:
    """Estimate timeliness from paper recency and volume trends.

    Heuristic: a topic is timely when related papers are increasing in the
    recent window, indicating growing scholarly interest.

    Returns a float in [0, 1].
    """
    if not papers:
        return 0.5  # neutral when we have no data

    current = _current_year()
    recent_cutoff = current - _RECENCY_WINDOW_YEARS

    # Count papers per year in recent window
    recent_year_counts: Counter = Counter()
    total_recent = 0
    for p in papers:
        if p.year >= recent_cutoff:
            recent_year_counts[p.year] += 1
            total_recent += 1

    if total_recent == 0:
        return 0.2  # topic exists in corpus but no recent activity

    # Simple trend: compare the most recent half of the window to the older half
    midpoint = recent_cutoff + _RECENCY_WINDOW_YEARS // 2
    older_half = sum(c for y, c in recent_year_counts.items() if y < midpoint)
    newer_half = sum(c for y, c in recent_year_counts.items() if y >= midpoint)

    if older_half + newer_half == 0:
        return 0.5

    # Ratio of newer to total recent gives a 0-1 growth signal
    growth_ratio = newer_half / (older_half + newer_half)

    # Also reward sheer volume of recent papers (capped contribution)
    volume_bonus = min(total_recent / 20.0, 0.2)

    timeliness = min(growth_ratio + volume_bonus, 1.0)
    return round(timeliness, 3)


def _compute_journal_fit(topic: TopicProposal, papers: list[Paper]) -> float:
    """Estimate how well the topic fits its target journals.

    Heuristic: check how many corpus papers appear in the topic's target
    journals, and whether those journals publish on related keywords.

    Returns a float in [0, 1].
    """
    if not topic.target_journals:
        return 0.3  # no target journal specified; low but not zero

    target_set = {j.strip().lower() for j in topic.target_journals}

    matching_papers = [
        p for p in papers if p.journal.strip().lower() in target_set
    ]

    if not matching_papers:
        # Target journal not represented in corpus -- uncertain fit
        return 0.4

    # Keyword overlap between topic gap description and matching papers
    topic_words = set(topic.gap_description.lower().split())
    topic_words.update(topic.research_question.lower().split())

    overlap_scores: list[float] = []
    for p in matching_papers:
        paper_words = set(kw.lower() for kw in p.keywords)
        if paper_words:
            overlap = len(topic_words & paper_words) / max(len(paper_words), 1)
            overlap_scores.append(min(overlap, 1.0))

    # Base score from presence in target journal + keyword relevance
    presence_score = min(len(matching_papers) / 10.0, 0.5)
    keyword_score = (
        (sum(overlap_scores) / len(overlap_scores)) * 0.5
        if overlap_scores
        else 0.0
    )

    return round(min(presence_score + keyword_score, 1.0), 3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_topic(
    topic: TopicProposal,
    papers: list[Paper],
    llm_router: LLMRouter,
) -> TopicProposal:
    """Score a topic proposal and return it with updated score fields.

    Scores:
        - novelty (0-1): LLM-assessed originality vs. existing corpus
        - feasibility (0-1): LLM-assessed practicality of the research
        - journal_fit (0-1): heuristic match to target journal scope
        - timeliness (0-1): heuristic based on publication recency trends
        - overall_score: weighted average of the four dimensions

    Parameters
    ----------
    topic:
        The proposal to score.
    papers:
        Corpus of papers for context.
    llm_router:
        LLM router (uses task_type="topic_discovery").

    Returns
    -------
    TopicProposal with all score fields populated.
    """
    # --- LLM-based scores: novelty and feasibility -------------------------
    corpus_summary = _build_corpus_summary(papers)
    user_prompt = _NOVELTY_FEASIBILITY_PROMPT.format(
        title=topic.title,
        research_question=topic.research_question,
        gap_description=topic.gap_description,
        target_journals=", ".join(topic.target_journals) if topic.target_journals else "not specified",
        corpus_count=len(papers),
        corpus_summary=corpus_summary,
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert evaluator of comparative-literature research "
                "proposals. Return well-structured JSON only."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    novelty = 0.5
    feasibility = 0.5

    try:
        response = llm_router.complete(
            task_type="topic_discovery",
            messages=messages,
            temperature=0.2,
        )
        raw_text = llm_router.get_response_text(response)
        parsed = _parse_json_object(raw_text)
        if "novelty" in parsed:
            novelty = max(0.0, min(1.0, float(parsed["novelty"])))
        if "feasibility" in parsed:
            feasibility = max(0.0, min(1.0, float(parsed["feasibility"])))
        logger.info(
            "LLM scores for '%s': novelty=%.2f, feasibility=%.2f",
            topic.title,
            novelty,
            feasibility,
        )
    except Exception:
        logger.exception(
            "LLM scoring failed for topic '%s'; using defaults", topic.title
        )

    # --- Heuristic scores: timeliness and journal fit ----------------------
    timeliness = _compute_timeliness(topic, papers)
    journal_fit = _compute_journal_fit(topic, papers)

    # --- Weighted overall score --------------------------------------------
    overall = (
        SCORE_WEIGHTS["novelty"] * novelty
        + SCORE_WEIGHTS["feasibility"] * feasibility
        + SCORE_WEIGHTS["journal_fit"] * journal_fit
        + SCORE_WEIGHTS["timeliness"] * timeliness
    )

    # Update the topic in place and return it
    topic.novelty_score = round(novelty, 3)
    topic.feasibility_score = round(feasibility, 3)
    topic.journal_fit_score = round(journal_fit, 3)
    topic.timeliness_score = round(timeliness, 3)
    topic.overall_score = round(overall, 3)

    logger.info(
        "Topic '%s' scored: novelty=%.2f feasibility=%.2f journal_fit=%.2f "
        "timeliness=%.2f => overall=%.3f",
        topic.title,
        topic.novelty_score,
        topic.feasibility_score,
        topic.journal_fit_score,
        topic.timeliness_score,
        topic.overall_score,
    )
    return topic
