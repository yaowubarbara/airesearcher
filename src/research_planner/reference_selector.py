"""Reference selection with Corrective RAG pattern.

Retrieves candidate references, verifies relevance, discards irrelevant ones,
and re-retrieves if the result set is insufficient.
"""

from __future__ import annotations

import json
from typing import Optional

from src.knowledge_base.db import Database
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter


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
