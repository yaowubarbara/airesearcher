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

DISCIPLINE CONSTRAINT: Every direction MUST be framed as a comparative \
literature research area. Do NOT produce directions that belong to sociology, \
political science, area studies, or any other discipline. If a cluster of \
annotations points toward a non-literary field, reframe it through the lens \
of literary-critical inquiry (poetics, narrative theory, hermeneutics, \
translation studies, genre theory, affect theory as applied to literary texts, \
etc.).

Each direction's title and description must be expressed in literary-critical \
vocabulary. Do NOT use proper nouns (specific author names, country names) in \
the title.

Each annotation has the form P = <T, M, S, G>:
  T = Tensions (intellectual forces pulling in opposite directions)
  M = Mediators (operative mechanisms traversing the tension)
  S = Scale (textual / perceptual / mediational / institutional / methodological)
  G = Gap (mediational_gap / temporal_flattening / method_naturalization / \
scale_mismatch / incommensurability_blindspot)

--- ANNOTATIONS ({count} papers) ---
{annotation_summaries}
--- END ANNOTATIONS ---

Synthesize these into **6 to 8** problématique directions.  A direction is a \
coherent cluster of shared or complementary T/M/S/G patterns.  For each \
direction, identify:

1. What tensions recur across papers in this cluster?
2. What mediators are used (or missing)?
3. At what scale does this direction predominantly operate?
4. What gap type dominates?
5. What is NOT yet addressed — what is this direction's blind spot? Each \
direction should identify a blind spot — something the current papers in this \
cluster do NOT address but should.

