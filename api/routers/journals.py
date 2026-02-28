"""Journal listing and profile endpoints — domain-aware."""
import sys
import yaml
from pathlib import Path
from fastapi import APIRouter, Query

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain_config import get_domain_config, DEFAULT_DOMAIN

router = APIRouter(tags=["journals"])

ACTIVE_JOURNALS = {"Comparative Literature"}


@router.get("/journals")
async def list_journals(domain: str = Query(DEFAULT_DOMAIN, description="Research domain")):
    """List journals for the specified domain."""
    domain_config = get_domain_config(domain)
    raw_journals = domain_config.get_journals()

    journals = []
    for j in raw_journals:
        journals.append({
            "name": j["name"],
            "publisher": j.get("publisher", ""),
            "language": j.get("language", "en"),
            "citation_style": j.get("citation_style", ""),
            "scope": j.get("scope", ""),
            "issn": j.get("issn", ""),
            "is_active": j["name"] in ACTIVE_JOURNALS,
        })
    return {"journals": journals}


@router.get("/journals/{name}/profile")
async def get_journal_profile(name: str, domain: str = Query(DEFAULT_DOMAIN)):
    """Get journal profile for a specific journal."""
    domain_config = get_domain_config(domain)

    # Try to load profile from domain-specific directory
    slug = name.lower().replace(" ", "_")
    profiles = domain_config.list_journal_profiles()
    for p in profiles:
        if p.stem == slug:
            with open(p) as f:
                profile = yaml.safe_load(f)
            return {"name": name, "is_active": True, "profile": profile}

    return {"name": name, "is_active": name in ACTIVE_JOURNALS, "profile": None}
