"""Reference selection with Corrective RAG pattern.

Retrieves candidate references, verifies relevance, discards irrelevant ones,
and re-retrieves if the result set is insufficient. Supports reference type
classification and type-balance checking against citation profiles.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from src.knowledge_base.db import Database
from src.knowledge_base.models import ReferenceType
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter

CITATION_PROFILES_DIR = Path("config/citation_profiles")

# Mapping from LLM output strings to ReferenceType enum values
_TYPE_ALIASES: dict[str, ReferenceType] = {
    "primary_literary": ReferenceType.PRIMARY_LITERARY,
    "primary": ReferenceType.PRIMARY_LITERARY,
    "literary": ReferenceType.PRIMARY_LITERARY,
    "secondary_criticism": ReferenceType.SECONDARY_CRITICISM,
    "secondary": ReferenceType.SECONDARY_CRITICISM,
    "criticism": ReferenceType.SECONDARY_CRITICISM,
    "theory": ReferenceType.THEORY,
    "methodology": ReferenceType.METHODOLOGY,
    "method": ReferenceType.METHODOLOGY,
    "historical_context": ReferenceType.HISTORICAL_CONTEXT,
    "historical": ReferenceType.HISTORICAL_CONTEXT,
    "context": ReferenceType.HISTORICAL_CONTEXT,
    "reference_work": ReferenceType.REFERENCE_WORK,
    "reference": ReferenceType.REFERENCE_WORK,
    "self_citation": ReferenceType.SELF_CITATION,
    "self": ReferenceType.SELF_CITATION,
    "unclassified": ReferenceType.UNCLASSIFIED,
}


def _parse_ref_type(raw: str) -> ReferenceType:
    """Parse a string into a ReferenceType, tolerating LLM output variations."""
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _TYPE_ALIASES:
        return _TYPE_ALIASES[normalized]
    # Try enum value directly
    try:
        return ReferenceType(normalized)
    except ValueError:
        return ReferenceType.UNCLASSIFIED


def load_citation_profile(journal_name: str) -> Optional[dict[str, Any]]:
    """Load a citation profile YAML for the given journal.

    Looks for config/citation_profiles/<slug>.yaml where slug is the
    journal name lowercased with spaces replaced by underscores.
    """
    slug = journal_name.lower().replace(" ", "_")
    path = CITATION_PROFILES_DIR / f"{slug}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


class ReferenceSelector:
    """Selects verified, relevant references for a research plan using Corrective RAG."""

    def __init__(
        self,
        db: Database,
        vector_store: VectorStore,
        llm_router: LLMRouter,
    ):
        self.db = db
        self.vs = vector_store
        self.llm = llm_router

    async def select_references(
        self,
        research_question: str,
        thesis: str,
        target_count: int = 30,
        max_rounds: int = 3,
    ) -> list[str]:
        """Select relevant, verified references using Corrective RAG.

        Process:
        1. Retrieve top-N candidates via semantic search
        2. Judge relevance of each candidate with LLM
        3. Discard irrelevant ones
        4. If not enough, reformulate query and re-retrieve
        5. Return list of reference IDs
        """
        from src.literature_indexer.embeddings import EmbeddingModel

        embedder = EmbeddingModel()
        selected_ids: list[str] = []
        seen_ids: set[str] = set()
        query = f"{research_question} {thesis}"

        for round_num in range(max_rounds):
            # Retrieve candidates
            query_embedding = embedder.generate_embedding(query, is_query=True)
            results = self.vs.search_papers(
                query_embedding=query_embedding,
                n_results=target_count * 2,
            )

            if not results or not results.get("ids") or not results["ids"][0]:
                break

            candidate_ids = results["ids"][0]
            candidate_docs = results["documents"][0] if results.get("documents") else []
            candidate_metas = results["metadatas"][0] if results.get("metadatas") else []

            # Judge relevance for each candidate
            new_candidates = []
            for i, cid in enumerate(candidate_ids):
                # Extract paper_id from chunk id (format: paper_id_chunk_N)
                paper_id = cid.rsplit("_chunk_", 1)[0] if "_chunk_" in cid else cid
                if paper_id in seen_ids:
                    continue
                seen_ids.add(paper_id)

                doc_text = candidate_docs[i] if i < len(candidate_docs) else ""
                meta = candidate_metas[i] if i < len(candidate_metas) else {}
                new_candidates.append((paper_id, doc_text, meta))

            if not new_candidates:
                break

            # Batch relevance judgment
            relevant = await self._judge_relevance_batch(
                research_question, thesis, new_candidates
            )
            selected_ids.extend(relevant)

            if len(selected_ids) >= target_count:
                break

            # Reformulate query for next round
            if round_num < max_rounds - 1:
                query = await self._reformulate_query(
                    research_question, thesis, round_num + 1
                )

        return selected_ids[:target_count]

    async def _judge_relevance_batch(
        self,
        research_question: str,
        thesis: str,
        candidates: list[tuple[str, str, dict]],
    ) -> list[str]:
        """Judge relevance of candidate references in batch."""
        relevant_ids = []

        # Process in batches of 10
        batch_size = 10
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i : i + batch_size]
            candidate_descriptions = []
            for j, (pid, doc, meta) in enumerate(batch):
                title = meta.get("title", "Unknown")
                desc = f"[{j}] Title: {title}\nExcerpt: {doc[:500]}"
                candidate_descriptions.append(desc)

            prompt = f"""You are evaluating whether academic papers are relevant to a specific research project.

