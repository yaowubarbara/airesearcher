"""Stub source for CNKI (China National Knowledge Infrastructure).

CNKI does not offer a free public API. Accessing CNKI programmatically requires
institutional credentials and typically involves either:
  - An institutional CNKI API subscription
  - Web scraping (against CNKI's terms of service)
  - The CNKI Open API (limited availability, requires application)

This module provides the interface stub so the rest of the monitor can call it
uniformly, but it returns an empty list until proper authentication is configured.
"""

from __future__ import annotations

import logging
from typing import Any

from src.knowledge_base.models import Paper

logger = logging.getLogger(__name__)


async def fetch_recent_papers(
    journal_config: dict[str, Any],
    since_date: str,
) -> list[Paper]:
    """Fetch recent papers from CNKI for a Chinese journal.

    TODO: Implement CNKI integration once API access is available.
          Required steps:
          1. Obtain CNKI Open API credentials (institutional subscription).
          2. Implement OAuth or session-based authentication.
          3. Map cnki_journal_code to CNKI's internal source identifiers.
          4. Parse CNKI's response format into Paper objects.
          5. Handle Chinese metadata (author names, abstracts) properly.

    Args:
        journal_config: Journal configuration dict from journals.yaml.
            Expected keys: cnki_journal_code, name, language.
        since_date: ISO date string (YYYY-MM-DD) for the earliest publication date.

    Returns:
        Empty list (not yet implemented).
    """
    journal_code = journal_config.get("cnki_journal_code")
    if not journal_code:
        return []

    logger.info(
        "CNKI source not yet implemented. Skipping %s (code=%s)",
        journal_config.get("name", "unknown"),
        journal_code,
    )
    return []
