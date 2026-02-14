"""Journal fit analysis for manuscripts.

Compares a manuscript against a target journal profile to assess compatibility
on dimensions like word count, reference count, close-reading depth, and
theoretical framework alignment.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.knowledge_base.models import Manuscript
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


@dataclass
class FitReport:
    """Result of a journal-fit analysis."""

    fit_score: float = 0.0  # 0-1
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt for LLM-based theoretical alignment check
# ---------------------------------------------------------------------------

_ALIGNMENT_PROMPT = """\
You are an expert in academic journal publishing for literary studies and the humanities.

Evaluate how well the following manuscript aligns with the target journal's profile.
Focus on theoretical framework alignment, methodological compatibility, and topical scope.

Journal profile:
{journal_profile_json}

Manuscript title: {title}
Manuscript abstract: {abstract}

--- MANUSCRIPT TEXT (truncated) ---
{text_excerpt}
--- END ---

Return your analysis as JSON:
{{
  "alignment_score": <0.0 to 1.0>,
  "alignment_comments": ["<comment 1>", ...],
  "alignment_suggestions": ["<suggestion 1>", ...]
}}

Return ONLY the JSON object.
"""


def _parse_json_response(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    text = text.strip()
    return json.loads(text)


def _word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(text.split())


def _count_references(manuscript: Manuscript) -> int:
    """Estimate the number of references from reference_ids or in-text markers."""
    if manuscript.reference_ids:
        return len(manuscript.reference_ids)
    # Fallback: count unique citation markers in the text
    text = manuscript.full_text or ""
    # Match patterns like (Author Year), (Author, Year), [1], [Author Year]
    paren_cites = set(re.findall(r"\(([A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)*(?:,?\s*\d{4}))\)", text))
    bracket_cites = set(re.findall(r"\[(\d+)\]", text))
    return len(paren_cites) + len(bracket_cites)


def _count_close_reading_passages(text: str) -> int:
    """Estimate the number of close-reading passages by counting block quotes and
    inline quotations of substantial length."""
    if not text:
        return 0
    block_quotes = len(re.findall(r"\n\s{4,}.{80,}", text))
    long_inline = len(re.findall(r'"[^"]{100,}"', text))
    return block_quotes + long_inline


class JournalFitAnalyzer:
    """Analyzes how well a manuscript fits a target journal's profile."""

    async def analyze_fit(
        self,
        manuscript: Manuscript,
        journal_profile: dict,
        llm_router: LLMRouter,
    ) -> FitReport:
        """Compare manuscript against journal profile.

        Parameters
        ----------
        manuscript : Manuscript
            The manuscript to evaluate.
        journal_profile : dict
            Target journal profile (word limits, ref expectations, etc.).
        llm_router : LLMRouter
            LLM router for theoretical-alignment check.

        Returns
        -------
        FitReport
            Score (0-1), issues list, and suggestions list.
        """
        issues: list[str] = []
        suggestions: list[str] = []
        sub_scores: list[float] = []

        manuscript_text = manuscript.full_text or "\n\n".join(
            f"{name}\n{content}" for name, content in manuscript.sections.items()
        )

        # ---- Word count check ----
        wc = manuscript.word_count or _word_count(manuscript_text)
        word_limit = journal_profile.get("word_limit") or journal_profile.get("formatting", {}).get("word_limit")
        if word_limit:
            if isinstance(word_limit, dict):
                lo = word_limit.get("min", 0)
                hi = word_limit.get("max", 999999)
            else:
                lo, hi = 0, int(word_limit)

            if wc < lo:
                issues.append(f"Manuscript is under the minimum word count ({wc} vs {lo} required).")
                suggestions.append(f"Expand the manuscript by approximately {lo - wc} words.")
                sub_scores.append(max(0.0, wc / lo))
            elif wc > hi:
                issues.append(f"Manuscript exceeds the maximum word count ({wc} vs {hi} allowed).")
                suggestions.append(f"Reduce the manuscript by approximately {wc - hi} words.")
                sub_scores.append(max(0.0, hi / wc))
            else:
                sub_scores.append(1.0)
        else:
            sub_scores.append(0.8)  # no limit known, mild penalty

        # ---- Reference count check ----
        ref_count = _count_references(manuscript)
        expected_refs = journal_profile.get("expected_references") or journal_profile.get("formatting", {}).get("expected_references")
        if expected_refs:
            if isinstance(expected_refs, dict):
                ref_lo = expected_refs.get("min", 0)
                ref_hi = expected_refs.get("max", 999)
            else:
                ref_lo, ref_hi = 0, int(expected_refs)

            if ref_count < ref_lo:
                issues.append(f"Reference count is low ({ref_count} vs minimum {ref_lo}).")
                suggestions.append("Add more secondary sources to meet the journal's expectations.")
                sub_scores.append(max(0.0, ref_count / ref_lo))
            elif ref_count > ref_hi:
                issues.append(f"Reference count is high ({ref_count} vs maximum {ref_hi}).")
                suggestions.append("Consider trimming peripheral references.")
                sub_scores.append(max(0.0, ref_hi / ref_count))
            else:
                sub_scores.append(1.0)
        else:
            sub_scores.append(0.8)

        # ---- Close-reading passages check ----
        cr_count = _count_close_reading_passages(manuscript_text)
        expected_cr = journal_profile.get("expected_close_readings") or journal_profile.get("formatting", {}).get("expected_close_readings")
        if expected_cr:
            min_cr = int(expected_cr) if not isinstance(expected_cr, dict) else expected_cr.get("min", 0)
            if cr_count < min_cr:
                issues.append(f"Only {cr_count} close-reading passage(s) detected; journal typically expects at least {min_cr}.")
                suggestions.append("Add more in-depth textual analysis passages with extended quotations.")
                sub_scores.append(max(0.0, cr_count / min_cr))
            else:
                sub_scores.append(1.0)
        else:
            sub_scores.append(0.8)

        # ---- LLM-based theoretical alignment ----
        alignment_score, alignment_comments, alignment_suggestions = await self._check_alignment(
            manuscript, manuscript_text, journal_profile, llm_router
        )
        sub_scores.append(alignment_score)
        issues.extend(alignment_comments)
        suggestions.extend(alignment_suggestions)

        # ---- Aggregate ----
        fit_score = sum(sub_scores) / len(sub_scores) if sub_scores else 0.0
        fit_score = round(min(1.0, max(0.0, fit_score)), 2)

        return FitReport(fit_score=fit_score, issues=issues, suggestions=suggestions)

    # ------------------------------------------------------------------
    # LLM alignment helper
    # ------------------------------------------------------------------

    async def _check_alignment(
        self,
        manuscript: Manuscript,
        manuscript_text: str,
        journal_profile: dict,
        llm_router: LLMRouter,
    ) -> tuple[float, list[str], list[str]]:
        """Use LLM to evaluate theoretical and methodological alignment."""
        # Truncate text for prompt efficiency
        excerpt = manuscript_text[:6000]

        prompt = _ALIGNMENT_PROMPT.format(
            journal_profile_json=json.dumps(journal_profile, ensure_ascii=False, indent=2),
            title=manuscript.title,
            abstract=manuscript.abstract or "(no abstract provided)",
            text_excerpt=excerpt,
        )

        messages = [
            {"role": "user", "content": prompt},
        ]

        try:
            response = llm_router.complete(task_type="self_review", messages=messages)
            raw = llm_router.get_response_text(response)
            data = _parse_json_response(raw)
            score = float(data.get("alignment_score", 0.5))
            comments = data.get("alignment_comments", [])
            sug = data.get("alignment_suggestions", [])
            return score, comments, sug
        except Exception:
            logger.warning("LLM alignment check failed; defaulting to 0.5.")
            return 0.5, [], ["Could not perform LLM-based alignment analysis; review manually."]
