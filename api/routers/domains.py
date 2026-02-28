"""Domain listing endpoint."""
import sys
from pathlib import Path
from fastapi import APIRouter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain_config import get_domain_config, list_domains

router = APIRouter(tags=["domains"])


@router.get("/domains")
async def get_domains():
    """Return available research domains with metadata."""
    domains = []
    for domain_id in list_domains():
        config = get_domain_config(domain_id)
        journals = config.get_journals()
        domains.append({
            "domain_id": config.domain_id,
            "name": config.name,
            "description": config.description,
            "icon": config.metadata.get("icon", "search"),
            "color": config.metadata.get("color", "#6366f1"),
            "journal_count": len(journals),
        })
    return {"domains": domains}
