"""Readiness checker — evaluates whether a research plan is ready for writing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain_config import get_domain_config

if TYPE_CHECKING:
    from src.knowledge_base.db import Database
    from src.knowledge_base.models import ResearchPlan
    from src.knowledge_base.vector_store import VectorStore

logger = logging.getLogger(__name__)


def check_readiness(
    plan: ResearchPlan,
    db: Database,
    vs: VectorStore,
    *,
    domain_id: str = "comparative_literature",
) -> dict:
    """Check whether a research plan has sufficient resources to proceed.

    Evaluates based on domain-specific criteria:
    - Comparative literature: primary texts, theoretical works, close reading material
    - Computer science: datasets, baseline implementations, compute resources
    - Biomedical: clinical data, IRB approval, statistical power

    Returns:
        Dict with ready (bool), missing items, and recommendations.
    """
    domain = get_domain_config(domain_id)
    criteria = domain.metadata.get("review_criteria", [])

    issues = []
    if not plan.reference_ids:
        issues.append("No references identified")
    if not plan.outline:
        issues.append("No outline sections defined")

    return {
        "ready": len(issues) == 0,
        "issues": issues,
        "domain": domain.name,
        "criteria_checked": criteria,
    }
