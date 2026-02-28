"""P-ontology annotation of academic papers using domain-specific schemas.

Annotates papers with structured metadata (problématique, approach, etc.)
driven by domain-specific prompt templates.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.domain_config import get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.db import Database
    from src.knowledge_base.models import Annotation, Paper
    from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


async def annotate_corpus(
    papers: list[Paper],
    llm_router: LLMRouter,
    db: Database,
    *,
    domain_id: str = "comparative_literature",
) -> list[Annotation]:
    """Annotate a corpus of papers using domain-specific P-ontology.

    Args:
        papers: Papers to annotate.
        llm_router: LLM router for making API calls.
        db: Database for storing/retrieving annotations.
        domain_id: Research domain identifier.

    Returns:
        List of annotations (both existing and newly created).
    """
    domain = get_domain_config(domain_id)
    prompt_template = domain.load_prompt("annotation.md")

    annotations = []
    for paper in papers:
        existing = db.get_annotation(paper.id)
        if existing:
            annotations.append(existing)
            continue

        prompt = prompt_template.format(
            title=paper.title or "",
            authors=paper.authors or "",
            abstract=paper.abstract or "",
            text=(paper.full_text or "")[:4000],
        )

        try:
            response = await llm_router.call(
                task="annotate",
                prompt=prompt,
                temperature=0.2,
            )
            data = json.loads(response)
            annotation = db.create_annotation(paper_id=paper.id, data=data)
            annotations.append(annotation)
            logger.info("Annotated paper: %s", paper.title)
        except Exception as e:
            logger.warning("Failed to annotate %s: %s", paper.id, e)

    return annotations
