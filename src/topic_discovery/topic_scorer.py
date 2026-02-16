"""Generate concrete research topics for each problématique direction.

Given a direction and its supporting paper annotations, proposes exactly 10
specific research topics.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.knowledge_base.models import (
    Paper,
    PaperAnnotation,
    ProblematiqueDirection,
    TopicProposal,
)
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_TOPIC_GENERATION_PROMPT = """\
You are a senior comparatist generating concrete research topics from a \
broad problématique direction.

--- DIRECTION ---
Title: {direction_title}
Description: {direction_description}
Dominant tensions: {dominant_tensions}
Dominant mediators: {dominant_mediators}
Dominant scale: {dominant_scale}
Dominant gap: {dominant_gap}
--- END DIRECTION ---

--- SUPPORTING PAPERS ({paper_count}) ---
{paper_summaries}
--- END PAPERS ---

Propose exactly **10** specific, publishable research topics that fall under \
this direction.  Each topic should:
  - Address the direction's dominant gap type
  - Be specific enough for a 8000-12000 word journal article
  - Name concrete texts, authors, or corpora (not vague gestures)
  - Formulate a clear research question with a falsifiable thesis

Return a JSON array of exactly 10 objects with these keys:
  "title": string (concise, max 20 words),
  "research_question": string (one well-formed question),
  "gap_description": string (2-3 sentences explaining the specific gap this \
topic addresses)

Output ONLY the JSON array, no other text.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_array(text: str) -> list[Any]:
    """Robustly extract a JSON array from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []


def _build_paper_summaries(
    direction: ProblematiqueDirection,
    papers: list[Paper],
    annotations: list[PaperAnnotation],
) -> str:
    """Build summaries of papers belonging to this direction, with annotations."""
    paper_map = {p.id: p for p in papers if p.id}
    ann_map = {a.paper_id: a for a in annotations}

    lines: list[str] = []
    for pid in direction.paper_ids:
        paper = paper_map.get(pid)
        ann = ann_map.get(pid)
        if not paper:
            continue
        title = paper.title[:80]
        t_str = ", ".join(ann.tensions) if ann and ann.tensions else "(none)"
        m_str = ", ".join(ann.mediators) if ann and ann.mediators else "(none)"
        s_str = ann.scale.value if ann else "?"
        g_str = ann.gap.value if ann else "?"
        evidence = (ann.evidence[:150] if ann and ann.evidence else "")
        lines.append(
            f"- {title} ({paper.year})\n"
            f"  T: {t_str} | M: {m_str} | S: {s_str} | G: {g_str}\n"
            f"  {evidence}"
        )

    return "\n".join(lines) if lines else "(no supporting papers)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_topics_for_direction(
    direction: ProblematiqueDirection,
    papers: list[Paper],
    annotations: list[PaperAnnotation],
    llm_router: LLMRouter,
) -> list[TopicProposal]:
    """Generate 10 research topics for a single direction.

    Parameters
    ----------
    direction:
        The problématique direction to generate topics for.
    papers:
        Full paper corpus (for building summaries).
    annotations:
        All P-ontology annotations.
    llm_router:
        LLM router (uses task_type="topic_discovery").

    Returns
    -------
    list[TopicProposal] with direction_id set.
    """
    paper_summaries = _build_paper_summaries(direction, papers, annotations)

    user_prompt = _TOPIC_GENERATION_PROMPT.format(
        direction_title=direction.title,
        direction_description=direction.description,
        dominant_tensions=", ".join(direction.dominant_tensions) if direction.dominant_tensions else "(none)",
        dominant_mediators=", ".join(direction.dominant_mediators) if direction.dominant_mediators else "(none)",
        dominant_scale=direction.dominant_scale or "(unspecified)",
        dominant_gap=direction.dominant_gap or "(unspecified)",
        paper_count=len(direction.paper_ids),
        paper_summaries=paper_summaries,
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior researcher in comparative literature. "
                "Return well-structured JSON only."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = llm_router.complete(
            task_type="topic_discovery",
            messages=messages,
            temperature=0.5,
        )
        raw_text = llm_router.get_response_text(response)
        raw_topics = _parse_json_array(raw_text)
    except Exception:
        logger.exception("Topic generation LLM call failed for direction '%s'", direction.title)
        return []

    topics: list[TopicProposal] = []
    for t in raw_topics:
        if not isinstance(t, dict) or "title" not in t:
            continue
        topic = TopicProposal(
            title=t.get("title", "Untitled"),
            research_question=t.get("research_question", ""),
            gap_description=t.get("gap_description", ""),
            direction_id=direction.id,
            evidence_paper_ids=direction.paper_ids[:],
            target_journals=[],
            # Scores set to 0.0 — no separate scoring pass
            novelty_score=0.0,
            feasibility_score=0.0,
            journal_fit_score=0.0,
            timeliness_score=0.0,
            overall_score=0.0,
        )
        topics.append(topic)

    logger.info(
        "Generated %d topics for direction '%s'",
        len(topics),
        direction.title,
    )
    return topics
