"""Multi-Agent Debate self-review module.

Implements three reviewer agents with distinct perspectives plus a meta-reviewer
that synthesizes their feedback into a consolidated ReviewResult.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.knowledge_base.models import Manuscript
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReviewResult:
    """Consolidated review output from the multi-agent debate."""

    scores: dict[str, float] = field(default_factory=dict)
    comments: list[str] = field(default_factory=list)
    revision_instructions: list[str] = field(default_factory=list)
    overall_recommendation: str = "major_revision"  # accept / minor_revision / major_revision / reject


# ---------------------------------------------------------------------------
# Reviewer system prompts
# ---------------------------------------------------------------------------

REVIEWER_A_SYSTEM = (
    "You are Reviewer A, a strict and meticulous academic reviewer. "
    "Your focus is on identifying argument holes, logical gaps, unsupported claims, "
    "and citation issues (missing citations, mis-cited sources, incorrect page numbers). "
    "You are skeptical by nature: every claim must be backed by evidence. "
    "Be specific and reference the exact passage or section where each problem occurs."
)

REVIEWER_B_SYSTEM = (
    "You are Reviewer B, a constructive academic reviewer. "
    "Your goal is to help the author strengthen the manuscript. "
    "Suggest concrete improvements: better transitions, deeper close readings, "
    "alternative theoretical angles, additional secondary sources, and places where "
    "the argument could be expanded or tightened. "
    "Maintain a supportive but rigorous tone."
)

REVIEWER_C_SYSTEM = (
    "You are Reviewer C, an expert on journal fit and stylistic conventions. "
    "Evaluate how well the manuscript matches the target journal's expectations: "
    "scope, methodology, writing register, citation style, length, and overall presentation. "
    "Identify mismatches and suggest adjustments to increase acceptance likelihood."
)

META_REVIEWER_SYSTEM = (
    "You are a meta-reviewer synthesizing feedback from three independent reviewers. "
    "Consolidate their scores, comments, and revision suggestions into a single, "
    "coherent review. Resolve disagreements by reasoning about the strength of each "
    "reviewer's argument. Produce a clear, prioritized list of revision instructions "
    "and a single overall recommendation (accept, minor_revision, major_revision, or reject)."
)

# ---------------------------------------------------------------------------
# Shared review prompt template
# ---------------------------------------------------------------------------

_REVIEW_PROMPT = """\
Review the following manuscript for the journal "{journal_name}".

Journal profile:
{journal_profile_json}

Manuscript title: {title}
Language: {language}

--- MANUSCRIPT TEXT ---
{text}
--- END MANUSCRIPT TEXT ---

Provide your review as JSON with exactly these keys:
{{
  "scores": {{
    "originality": <1-5>,
    "close_reading_depth": <1-5>,
    "argument_coherence": <1-5>,
    "citation_quality": <1-5>,
    "style_match": <1-5>
  }},
  "comments": ["<specific comment 1>", ...],
  "revision_suggestions": ["<actionable suggestion 1>", ...]
}}

Return ONLY the JSON object, no additional text.
"""

_META_PROMPT = """\
Below are three independent reviews of a manuscript submitted to "{journal_name}".

{reviews_text}

Synthesize these reviews into a single consolidated review. Resolve any disagreements
by weighing the strength of each reviewer's reasoning.

Return your synthesis as JSON with exactly these keys:
{{
  "scores": {{
    "originality": <1-5>,
    "close_reading_depth": <1-5>,
    "argument_coherence": <1-5>,
    "citation_quality": <1-5>,
    "style_match": <1-5>
  }},
  "comments": ["<consolidated comment 1>", ...],
  "revision_instructions": ["<prioritized instruction 1>", ...],
  "overall_recommendation": "<accept|minor_revision|major_revision|reject>"
}}

