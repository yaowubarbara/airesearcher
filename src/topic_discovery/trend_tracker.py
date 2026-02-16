"""Cluster P-ontology annotations into broad problématique directions.

Takes a set of PaperAnnotation objects (T, M, S, G) and uses an LLM to
synthesize them into 3-8 coherent research directions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.knowledge_base.models import (
    Paper,
    PaperAnnotation,
    ProblematiqueDirection,
)
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_DIRECTION_SYNTHESIS_PROMPT = """\
You are a senior comparatist synthesizing a corpus of per-paper problématique \
annotations into broad research directions.

Each annotation has the form P = <T, M, S, G>:
  T = Tensions (intellectual forces pulling in opposite directions)
  M = Mediators (operative mechanisms traversing the tension)
  S = Scale (textual / perceptual / mediational / institutional / methodological)
  G = Gap (mediational_gap / temporal_flattening / method_naturalization / \
scale_mismatch / incommensurability_blindspot)

--- ANNOTATIONS ({count} papers) ---
{annotation_summaries}
--- END ANNOTATIONS ---

Synthesize these into **3 to 8** problématique directions.  A direction is a \
coherent cluster of shared or complementary T/M/S/G patterns.  For each \
direction, identify:

1. What tensions recur across papers in this cluster?
2. What mediators are used (or missing)?
3. At what scale does this direction predominantly operate?
4. What gap type dominates?
5. What is NOT yet addressed — what is this direction's blind spot?

Return a JSON array of objects with exactly these keys:
  "title": string (concise label, max 15 words),
  "description": string (2-3 sentences explaining the direction and its \
blind spot),
  "dominant_tensions": [string, ...] (the shared tensions),
  "dominant_mediators": [string, ...] (the shared mediators),
  "dominant_scale": string (one of the 5 scale values),
  "dominant_gap": string (one of the 5 gap values),
  "paper_indices": [int, ...] (0-based indices of papers belonging to this \
direction)

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


def _build_annotation_summaries(
    annotations: list[PaperAnnotation],
    papers: list[Paper],
) -> str:
    """Build a compact text summary of annotations for the LLM prompt."""
    paper_map = {p.id: p for p in papers if p.id}
    lines: list[str] = []
    for i, ann in enumerate(annotations):
        paper = paper_map.get(ann.paper_id)
        title = paper.title[:80] if paper else f"paper_{ann.paper_id[:8]}"
        lines.append(
            f"[{i}] {title}\n"
            f"  T: {', '.join(ann.tensions) if ann.tensions else '(none)'}\n"
            f"  M: {', '.join(ann.mediators) if ann.mediators else '(none)'}\n"
            f"  S: {ann.scale.value}\n"
            f"  G: {ann.gap.value}\n"
            f"  Evidence: {ann.evidence[:200] if ann.evidence else '(none)'}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def cluster_into_directions(
    annotations: list[PaperAnnotation],
    papers: list[Paper],
    llm_router: LLMRouter,
) -> list[ProblematiqueDirection]:
    """Cluster annotations into 3-8 problématique directions via LLM.

    Parameters
    ----------
    annotations:
        P-ontology annotations (one per paper).
    papers:
        The paper corpus (for titles in the prompt).
    llm_router:
        LLM router (uses task_type="topic_discovery").

    Returns
    -------
    list[ProblematiqueDirection]
    """
    if not annotations:
        return []

    summaries = _build_annotation_summaries(annotations, papers)

    user_prompt = _DIRECTION_SYNTHESIS_PROMPT.format(
        count=len(annotations),
        annotation_summaries=summaries,
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
            temperature=0.4,
        )
        raw_text = llm_router.get_response_text(response)
        raw_directions = _parse_json_array(raw_text)
    except Exception:
        logger.exception("Direction synthesis LLM call failed")
        return []

    # Map paper_indices -> paper_ids
    directions: list[ProblematiqueDirection] = []
    for d in raw_directions:
        if not isinstance(d, dict) or "title" not in d:
            continue

        paper_indices = d.get("paper_indices", [])
        paper_ids = []
        for idx in paper_indices:
            if isinstance(idx, int) and 0 <= idx < len(annotations):
                paper_ids.append(annotations[idx].paper_id)

        direction = ProblematiqueDirection(
            title=d.get("title", "Untitled Direction"),
            description=d.get("description", ""),
            dominant_tensions=d.get("dominant_tensions", []) if isinstance(d.get("dominant_tensions"), list) else [],
            dominant_mediators=d.get("dominant_mediators", []) if isinstance(d.get("dominant_mediators"), list) else [],
            dominant_scale=d.get("dominant_scale"),
            dominant_gap=d.get("dominant_gap"),
            paper_ids=paper_ids,
        )
        directions.append(direction)

    logger.info("Clustered %d annotations into %d directions", len(annotations), len(directions))
    return directions