Research question: {research_question}
Thesis: {thesis}

Candidate papers:
{chr(10).join(candidate_descriptions)}

For each paper, output a JSON array of indices that ARE relevant (directly useful as a reference for this research).
Only include papers that are substantively relevant, not just superficially keyword-matching.

Output ONLY a JSON array of integers, e.g. [0, 2, 5]"""

            response = self.llm.complete(
                task_type="reference_verification",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            text = self.llm.get_response_text(response)

            try:
                # Extract JSON array from response
                import re
                match = re.search(r"\[[\d\s,]*\]", text)
                if match:
                    indices = json.loads(match.group())
                    for idx in indices:
                        if 0 <= idx < len(batch):
                            relevant_ids.append(batch[idx][0])
            except (json.JSONDecodeError, ValueError):
                # If parsing fails, include all candidates (conservative)
                relevant_ids.extend(pid for pid, _, _ in batch)

        return relevant_ids

    async def _reformulate_query(
        self, research_question: str, thesis: str, round_num: int
    ) -> str:
        """Reformulate the search query to find different relevant papers."""
        prompt = f"""The following research question needs more references found via semantic search.
Previous search rounds have been completed but more references are needed.

Research question: {research_question}
Thesis: {thesis}
Search round: {round_num + 1}

Generate a new search query that explores a DIFFERENT angle of this research topic
to find additional relevant papers. Focus on:
- Round 2: Related theoretical frameworks and methodological approaches
- Round 3: Broader context, adjacent fields, and interdisciplinary connections

Output ONLY the new search query (one line)."""

        response = self.llm.complete(
            task_type="metadata_processing",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return self.llm.get_response_text(response).strip()

    # --- Reference Type Classification ---

    async def classify_references(
        self,
        references: list[dict[str, Any]],
        manuscript_authors: Optional[list[str]] = None,
    ) -> list[tuple[str, ReferenceType]]:
        """Classify a list of references into ReferenceType categories.

        Args:
            references: List of dicts with at least 'id', 'title', 'authors',
                'year', and optionally 'journal', 'abstract'.
            manuscript_authors: Authors of the manuscript being written, used
                to detect self-citations.

        Returns:
            List of (reference_id, ReferenceType) tuples.
        """
        results: list[tuple[str, ReferenceType]] = []
        ms_author_set = {a.lower() for a in (manuscript_authors or [])}

        # Fast-path: detect self-citations by author overlap
        to_classify: list[dict[str, Any]] = []
        for ref in references:
            ref_authors = {a.lower() for a in ref.get("authors", [])}
            if ms_author_set and ref_authors & ms_author_set:
                results.append((ref["id"], ReferenceType.SELF_CITATION))
            else:
                to_classify.append(ref)

        # Batch classify the rest via LLM
        batch_size = 15
        for i in range(0, len(to_classify), batch_size):
            batch = to_classify[i : i + batch_size]
            ref_descriptions = []
            for j, ref in enumerate(batch):
                authors_str = ", ".join(ref.get("authors", [])[:3])
                desc = (
                    f"[{j}] {authors_str} ({ref.get('year', '?')}). "
                    f"\"{ref.get('title', 'Unknown')}\""
                )
                if ref.get("journal"):
                    desc += f". {ref['journal']}"
                ref_descriptions.append(desc)

            prompt = f"""Classify each reference into exactly ONE of these types:
