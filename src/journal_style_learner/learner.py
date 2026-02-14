"""Journal style learner.

Analyzes sample papers from a target journal and produces a StyleProfile
that is persisted as YAML under ``config/journal_profiles/``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from src.journal_style_learner.style_extractor import StyleExtractor
from src.journal_style_learner.style_profile import (
    FormattingProfile,
    JournalInfo,
    LearnedPatterns,
    ReferenceExample,
    StyleProfile,
)
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)

PROFILES_DIR = Path("config/journal_profiles")

# ---------------------------------------------------------------------------
# LLM prompt for deep style analysis
# ---------------------------------------------------------------------------

_ANALYSIS_PROMPT = """\
You are an expert in academic publishing conventions for literary studies and the humanities.

Analyze the following extracted style features from {n_papers} sample paper(s) published in
the journal "{journal_name}". Then produce a comprehensive style profile for the journal.

Extracted features (aggregated across samples):
{features_json}

Sample text excerpts (first 2000 chars of each paper):
{excerpts}

Based on this evidence, produce a JSON style profile with these keys:
{{
  "formatting": {{
    "citation_style": "<MLA|Chicago|APA|GB/T 7714|other>",
    "citation_method": "<parenthetical|footnote|endnote>",
    "bibliography": "<Works Cited|References|Bibliography|other>",
    "abstract": "<required|optional|none>",
    "word_limit": <integer or null>,
    "block_quote": "<indent|quotation_marks|both>",
    "footnotes": "<footnotes|endnotes|none>",
    "reference_examples": [{{"type": "<book|article|chapter>", "example": "<formatted reference>"}}],
    "writing_conventions": ["<convention 1>", ...]
  }},
  "learned_patterns": {{
    "avg_paragraph_length": <integer>,
    "avg_sentence_length": <integer>,
    "passive_voice_ratio": <float 0-1>,
    "common_section_headings": ["<heading 1>", ...],
    "typical_argument_structures": ["<structure 1>", ...],
    "frequent_theoretical_frameworks": ["<framework 1>", ...],
    "hedging_frequency": "<low|medium|high>",
    "notes": ["<observation 1>", ...]
  }}
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


class JournalStyleLearner:
    """Learns a journal's style conventions from sample papers."""

    def __init__(self) -> None:
        self._extractor = StyleExtractor()

    async def learn_style(
        self,
        journal_name: str,
        sample_papers: list[str],
        llm_router: LLMRouter,
    ) -> dict:
        """Analyze sample papers and generate a style profile.

        Parameters
        ----------
        journal_name : str
            Name of the target journal.
        sample_papers : list[str]
            List of plain-text contents of sample papers from the journal.
        llm_router : LLMRouter
            LLM router for the deep analysis call.

        Returns
        -------
        dict
            The generated style profile as a dictionary (also saved as YAML).
        """
        # ------------------------------------------------------------------
        # Step 1: rule-based feature extraction from each paper
        # ------------------------------------------------------------------
        all_features: list[dict[str, Any]] = []
        excerpts_parts: list[str] = []

        for idx, paper_text in enumerate(sample_papers, start=1):
            features = self._extractor.extract_style_features(paper_text)
            all_features.append(features)
            excerpt = paper_text[:2000]
            excerpts_parts.append(f"--- Paper {idx} ---\n{excerpt}\n--- End Paper {idx} ---")

        aggregated = self._aggregate_features(all_features)

        # ------------------------------------------------------------------
        # Step 2: LLM-based deep analysis
        # ------------------------------------------------------------------
        prompt = _ANALYSIS_PROMPT.format(
            n_papers=len(sample_papers),
            journal_name=journal_name,
            features_json=json.dumps(aggregated, ensure_ascii=False, indent=2),
            excerpts="\n\n".join(excerpts_parts),
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            response = llm_router.complete(task_type="self_review", messages=messages)
            raw = llm_router.get_response_text(response)
            llm_data = _parse_json_response(raw)
        except Exception:
            logger.warning("LLM analysis failed; building profile from rule-based features only.")
            llm_data = {}

        # ------------------------------------------------------------------
        # Step 3: build StyleProfile
        # ------------------------------------------------------------------
        profile = self._build_profile(journal_name, aggregated, llm_data)
        profile_dict = profile.model_dump()

        # ------------------------------------------------------------------
        # Step 4: save to YAML
        # ------------------------------------------------------------------
        self._save_profile(journal_name, profile_dict)

        return profile_dict

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_features(features_list: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge features extracted from multiple papers."""
        if not features_list:
            return {}
        if len(features_list) == 1:
            return features_list[0]

        aggregated: dict[str, Any] = {}

        # Citation style: majority vote
        styles = [f.get("citation_style", "unknown") for f in features_list]
        aggregated["citation_style"] = max(set(styles), key=styles.count)

        # Footnote style: majority vote
        fn_styles = [f.get("footnote_style", "none") for f in features_list]
        aggregated["footnote_style"] = max(set(fn_styles), key=fn_styles.count)

        # Headings: union
        all_headings: list[str] = []
        for f in features_list:
            all_headings.extend(f.get("heading_patterns", []))
        aggregated["heading_patterns"] = list(dict.fromkeys(all_headings))  # dedupe, preserve order

        # Block quotes: majority vote
        bq = [f.get("block_quote_patterns", "unknown") for f in features_list]
        aggregated["block_quote_patterns"] = max(set(bq), key=bq.count)

        # Numeric averages
        for key in ("avg_paragraph_length", "avg_sentence_length", "passive_voice_ratio"):
            values = [f.get(key, 0) for f in features_list if f.get(key) is not None]
            if values:
                aggregated[key] = round(sum(values) / len(values), 2)

        return aggregated

    @staticmethod
    def _build_profile(
        journal_name: str,
        rule_features: dict[str, Any],
        llm_data: dict[str, Any],
    ) -> StyleProfile:
        """Construct a StyleProfile from rule-based and LLM-derived data."""
        # LLM data takes precedence where available; rule-based features fill gaps.
        fmt_data = llm_data.get("formatting", {})
        lp_data = llm_data.get("learned_patterns", {})

        ref_examples_raw = fmt_data.get("reference_examples", [])
        ref_examples = [
            ReferenceExample(type=r.get("type", ""), example=r.get("example", ""))
            for r in ref_examples_raw
            if isinstance(r, dict)
        ]

        formatting = FormattingProfile(
            citation_style=fmt_data.get("citation_style", rule_features.get("citation_style", "MLA")),
            citation_method=fmt_data.get("citation_method", "parenthetical"),
            bibliography=fmt_data.get("bibliography", "Works Cited"),
            abstract=fmt_data.get("abstract", "required"),
            word_limit=fmt_data.get("word_limit"),
            block_quote=fmt_data.get("block_quote", rule_features.get("block_quote_patterns", "indent")),
            footnotes=fmt_data.get("footnotes", rule_features.get("footnote_style", "none")),
            reference_examples=ref_examples,
            writing_conventions=fmt_data.get("writing_conventions", []),
        )

        learned = LearnedPatterns(
            avg_paragraph_length=lp_data.get("avg_paragraph_length", rule_features.get("avg_paragraph_length")),
            avg_sentence_length=lp_data.get("avg_sentence_length", rule_features.get("avg_sentence_length")),
            passive_voice_ratio=lp_data.get("passive_voice_ratio", rule_features.get("passive_voice_ratio")),
            common_section_headings=lp_data.get("common_section_headings", rule_features.get("heading_patterns", [])),
            typical_argument_structures=lp_data.get("typical_argument_structures", []),
            frequent_theoretical_frameworks=lp_data.get("frequent_theoretical_frameworks", []),
            hedging_frequency=lp_data.get("hedging_frequency"),
            notes=lp_data.get("notes", []),
        )

        journal_info = JournalInfo(name=journal_name)

        return StyleProfile(
            journal_info=journal_info,
            formatting=formatting,
            learned_patterns=learned,
        )

    @staticmethod
    def _save_profile(journal_name: str, profile_dict: dict) -> Path:
        """Persist the profile as a YAML file."""
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        # Sanitize journal name for filesystem
        safe_name = journal_name.lower().replace(" ", "_").replace("/", "_")
        path = PROFILES_DIR / f"{safe_name}.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(profile_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        logger.info("Saved journal style profile to %s", path)
        return path
