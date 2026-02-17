"""Per-paper P-ontology annotation for research gap discovery.

Annotates each paper with P = <T, M, S, G> (Tension, Mediator, Scale, Gap)
using a structured 6-step LLM process.  Replaces the earlier STORM
multi-perspective approach.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    AnnotationGap,
    AnnotationScale,
    Paper,
    PaperAnnotation,
)
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_ANNOTATION_PROMPT = """\
You are a senior comparatist performing a structured problématique annotation \
on a scholarly paper.  Follow these six steps IN ORDER.

DISCIPLINARY CONSTRAINT — COMPARATIVE LITERATURE ONLY:
This annotation must stay within comparative literature as a discipline.  \
That means:
  - Tensions must be at the literary-critical CONCEPTUAL level, not at the \
level of proper nouns, geopolitics, or social phenomena.
  - Mediators must name specific literary-critical OPERATIONS, not vague \
thematic labels or field names.
  - If the paper's subject is non-literary (political science, economics, \
public health, etc.), extract ONLY whatever literary-critical thread is \
present; ignore everything else.

---

1. **De-objectification**: If we swapped the text object studied in this paper \
for a completely different text, what underlying *problem* would remain?  \
State the problem in one sentence.

2. **Tensions (T)**: Extract 1–2 core intellectual tensions from the paper.  \
Format each as "A ↔ B" (max 7 words per side).  \
A tension is NOT a topic; it is a pair of forces, frameworks, or demands \
pulling in opposite directions.

CRITICAL RULES for Tensions:
  - NO proper nouns: no person names (Celan, Heidegger, Derrida), no place \
names (France, Germany, Paris), no country names, no movement labels used as \
mere flags.
  - Tensions must be at the LITERARY-CRITICAL CONCEPTUAL level — opposing \
intellectual forces, not opposing entities or historical actors.

  BAD tensions (NEVER produce these):
    "France ↔ Germany"
    "Celan ↔ Heidegger"
    "colonialism ↔ resistance"
    "Romanticism ↔ Abolitionism"
    "East ↔ West"
    "tradition ↔ modernity"
  GOOD tensions (aim for this level of abstraction):
    "aesthetic autonomy ↔ political instrumentalization"
    "formal experiment ↔ communicative transparency"
    "textual surface ↔ historical depth"
    "authorial intention ↔ linguistic undecidability"
    "untranslatability ↔ universalist reading"

3. **Mediators (M)**: Identify 1–2 operative mechanisms or conceptual mediators \
that the paper uses (or fails to use) to traverse the tension.  \
A mediator is NOT a theme or a field name; it is a concrete literary-critical \
OPERATION or DEVICE — something a scholar *does* with texts.

CRITICAL RULES for Mediators:
  - Each mediator must specify a literary-critical operation with enough \
detail to distinguish it from a bare keyword.
  - NO vague single-word topics or field labels.

  BAD mediators (NEVER produce these):
    "postcolonialism"
    "feminism"
    "the archive"
    "translation"
    "intertextuality"
    "memory"
  GOOD mediators (aim for this level of specificity):
    "allegorical figuration as ideological mediation"
    "rhythmic mimesis of bodily experience"
    "editorial apparatus as canon-construction device"
    "close-reading of rhythm to expose affective surplus"
    "translation as cultural transfer across imperial asymmetry"
    "paratextual framing as interpretive constraint"

4. **Scale (S)**: Determine the dominant scale at which the paper's \
problematic operates.  Choose exactly ONE from this fixed list:
   - textual (formal, stylistic, close-reading)
   - perceptual (affect, reception, reader response)
   - mediational (translation, circulation, transfer)
   - institutional (publishing, canon formation, academia)
   - methodological (method itself is the object of inquiry)

5. **Gap (G)**: Determine the principal gap exposed (or left unnoticed) by \
the paper.  Choose exactly ONE from this fixed list:
   - mediational_gap (no mechanism connects the two sides of the tension)
   - temporal_flattening (historical depth is collapsed)
   - method_naturalization (method is assumed, never examined)
   - scale_mismatch (argument operates at wrong scale for its claims)
   - incommensurability_blindspot (untranslatable difference is ignored)

6. **Evidence**: Quote or closely paraphrase ONE sentence from the abstract \
that best supports your annotation.

--- PAPER ---
Title: {title}
Authors: {authors}
Journal: {journal} ({year})
Abstract: {abstract}
---

Return a JSON object with exactly these keys:
  "deobjectification": string (step 1, one sentence),
  "tensions": [string, ...] (step 2, 1-2 items, format "A ↔ B"),
  "mediators": [string, ...] (step 3, 1-2 items),
  "scale": string (step 4, one of the five options),
  "gap": string (step 5, one of the five options),
  "evidence": string (step 6, one sentence)