- primary_literary: Literary works, poems, novels, testimonial texts, music scores, early modern primary sources -- objects of analysis
- secondary_criticism: Scholarly articles/monographs analyzing literary texts or traditions (philology, literary history, specialized criticism)
- theory: Philosophy, critical theory, cross-disciplinary theoretical frameworks (e.g., Derrida, Foucault, postcolonial theory)
- methodology: Works cited for their methodological contribution (e.g., quantitative metrics, oral-formulaic theory, book history methods)
- historical_context: Historical, social science, legal, political sources providing context
- reference_work: Encyclopedias, dictionaries, bibliographic tools

References:
{chr(10).join(ref_descriptions)}

Output a JSON object mapping each index to its type, e.g. {{"0": "primary_literary", "2": "theory"}}
Include ALL indices. Output ONLY the JSON object."""

            response = self.llm.complete(
                task_type="metadata_processing",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            text = self.llm.get_response_text(response)

            try:
                match = re.search(r"\{[^}]+\}", text, re.DOTALL)
                if match:
                    classifications = json.loads(match.group())
                    for idx_str, type_str in classifications.items():
                        idx = int(idx_str)
                        if 0 <= idx < len(batch):
                            ref_type = _parse_ref_type(str(type_str))
                            results.append((batch[idx]["id"], ref_type))
                    # Fill in any missing indices as UNCLASSIFIED
                    classified_indices = {int(k) for k in classifications}
                    for idx in range(len(batch)):
                        if idx not in classified_indices:
                            results.append((batch[idx]["id"], ReferenceType.UNCLASSIFIED))
                else:
                    # No JSON found -- mark all as unclassified
                    for ref in batch:
                        results.append((ref["id"], ReferenceType.UNCLASSIFIED))
            except (json.JSONDecodeError, ValueError):
                for ref in batch:
                    results.append((ref["id"], ReferenceType.UNCLASSIFIED))

        return results

    # --- Type Balance Checking ---

    @staticmethod
    def check_type_balance(
        type_counts: dict[str, int],
        citation_profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Check whether reference type distribution matches citation profile targets.

        Args:
            type_counts: Mapping of ReferenceType value -> count.
            citation_profile: Loaded citation profile dict (from YAML).

        Returns:
            List of deviation dicts, each with keys:
                'type', 'actual_pct', 'target_range', 'status' ('under'|'over'|'ok').
            Only types with deviations are included.
        """
        dist_config = citation_profile.get("reference_type_distribution", {})
        if not dist_config:
            return []

        total = sum(type_counts.values())
        if total == 0:
            return []

        deviations: list[dict[str, Any]] = []
        for type_key, type_conf in dist_config.items():
            target_range = type_conf.get("target_pct")
            if not target_range or len(target_range) != 2:
                continue

            count = type_counts.get(type_key, 0)
            actual_pct = (count / total) * 100

            low, high = target_range
            if actual_pct < low:
                deviations.append({
                    "type": type_key,
                    "count": count,
                    "actual_pct": round(actual_pct, 1),
                    "target_range": target_range,
                    "status": "under",
                })
            elif actual_pct > high:
                deviations.append({
                    "type": type_key,
                    "count": count,
                    "actual_pct": round(actual_pct, 1),
                    "target_range": target_range,
                    "status": "over",
                })

        return deviations

    @staticmethod
    def format_balance_report(
        type_counts: dict[str, int],
        deviations: list[dict[str, Any]],
    ) -> str:
        """Format a human-readable report of reference type balance."""
        total = sum(type_counts.values())
        if total == 0:
            return "No references to analyze."

        lines = [f"Reference Type Distribution ({total} total references):"]
        for type_key in [
            "primary_literary",
            "secondary_criticism",
            "theory",
            "methodology",
            "historical_context",
            "reference_work",
            "self_citation",
            "unclassified",
        ]:
            count = type_counts.get(type_key, 0)
            pct = (count / total) * 100
            lines.append(f"  {type_key}: {count} ({pct:.0f}%)")

        if deviations:
            lines.append("")
            lines.append("Deviations from citation profile targets:")
            for d in deviations:
                low, high = d["target_range"]
                if d["status"] == "under":
                    lines.append(
                        f"  WARNING: {d['type']} is UNDER target "
                        f"({d['actual_pct']}% vs {low}-{high}%)"
                    )
                else:
                    lines.append(
                        f"  WARNING: {d['type']} is OVER target "
                        f"({d['actual_pct']}% vs {low}-{high}%)"
                    )
        else:
            lines.append("")
            lines.append("All reference types within target ranges.")

        return "\n".join(lines)
