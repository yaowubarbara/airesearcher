"""Journal listing and profile endpoints."""
import yaml
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(tags=["journals"])

JOURNALS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "journals.yaml"
PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "journal_profiles"

ACTIVE_JOURNALS = {"Comparative Literature"}


@router.get("/journals")
async def list_journals():
    with open(JOURNALS_PATH) as f:
        data = yaml.safe_load(f)
    journals = []
    for j in data.get("journals", []):
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
async def get_journal_profile(name: str):
    if name not in ACTIVE_JOURNALS:
        return {"error": "Journal not active", "is_active": False}
    # Try to load profile
    slug = name.lower().replace(" ", "_")
    profile_path = PROFILES_DIR / f"{slug}.yaml"
    if profile_path.exists():
        with open(profile_path) as f:
            profile = yaml.safe_load(f)
        return {"name": name, "is_active": True, "profile": profile}
    return {"name": name, "is_active": True, "profile": None}