Return ONLY the JSON object, no additional text.
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_json_response(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from an LLM response."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    text = text.strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# SelfReviewAgent
# ---------------------------------------------------------------------------


class SelfReviewAgent:
    """Orchestrates a Multi-Agent Debate review of a manuscript."""

    async def review_manuscript(
        self,
        manuscript: Manuscript,
        journal_profile: dict,
        llm_router: LLMRouter,
    ) -> ReviewResult:
        """Run three reviewer agents then synthesize via a meta-reviewer.

        Parameters
        ----------
        manuscript : Manuscript
            The manuscript to review.
        journal_profile : dict
            Target journal profile information.
        llm_router : LLMRouter
            Router for LLM calls (uses task_type="self_review").

        Returns
        -------
        ReviewResult
            Consolidated review with scores, comments, revision instructions,
            and an overall recommendation.
        """
        manuscript_text = manuscript.full_text or "\n\n".join(
            f"## {name}\n{content}" for name, content in manuscript.sections.items()
        )

        journal_name = journal_profile.get("name", manuscript.target_journal)

        # ------------------------------------------------------------------
        # Phase 1: individual reviews
        # ------------------------------------------------------------------
        reviewer_configs = [
            ("Reviewer A (Strict)", REVIEWER_A_SYSTEM),
            ("Reviewer B (Constructive)", REVIEWER_B_SYSTEM),
            ("Reviewer C (Journal Fit)", REVIEWER_C_SYSTEM),
        ]

        individual_reviews: list[dict[str, Any]] = []

        for label, system_prompt in reviewer_configs:
            user_prompt = _REVIEW_PROMPT.format(
                journal_name=journal_name,
                journal_profile_json=json.dumps(journal_profile, ensure_ascii=False, indent=2),
                title=manuscript.title,
                language=manuscript.language.value,
                text=manuscript_text,
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            logger.info("Running %s ...", label)
            response = llm_router.complete(task_type="self_review", messages=messages)
            raw_text = llm_router.get_response_text(response)

            try:
                review_data = _parse_json_response(raw_text)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to parse JSON from %s; using raw text as comment.", label)
                review_data = {
                    "scores": {
                        "originality": 3,
                        "close_reading_depth": 3,
                        "argument_coherence": 3,
                        "citation_quality": 3,
                        "style_match": 3,
                    },
                    "comments": [raw_text],
                    "revision_suggestions": [],
                }

            review_data["_label"] = label
            individual_reviews.append(review_data)

        # ------------------------------------------------------------------
        # Phase 2: meta-review synthesis
        # ------------------------------------------------------------------
        reviews_text_parts: list[str] = []
        for rev in individual_reviews:
            label = rev.pop("_label", "Reviewer")
            reviews_text_parts.append(
                f"=== {label} ===\n{json.dumps(rev, ensure_ascii=False, indent=2)}"
            )

        meta_user_prompt = _META_PROMPT.format(
            journal_name=journal_name,
            reviews_text="\n\n".join(reviews_text_parts),
        )

        meta_messages = [
            {"role": "system", "content": META_REVIEWER_SYSTEM},
            {"role": "user", "content": meta_user_prompt},
        ]

        logger.info("Running meta-reviewer synthesis ...")
        meta_response = llm_router.complete(task_type="self_review", messages=meta_messages)
        meta_raw = llm_router.get_response_text(meta_response)

        try:
            meta_data = _parse_json_response(meta_raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse meta-review JSON; building result from individual reviews.")
            meta_data = self._fallback_synthesis(individual_reviews)

        # ------------------------------------------------------------------
        # Build ReviewResult
        # ------------------------------------------------------------------
        return ReviewResult(
            scores=meta_data.get("scores", {}),
            comments=meta_data.get("comments", []),
            revision_instructions=meta_data.get("revision_instructions", []),
            overall_recommendation=meta_data.get("overall_recommendation", "major_revision"),
        )

    # ------------------------------------------------------------------
    # Fallback synthesis when meta-review JSON parsing fails
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_synthesis(reviews: list[dict[str, Any]]) -> dict[str, Any]:
        """Average scores and merge comments from individual reviews."""
        score_keys = [
            "originality",
            "close_reading_depth",
            "argument_coherence",
            "citation_quality",
            "style_match",
        ]
        averaged: dict[str, float] = {}
        for key in score_keys:
            values = [
                r.get("scores", {}).get(key, 3) for r in reviews
            ]
            averaged[key] = round(sum(values) / max(len(values), 1), 1)

        all_comments: list[str] = []
        all_suggestions: list[str] = []
        for r in reviews:
            all_comments.extend(r.get("comments", []))
            all_suggestions.extend(r.get("revision_suggestions", []))

        avg_score = sum(averaged.values()) / max(len(averaged), 1)
        if avg_score >= 4.0:
            recommendation = "accept"
        elif avg_score >= 3.0:
            recommendation = "minor_revision"
        elif avg_score >= 2.0:
            recommendation = "major_revision"
        else:
            recommendation = "reject"

        return {
            "scores": averaged,
            "comments": all_comments,
            "revision_instructions": all_suggestions,
            "overall_recommendation": recommendation,
        }
