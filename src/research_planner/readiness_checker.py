"""Pre-plan readiness checker.

Predicts required primary texts and key criticism/theory for a research topic,
then checks their availability in the knowledge base BEFORE plan creation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import PaperStatus
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter
from src.research_planner.planner import _extract_title, _jaccard_word_overlap

logger = logging.getLogger(__name__)


@dataclass
class ReadinessItem:
    """A single work predicted as needed for the research topic."""

    author: str
    title: str
    category: str  # "primary" or "criticism"
    reason: str = ""
    available: bool = False


@dataclass
class ReadinessReport:
    """Result of a pre-plan readiness check."""

    query: str
    status: str = "ready"  # ready, missing_primary, insufficient_criticism, not_ready
    items: list[ReadinessItem] = field(default_factory=list)

    @property
    def missing_primary(self) -> list[ReadinessItem]:
        return [i for i in self.items if i.category == "primary" and not i.available]

    @property
    def missing_criticism(self) -> list[ReadinessItem]:
        return [i for i in self.items if i.category == "criticism" and not i.available]

    def summary(self) -> str:
        total = len(self.items)
        available = sum(1 for i in self.items if i.available)
        return (
            f"{available}/{total} works available. "
            f"Status: {self.status}. "
            f"Missing primary: {len(self.missing_primary)}, "
            f"missing criticism: {len(self.missing_criticism)}"
        )


async def check_readiness(
    query: str,
    db: Database,
    vector_store: VectorStore,
    llm_router: LLMRouter,
    session_paper_ids: list[str] | None = None,
) -> ReadinessReport:
    """Check whether the knowledge base is ready to produce a good plan.

    Steps:
      1. Gather titles of already-indexed papers (if session provided)
      2. LLM call: predict 3-8 primary texts + 5-10 key criticism/theory
      3. Check each item's availability via SQLite + ChromaDB
      4. Determine overall readiness status

    Args:
        query: The research topic or question.
        db: Database instance.
        vector_store: VectorStore instance.
        llm_router: LLM router for predictions.
        session_paper_ids: Optional list of paper IDs from a search session.

    Returns:
        ReadinessReport with status and item-level availability.
    """
    # Step 1: gather available paper titles for context
    available_titles: list[str] = []
    if session_paper_ids:
        for pid in session_paper_ids[:50]:
            paper = db.get_paper(pid)
            if paper and paper.title:
                available_titles.append(paper.title)

    # Step 2: LLM prediction
    items = await _predict_needed_works(query, available_titles, llm_router)

    if not items:
        return ReadinessReport(query=query, status="ready")

    # Step 3: check availability for each item
    for item in items:
        item.available = _check_availability(item, db, vector_store)

    # Step 4: determine status
    status = _determine_status(items)

    return ReadinessReport(query=query, status=status, items=items)


async def _predict_needed_works(
    query: str,
    available_titles: list[str],
    llm_router: LLMRouter,
) -> list[ReadinessItem]:
    """Use LLM to predict primary texts and key criticism needed for the topic."""
    titles_context = ""
    if available_titles:
        titles_str = "\n".join(f"  - {t}" for t in available_titles[:30])
        titles_context = f"\n\nAlready available in the knowledge base:\n{titles_str}"

    prompt = f"""You are a comparative literature research librarian. Given a research topic,
predict the essential works that a scholar would need access to.

Research topic: {query}
{titles_context}

Return a JSON array of objects, each with:
- "author": author name (e.g. "Walter Benjamin")
- "title": work title (e.g. "The Task of the Translator")
- "category": either "primary" (literary texts being analyzed) or "criticism" (secondary criticism, theory, methodology)
- "reason": brief explanation of why this work is needed (1 sentence)

Requirements:
- List 3-8 PRIMARY literary texts that would be directly analyzed
- List 5-10 key CRITICISM/THEORY works (canonical theory, essential secondary sources)
- Focus on works that are truly essential, not exhaustive lists
- For criticism, prioritize canonical/foundational works over recent articles

Respond with ONLY the JSON array, no other text."""

    try:
        response = llm_router.complete(
            task_type="metadata_processing",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        text = llm_router.get_response_text(response).strip()

        # Extract JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            logger.warning("LLM response did not contain a JSON array")
            return []

        data = json.loads(match.group())
        items = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            author = entry.get("author", "").strip()
            title = entry.get("title", "").strip()
            if not title:
                continue
            items.append(ReadinessItem(
                author=author,
                title=title,
                category=entry.get("category", "criticism").strip().lower(),
                reason=entry.get("reason", ""),
            ))
        return items
    except Exception:
        logger.warning("Failed to predict needed works", exc_info=True)
        return []


def _check_availability(
    item: ReadinessItem,
    db: Database,
    vector_store: VectorStore,
) -> bool:
    """Check if a work is available in the knowledge base.

    Tier 1: SQLite LIKE search by title
    Tier 2: ChromaDB semantic search with Jaccard validation
    """
    title = _extract_title(f"{item.author}, {item.title}" if item.author else item.title)
    if not title:
        title = item.title

    # Tier 1: SQLite search
    papers = db.search_papers_by_title(title, limit=5)
    for p in papers:
        if p.status in (PaperStatus.INDEXED, PaperStatus.ANALYZED):
            return True

    # Also check references table for criticism
    if item.category == "criticism":
        refs = db.search_references_by_title(title, limit=5)
        if refs:
            return True

    # Tier 2: ChromaDB semantic search
    try:
        from src.literature_indexer.embeddings import get_embedding

        search_text = f"{item.author} {item.title}" if item.author else item.title
        embedding = get_embedding(search_text)
        results = vector_store.search_papers(embedding, n_results=3)
        if results and results.get("metadatas") and results["metadatas"][0]:
            for i, meta in enumerate(results["metadatas"][0]):
                paper_id = meta.get("paper_id", "")
                if paper_id:
                    paper = db.get_paper(paper_id)
                    if paper and paper.status in (PaperStatus.INDEXED, PaperStatus.ANALYZED):
                        paper_title = paper.title or ""
                        if _jaccard_word_overlap(title, paper_title) > 0.5:
                            return True
    except Exception:
        logger.debug("ChromaDB search failed for '%s', skipping Tier 2", title)

    return False


def _determine_status(items: list[ReadinessItem]) -> str:
    """Determine overall readiness status from item availability."""
    primary = [i for i in items if i.category == "primary"]
    criticism = [i for i in items if i.category == "criticism"]

    primary_available = sum(1 for i in primary if i.available)
    criticism_available = sum(1 for i in criticism if i.available)

    has_missing_primary = len(primary) > 0 and primary_available < len(primary)
    criticism_ratio = criticism_available / len(criticism) if criticism else 1.0

    if has_missing_primary and criticism_ratio < 0.3:
        return "not_ready"
    elif has_missing_primary:
        return "missing_primary"
    elif criticism_ratio < 0.5:
        return "insufficient_criticism"
    else:
        return "ready"