Output ONLY the JSON object, no other text.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_array(text: str) -> list[Any]:
    """Robustly extract a JSON array from LLM output."""
    text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        logger.warning("No JSON array found in LLM response, returning empty list")
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse JSON from LLM response: %s", exc)
        return []


def _parse_json_object(text: str) -> dict:
    """Robustly extract a JSON object from LLM output."""
    text = text.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


_VALID_SCALES = {s.value for s in AnnotationScale}
_VALID_GAPS = {g.value for g in AnnotationGap}


def _parse_annotation(raw_text: str) -> dict:
    """Parse LLM annotation output into a validated dict."""
    parsed = _parse_json_object(raw_text)
    if not parsed:
        return {}

    # Validate and normalise enums
    scale = parsed.get("scale", "textual")
    if scale not in _VALID_SCALES:
        scale = "textual"
    parsed["scale"] = scale

    gap = parsed.get("gap", "mediational_gap")
    if gap not in _VALID_GAPS:
        gap = "mediational_gap"
    parsed["gap"] = gap

    # Ensure list fields
    if not isinstance(parsed.get("tensions"), list):
        parsed["tensions"] = []
    if not isinstance(parsed.get("mediators"), list):
        parsed["mediators"] = []

    # Ensure string fields
    for key in ("evidence", "deobjectification"):
        if not isinstance(parsed.get(key), str):
            parsed[key] = ""

    return parsed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def annotate_paper(
    paper: Paper,
    llm_router: LLMRouter,
) -> Optional[PaperAnnotation]:
    """Annotate a single paper with P = <T, M, S, G>.

    Returns None if the paper has no abstract or the LLM call fails.
    """
    if not paper.abstract or not paper.abstract.strip():
        return None

    user_prompt = _ANNOTATION_PROMPT.format(
        title=paper.title,
        authors=", ".join(paper.authors[:5]) if paper.authors else "Unknown",
        journal=paper.journal,
        year=paper.year,
        abstract=paper.abstract[:2000],
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
        parsed = _parse_annotation(raw_text)
        if not parsed:
            logger.warning("Failed to parse annotation for paper '%s'", paper.title)
            return None

        return PaperAnnotation(
            paper_id=paper.id or "",
            tensions=parsed["tensions"],
            mediators=parsed["mediators"],
            scale=AnnotationScale(parsed["scale"]),
            gap=AnnotationGap(parsed["gap"]),
            evidence=parsed["evidence"],
            deobjectification=parsed["deobjectification"],
        )
    except Exception:
        logger.exception("LLM annotation failed for paper '%s'", paper.title)
        return None


async def annotate_corpus(
    papers: list[Paper],
    llm_router: LLMRouter,
    db: Database,
) -> list[PaperAnnotation]:
    """Annotate all papers that have abstracts but lack annotations.

    Skips already-annotated papers.  Stores each new annotation in DB.
    Returns all annotations (existing + new).
    """
    if not papers:
        return []

    # Collect existing annotations
    all_annotations: list[PaperAnnotation] = []
    to_annotate: list[Paper] = []

    for paper in papers:
        if not paper.abstract or not paper.abstract.strip():
            continue
        existing = db.get_annotation(paper.id or "")
        if existing:
            all_annotations.append(existing)
        else:
            to_annotate.append(paper)

    logger.info(
        "Annotation corpus: %d papers with abstracts, %d already annotated, %d to annotate",
        len(all_annotations) + len(to_annotate),
        len(all_annotations),
        len(to_annotate),
    )

    # Annotate concurrently in batches
    import asyncio

    CONCURRENCY = 10
    semaphore = asyncio.Semaphore(CONCURRENCY)
    completed = 0

    async def _annotate_one(paper: Paper) -> Optional[PaperAnnotation]:
        nonlocal completed
        async with semaphore:
            ann = await annotate_paper(paper, llm_router)
            completed += 1
            if ann:
                ann_id = db.insert_annotation(ann)
                ann.id = ann_id
                logger.info(
                    "Annotated [%d/%d] '%s': T=%s M=%s S=%s G=%s",
                    completed,
                    len(to_annotate),
                    paper.title[:50],
                    ann.tensions,
                    ann.mediators,
                    ann.scale.value,
                    ann.gap.value,
                )
            else:
                logger.warning(
                    "Skipped [%d/%d] '%s' (no annotation returned)",
                    completed,
                    len(to_annotate),
                    paper.title[:50],
                )
            return ann

    tasks = [_annotate_one(paper) for paper in to_annotate]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, PaperAnnotation):
            all_annotations.append(r)
        elif isinstance(r, Exception):
            logger.warning("Annotation task failed: %s", r)

    logger.info("Annotation complete: %d total annotations", len(all_annotations))
    return all_annotations
