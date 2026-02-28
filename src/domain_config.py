"""Domain configuration loader — the core of multi-domain support.

Usage:
    from src.domain_config import get_domain_config, list_domains

    domain = get_domain_config("computer_science")
    prompt = domain.load_prompt("annotation.md")
    journals = domain.load_config("journals.yaml")
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DOMAINS_DIR = PROJECT_ROOT / "config" / "domains"
PROMPTS_DOMAINS_DIR = PROJECT_ROOT / "prompts" / "domains"

DEFAULT_DOMAIN = "comparative_literature"


@dataclass
class DomainConfig:
    """Loaded configuration for a research domain."""

    domain_id: str
    name: str
    persona: str
    analysis_method: str
    description: str = ""
    annotation_schema: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    # Internal paths
    _config_dir: Path = field(default=Path("."), repr=False)
    _prompts_dir: Path = field(default=Path("."), repr=False)

    def load_prompt(self, prompt_name: str) -> str:
        """Load a prompt template file for this domain.

        Args:
            prompt_name: filename relative to prompts/domains/<domain>/
                         e.g. "annotation.md" or "writing/introduction.md"

        Returns:
            Prompt text content.

        Raises:
            FileNotFoundError: if prompt file does not exist.
        """
        path = self._prompts_dir / prompt_name
        if not path.exists():
            raise FileNotFoundError(
                f"Prompt '{prompt_name}' not found for domain '{self.domain_id}' "
                f"(looked at {path})"
            )
        return path.read_text(encoding="utf-8")

    def load_config(self, config_name: str) -> Any:
        """Load a YAML config file for this domain.

        Args:
            config_name: filename relative to config/domains/<domain>/
                         e.g. "journals.yaml"

        Returns:
            Parsed YAML data.
        """
        path = self._config_dir / config_name
        if not path.exists():
            raise FileNotFoundError(
                f"Config '{config_name}' not found for domain '{self.domain_id}' "
                f"(looked at {path})"
            )
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def list_journal_profiles(self) -> list[Path]:
        """Return paths to all journal profile YAML files."""
        profiles_dir = self._config_dir / "journal_profiles"
        if not profiles_dir.exists():
            return []
        return sorted(profiles_dir.glob("*.yaml"))

    def list_reviewer_profiles(self) -> list[Path]:
        """Return paths to all reviewer profile YAML files."""
        profiles_dir = self._config_dir / "reviewer_profiles"
        if not profiles_dir.exists():
            return []
        return sorted(profiles_dir.glob("*.yaml"))

    def get_journals(self) -> list[dict]:
        """Load and return the journal list for this domain."""
        data = self.load_config("journals.yaml")
        return data.get("journals", [])


@lru_cache(maxsize=8)
def get_domain_config(domain_id: str = DEFAULT_DOMAIN) -> DomainConfig:
    """Load and return configuration for a research domain.

    Args:
        domain_id: domain identifier, e.g. "comparative_literature",
                   "computer_science", "biomedical"

    Returns:
        DomainConfig instance.

    Raises:
        ValueError: if domain_id is not found.
    """
    config_dir = CONFIG_DOMAINS_DIR / domain_id
    prompts_dir = PROMPTS_DOMAINS_DIR / domain_id

    domain_yaml_path = config_dir / "domain.yaml"
    if not domain_yaml_path.exists():
        available = list_domains()
        raise ValueError(
            f"Domain '{domain_id}' not found. "
            f"Available domains: {available}"
        )

    with open(domain_yaml_path, encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    return DomainConfig(
        domain_id=domain_id,
        name=meta.get("name", domain_id),
        persona=meta.get("persona", "senior researcher"),
        analysis_method=meta.get("analysis_method", "critical analysis"),
        description=meta.get("description", ""),
        annotation_schema=meta.get("annotation_schema", {}),
        metadata=meta,
        _config_dir=config_dir,
        _prompts_dir=prompts_dir,
    )


def list_domains() -> list[str]:
    """Return list of available domain identifiers."""
    if not CONFIG_DOMAINS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in CONFIG_DOMAINS_DIR.iterdir()
        if d.is_dir() and (d / "domain.yaml").exists()
    )