Tensions and mediators in the direction should be at the level of \
literary-critical concepts, not proper nouns or vague themes.

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
        import asyncio
        response = await asyncio.to_thread(
            llm_router.complete,
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


# ---------------------------------------------------------------------------
# Recency scoring
# ---------------------------------------------------------------------------


def compute_recency_scores(
    directions: list[ProblematiqueDirection],
    papers: list[Paper],
    current_year: int,
) -> None:
    """Compute and set recency_score on each direction (in-place).

    Formula per direction: mean(1.0 / (current_year - paper_year + 1))
    for all papers whose IDs appear in the direction's paper_ids.
    """
    paper_map = {p.id: p for p in papers if p.id}
    for d in directions:
        scores = []
        for pid in d.paper_ids:
            paper = paper_map.get(pid)
            if paper:
                scores.append(1.0 / (current_year - paper.year + 1))
        d.recency_score = sum(scores) / len(scores) if scores else 0.0


# ---------------------------------------------------------------------------
# Delta clustering
# ---------------------------------------------------------------------------

_DELTA_CLUSTER_PROMPT = """\
You are a senior comparatist. You have an existing set of research directions \
and a batch of NEW paper annotations that have not yet been assigned.

--- EXISTING DIRECTIONS ---
{existing_directions}
--- END EXISTING DIRECTIONS ---

--- NEW ANNOTATIONS ({count} papers) ---
{new_annotation_summaries}
--- END NEW ANNOTATIONS ---

For each new annotation, decide whether it fits an EXISTING direction or \
requires a NEW direction. You may create at most 2 new directions.

Return a JSON object with exactly these keys:
  "assignments": [
    {{"annotation_index": int, "direction_id": "existing-dir-id"}}
    ...
  ],
  "new_directions": [
    {{
      "title": string,
      "description": string,
      "dominant_tensions": [string],
      "dominant_mediators": [string],
      "dominant_scale": string,
      "dominant_gap": string,
      "annotation_indices": [int]
    }}
    ...
  ]

Rules:
- Every new annotation must appear in exactly one assignment or one new_direction.
- Use existing direction IDs verbatim.
- At most 2 new_directions.

Output ONLY the JSON object, no other text.
"""


def _build_existing_directions_summary(directions: list[ProblematiqueDirection]) -> str:
    lines = []
    for d in directions:
        lines.append(
            f"[{d.id}] {d.title}\n"
            f"  T: {', '.join(d.dominant_tensions) if d.dominant_tensions else '(none)'}\n"
            f"  M: {', '.join(d.dominant_mediators) if d.dominant_mediators else '(none)'}\n"
            f"  S: {d.dominant_scale or '(none)'}\n"
            f"  G: {d.dominant_gap or '(none)'}\n"
            f"  Papers: {len(d.paper_ids)}"
        )
    return "\n".join(lines)


async def delta_cluster_directions(
    new_annotations: list[PaperAnnotation],
    existing_directions: list[ProblematiqueDirection],
    papers: list[Paper],
    llm_router: LLMRouter,
) -> tuple[list[ProblematiqueDirection], set[str]]:
    """Assign new annotations to existing directions or create up to 2 new ones.

    Returns (all_directions, changed_direction_ids).
    """
    if not new_annotations:
        return existing_directions, set()

    existing_summary = _build_existing_directions_summary(existing_directions)
    new_summary = _build_annotation_summaries(new_annotations, papers)

    user_prompt = _DELTA_CLUSTER_PROMPT.format(
        existing_directions=existing_summary,
        count=len(new_annotations),
        new_annotation_summaries=new_summary,
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
        import asyncio
        response = await asyncio.to_thread(
            llm_router.complete,
            task_type="topic_discovery",
            messages=messages,
            temperature=0.3,
        )
        raw_text = llm_router.get_response_text(response)
        # Parse JSON object
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("Delta cluster: no JSON object found in response")
            return existing_directions, set()
        result = json.loads(text[start : end + 1])
    except Exception:
        logger.exception("Delta cluster LLM call failed")
        return existing_directions, set()

    dir_map = {d.id: d for d in existing_directions if d.id}
    changed_ids: set[str] = set()

    # Process assignments to existing directions
    for assignment in result.get("assignments", []):
        idx = assignment.get("annotation_index")
        dir_id = assignment.get("direction_id")
        if not isinstance(idx, int) or not isinstance(dir_id, str):
            continue
        if idx < 0 or idx >= len(new_annotations):
            continue
        if dir_id not in dir_map:
            continue
        paper_id = new_annotations[idx].paper_id
        if paper_id not in dir_map[dir_id].paper_ids:
            dir_map[dir_id].paper_ids.append(paper_id)
            changed_ids.add(dir_id)

    # Process new directions (max 2)
    new_dirs_data = result.get("new_directions", [])[:2]
    for nd in new_dirs_data:
        if not isinstance(nd, dict) or "title" not in nd:
            continue
        ann_indices = nd.get("annotation_indices", [])
        pids = []
        for idx in ann_indices:
            if isinstance(idx, int) and 0 <= idx < len(new_annotations):
                pids.append(new_annotations[idx].paper_id)
        new_dir = ProblematiqueDirection(
            title=nd.get("title", "New Direction"),
            description=nd.get("description", ""),
            dominant_tensions=nd.get("dominant_tensions", []) if isinstance(nd.get("dominant_tensions"), list) else [],
            dominant_mediators=nd.get("dominant_mediators", []) if isinstance(nd.get("dominant_mediators"), list) else [],
            dominant_scale=nd.get("dominant_scale"),
            dominant_gap=nd.get("dominant_gap"),
            paper_ids=pids,
        )
        existing_directions.append(new_dir)
        # New directions always count as changed (need topic generation)
        changed_ids.add("__new__")

    logger.info(
        "Delta cluster: %d assignments, %d new directions, %d changed",
        len(result.get("assignments", [])),
        len(new_dirs_data),
        len(changed_ids),
    )
    return existing_directions, changed_ids


# ---------------------------------------------------------------------------
# Direction compression
# ---------------------------------------------------------------------------

_COMPRESS_PROMPT = """\
You are a senior comparatist. The following list of research directions has \
grown too large. Merge similar directions that share tensions, mediators, \
or gap types into a smaller set of at most {max_directions} directions.

Preserve ALL paper_ids — every paper must appear in exactly one direction.

--- DIRECTIONS ({count}) ---
{direction_summaries}
--- END DIRECTIONS ---

Return a JSON array of merged directions with these keys:
  "title": string,
  "description": string,
  "dominant_tensions": [string],
  "dominant_mediators": [string],
  "dominant_scale": string,
  "dominant_gap": string,
  "merged_from": [string]  (IDs of directions that were merged),
  "paper_ids": [string]  (union of all paper_ids from merged directions)

Output ONLY the JSON array, no other text.
"""


def _build_direction_summaries_for_compress(directions: list[ProblematiqueDirection]) -> str:
    lines = []
    for d in directions:
        lines.append(
            f"[{d.id}] {d.title}\n"
            f"  T: {', '.join(d.dominant_tensions) if d.dominant_tensions else '(none)'}\n"
            f"  M: {', '.join(d.dominant_mediators) if d.dominant_mediators else '(none)'}\n"
            f"  S: {d.dominant_scale or '(none)'}\n"
            f"  G: {d.dominant_gap or '(none)'}\n"
            f"  Papers: {json.dumps(d.paper_ids)}"
        )
    return "\n".join(lines)


async def compress_directions(
    directions: list[ProblematiqueDirection],
    llm_router: LLMRouter,
    max_directions: int = 10,
) -> list[ProblematiqueDirection]:
    """Merge directions if there are more than max_directions.

    Returns original list unchanged if already under the cap or on LLM failure.
    """
    if len(directions) <= max_directions:
        return directions

    summaries = _build_direction_summaries_for_compress(directions)
    user_prompt = _COMPRESS_PROMPT.format(
        max_directions=max_directions,
        count=len(directions),
        direction_summaries=summaries,
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
        import asyncio
        response = await asyncio.to_thread(
            llm_router.complete,
            task_type="topic_discovery",
            messages=messages,
            temperature=0.3,
        )
        raw_text = llm_router.get_response_text(response)
        merged_raw = _parse_json_array(raw_text)
    except Exception:
        logger.exception("Direction compression LLM call failed")
        return directions

    if not merged_raw:
        logger.warning("Direction compression returned empty result; keeping originals")
        return directions

    # Collect all paper_ids to verify no orphans
    all_paper_ids = set()
    for d in directions:
        all_paper_ids.update(d.paper_ids)

    merged: list[ProblematiqueDirection] = []
    seen_papers: set[str] = set()
    for md in merged_raw:
        if not isinstance(md, dict) or "title" not in md:
            continue
        pids = md.get("paper_ids", [])
        if not isinstance(pids, list):
            pids = []
        pids = [p for p in pids if isinstance(p, str)]
        seen_papers.update(pids)
        merged.append(ProblematiqueDirection(
            title=md.get("title", "Merged Direction"),
            description=md.get("description", ""),
            dominant_tensions=md.get("dominant_tensions", []) if isinstance(md.get("dominant_tensions"), list) else [],
            dominant_mediators=md.get("dominant_mediators", []) if isinstance(md.get("dominant_mediators"), list) else [],
            dominant_scale=md.get("dominant_scale"),
            dominant_gap=md.get("dominant_gap"),
            paper_ids=pids,
        ))

    # Safety: orphaned papers go to first direction
    orphaned = all_paper_ids - seen_papers
    if orphaned and merged:
        merged[0].paper_ids.extend(sorted(orphaned))
        logger.warning("Compression: %d orphaned papers assigned to first direction", len(orphaned))

    logger.info("Compressed %d directions to %d", len(directions), len(merged))
    return merged
