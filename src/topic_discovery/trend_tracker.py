"""Trend tracking across multilingual comparative-literature corpora.

Analyzes a collection of papers to surface trending themes, keyword clusters,
and cross-language gaps (topics discussed in Chinese or French scholarship but
absent from English-language work, and vice versa).
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional

from src.knowledge_base.models import Language, Paper

logger = logging.getLogger(__name__)

# Papers published within this many years of the current year are "recent".
_RECENCY_WINDOW_YEARS = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _current_year() -> int:
    return datetime.utcnow().year


def _is_recent(paper: Paper, window: int = _RECENCY_WINDOW_YEARS) -> bool:
    return paper.year >= _current_year() - window


def _normalize_keyword(kw: str) -> str:
    """Lowercase and strip whitespace for keyword deduplication."""
    return kw.strip().lower()


def _group_by_language(papers: list[Paper]) -> dict[str, list[Paper]]:
    groups: dict[str, list[Paper]] = defaultdict(list)
    for p in papers:
        groups[p.language.value].append(p)
    return groups


def _extract_keyword_counts(
    papers: list[Paper],
) -> Counter:
    """Count normalized keywords across a set of papers."""
    counter: Counter = Counter()
    for p in papers:
        for kw in p.keywords:
            counter[_normalize_keyword(kw)] += 1
    return counter


def _top_keywords_by_language(
    lang_groups: dict[str, list[Paper]],
    top_n: int = 30,
) -> dict[str, list[tuple[str, int]]]:
    """Return the top-N keywords per language."""
    result: dict[str, list[tuple[str, int]]] = {}
    for lang, papers in lang_groups.items():
        counts = _extract_keyword_counts(papers)
        result[lang] = counts.most_common(top_n)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def track_trends(papers: list[Paper]) -> dict:
    """Analyze papers to identify trending themes and cross-language gaps.

    Parameters
    ----------
    papers:
        Full corpus of papers to analyze.

    Returns
    -------
    dict with keys:
        - "keyword_trends": top keywords across all papers, ranked by count
        - "recent_keyword_trends": top keywords among recent papers only
        - "keyword_by_language": per-language keyword rankings
        - "language_distribution": paper counts per language
        - "yearly_counts": paper counts per year (most recent first)
        - "top_journals": journals ranked by paper count
        - "cross_language_gaps": keywords appearing in one language group but
          absent from another, signaling potential research gaps
        - "trending_up": keywords that appear more frequently in recent papers
          relative to the full corpus
    """
    if not papers:
        return {
            "keyword_trends": [],
            "recent_keyword_trends": [],
            "keyword_by_language": {},
            "language_distribution": {},
            "yearly_counts": {},
            "top_journals": [],
            "cross_language_gaps": [],
            "trending_up": [],
        }

    lang_groups = _group_by_language(papers)
    recent_papers = [p for p in papers if _is_recent(p)]

    # --- Overall keyword trends ---
    all_kw_counts = _extract_keyword_counts(papers)
    recent_kw_counts = _extract_keyword_counts(recent_papers)

    # --- Per-language keyword rankings ---
    kw_by_lang = _top_keywords_by_language(lang_groups)

    # --- Language distribution ---
    lang_dist = {lang: len(plist) for lang, plist in lang_groups.items()}

    # --- Yearly counts ---
    year_counter: Counter = Counter()
    for p in papers:
        year_counter[p.year] += 1
    yearly_counts = dict(sorted(year_counter.items(), reverse=True))

    # --- Top journals ---
    journal_counter: Counter = Counter()
    for p in papers:
        journal_counter[p.journal] += 1
    top_journals = journal_counter.most_common(20)

    # --- Cross-language gap detection ---
    cross_language_gaps = _detect_cross_language_gaps(kw_by_lang)

    # --- Trending-up keywords ---
    trending_up = _detect_trending_up(all_kw_counts, recent_kw_counts, len(papers), len(recent_papers))

    return {
        "keyword_trends": all_kw_counts.most_common(40),
        "recent_keyword_trends": recent_kw_counts.most_common(30),
        "keyword_by_language": {
            lang: [(kw, c) for kw, c in items] for lang, items in kw_by_lang.items()
        },
        "language_distribution": lang_dist,
        "yearly_counts": yearly_counts,
        "top_journals": top_journals,
        "cross_language_gaps": cross_language_gaps,
        "trending_up": trending_up,
    }


# ---------------------------------------------------------------------------
# Gap and trend detection
# ---------------------------------------------------------------------------


def _detect_cross_language_gaps(
    kw_by_lang: dict[str, list[tuple[str, int]]],
    min_count: int = 2,
) -> list[dict]:
    """Find keywords prominent in one language but absent in others.

    Returns a list of dicts:
        {"keyword": str, "present_in": [lang, ...], "absent_from": [lang, ...]}
    """
    # Build sets of keywords per language (only those with >= min_count)
    lang_kw_sets: dict[str, set[str]] = {}
    for lang, items in kw_by_lang.items():
        lang_kw_sets[lang] = {kw for kw, count in items if count >= min_count}

    all_langs = set(lang_kw_sets.keys())
    if len(all_langs) < 2:
        return []

    gaps: list[dict] = []
    seen: set[str] = set()

    for lang, kw_set in lang_kw_sets.items():
        other_langs = all_langs - {lang}
        for kw in kw_set:
            if kw in seen:
                continue
            present_in = [lang]
            absent_from = []
            for other in sorted(other_langs):
                if kw in lang_kw_sets.get(other, set()):
                    present_in.append(other)
                else:
                    absent_from.append(other)
            if absent_from:
                gaps.append(
                    {
                        "keyword": kw,
                        "present_in": sorted(present_in),
                        "absent_from": sorted(absent_from),
                    }
                )
                seen.add(kw)

    # Sort by number of languages the keyword is absent from (descending),
    # so the most striking gaps come first.
    gaps.sort(key=lambda g: len(g["absent_from"]), reverse=True)
    return gaps


def _detect_trending_up(
    all_counts: Counter,
    recent_counts: Counter,
    total_papers: int,
    recent_papers: int,
    min_recent: int = 2,
) -> list[dict]:
    """Identify keywords whose share in recent papers exceeds their overall share.

    A keyword is "trending up" if its frequency among recent papers is notably
    higher than its frequency across the full corpus.

    Returns a list of dicts:
        {"keyword": str, "recent_count": int, "total_count": int,
         "recent_share": float, "overall_share": float, "ratio": float}
    """
    if total_papers == 0 or recent_papers == 0:
        return []

    trending: list[dict] = []
    for kw, rc in recent_counts.items():
        if rc < min_recent:
            continue
        tc = all_counts.get(kw, rc)
        recent_share = rc / recent_papers
        overall_share = tc / total_papers
        if overall_share == 0:
            continue
        ratio = recent_share / overall_share
        if ratio > 1.2:  # at least 20 % over-representation in recent work
            trending.append(
                {
                    "keyword": kw,
                    "recent_count": rc,
                    "total_count": tc,
                    "recent_share": round(recent_share, 4),
                    "overall_share": round(overall_share, 4),
                    "ratio": round(ratio, 2),
                }
            )

    trending.sort(key=lambda t: t["ratio"], reverse=True)
    return trending
