"""Writing agent implementing Self-Refine iterative drafting."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Optional

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    Language,
    Manuscript,
    OutlineSection,
    ResearchPlan,
)
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter
from src.writing_agent.citation_manager import CitationManager
from src.writing_agent.close_reader import CloseReader


_MAX_REFINE_ITERATIONS = 3
_MIN_ACCEPTABLE_SCORE = 3


class WritingAgent:
    """Generates academic manuscript sections through Self-Refine iteration.

    The Self-Refine loop works as follows:
      1. Generate an initial draft for a section.
      2. A critic evaluates the draft on three axes (1-5 each):
         close_reading_depth, argument_logic, citation_density.
      3. If any axis scores below the minimum threshold, the critic produces
         specific revision instructions and the draft is revised.
      4. Steps 2-3 repeat for up to ``_MAX_REFINE_ITERATIONS`` rounds.

    Reflexion memories from prior writing attempts are injected into the
    system prompt so the agent learns from past feedback.
    """

    def __init__(
        self,
        db: Database,
        vector_store: VectorStore,
        llm_router: LLMRouter,
    ) -> None:
        self.db = db
        self.vector_store = vector_store
        self.llm_router = llm_router
        self.citation_manager = CitationManager()
        self.close_reader = CloseReader()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def write_section(
        self,
        section: OutlineSection,
        plan: ResearchPlan,
        reflexion_memories: list[str],
    ) -> str:
        """Write a single section of the manuscript using Self-Refine.

        Args:
            section: The outline section to write.
            plan: The full research plan (provides thesis, references, etc.).
            reflexion_memories: Past lessons/feedback to inject into the prompt.

        Returns:
            The final refined section text.
        """
        # --- Step 1: Generate initial draft ----------------------------- #
        draft = await self._generate_initial_draft(section, plan, reflexion_memories)

        # --- Step 2-3: Self-Refine loop --------------------------------- #
        for iteration in range(1, _MAX_REFINE_ITERATIONS + 1):
            scores, revision_instructions = await self._critic_evaluate(
                draft, section, plan
            )

            # Check if all scores meet the threshold
            if all(score >= _MIN_ACCEPTABLE_SCORE for score in scores.values()):
                break

            # Revise draft based on critic feedback
            draft = await self._revise_draft(
                draft, revision_instructions, section, plan, reflexion_memories
            )

        return draft

    async def write_full_manuscript(self, plan: ResearchPlan) -> Manuscript:
        """Write the complete manuscript by composing all sections.

        Args:
            plan: The research plan containing outline sections.

        Returns:
            A fully assembled Manuscript object.
        """
        reflexion_memories = self._load_reflexion_memories(plan)

        sections: dict[str, str] = {}
        all_text_parts: list[str] = []

        for section in plan.outline:
            section_text = await self.write_section(section, plan, reflexion_memories)
            sections[section.title] = section_text
            all_text_parts.append(f"## {section.title}\n\n{section_text}")

        full_text = "\n\n".join(all_text_parts)

        # Generate abstract
        abstract = await self._generate_abstract(full_text, plan)

        manuscript = Manuscript(
            id=str(uuid.uuid4()),
            plan_id=plan.id or "",
            title=plan.thesis_statement,
            target_journal=plan.target_journal,
            language=plan.target_language,
            sections=sections,
            full_text=full_text,
            abstract=abstract,
            reference_ids=plan.reference_ids,
            word_count=len(full_text.split()),
            version=1,
            status="drafting",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Persist
        self.db.insert_manuscript(manuscript)

        return manuscript

    # ------------------------------------------------------------------ #
    #  Private: reference context retrieval from ChromaDB
    # ------------------------------------------------------------------ #

    def _retrieve_reference_context(
        self,
        section: OutlineSection,
        plan: ResearchPlan,
    ) -> str:
        """Retrieve relevant passages from ChromaDB for grounded writing.

        Uses section argument + thesis as a query to find the most relevant
        indexed paper chunks, then formats them with author/year citations.
        """
        try:
            from src.literature_indexer.embeddings import EmbeddingModel
            embed_model = EmbeddingModel()

            query_text = f"{section.argument} {plan.thesis_statement}"
            query_embedding = embed_model.generate_embedding(query_text, is_query=True)

            results = self.vector_store.search_papers(
                query_embedding=query_embedding,
                n_results=10,
            )

            if not results or not results.get("documents"):
                return ""

            documents = results["documents"][0] if results["documents"] else []
            metadatas = results["metadatas"][0] if results.get("metadatas") else []

            if not documents:
                return ""

            context_parts: list[str] = []
            for i, (doc, meta) in enumerate(zip(documents, metadatas)):
                paper_id = meta.get("paper_id", "")
                citation = ""
                if paper_id and self.db:
                    paper = self.db.get_paper(paper_id)
                    if paper:
                        first_author = paper.authors[0].split()[-1] if paper.authors else "Unknown"
                        citation = f"({first_author}, {paper.year})"

                context_parts.append(
                    f"[Source {i+1}] {citation}\n{doc[:500]}"
                )

            return (
                "\n\nREFERENCE CONTEXT (real passages from indexed papers — "
                "cite these when making claims):\n"
                + "\n---\n".join(context_parts)
            )
        except Exception:
            # If embedding API unavailable, return empty
            return ""

    # ------------------------------------------------------------------ #
    #  Private: initial draft generation
    # ------------------------------------------------------------------ #

    async def _generate_initial_draft(
        self,
        section: OutlineSection,
        plan: ResearchPlan,
        reflexion_memories: list[str],
    ) -> str:
        """Produce the first draft of a section."""
        system_prompt = self._build_system_prompt(plan, reflexion_memories)

        # If the section has passages to analyze, perform close reading first
        close_reading_analyses: list[str] = []
        for passage in section.passages_to_analyze:
            analysis = await self.close_reader.perform_close_reading(
                passage=passage,
                context={
                    "work_title": ", ".join(section.primary_texts) if section.primary_texts else "",
                    "author": "",
                    "page": "",
                    "surrounding_text": "",
                    "thesis": plan.thesis_statement,
                },
                language=plan.target_language.value,
                llm_router=self.llm_router,
            )
            close_reading_analyses.append(analysis)

        close_reading_block = ""
        if close_reading_analyses:
            close_reading_block = (
                "\n\nCLOSE READING ANALYSES (incorporate these into your writing):\n"
                + "\n---\n".join(close_reading_analyses)
            )

        # Retrieve real reference context from ChromaDB
        reference_context = self._retrieve_reference_context(section, plan)

        user_prompt = (
            f"Write the section titled \"{section.title}\" for an academic paper.\n\n"
            f"SECTION ARGUMENT: {section.argument}\n"
            f"ESTIMATED WORD COUNT: {section.estimated_words}\n"
            f"PRIMARY TEXTS: {', '.join(section.primary_texts)}\n"
            f"SECONDARY SOURCES: {', '.join(section.secondary_sources)}\n"
            f"{close_reading_block}"
            f"{reference_context}\n\n"
            f"Write publication-ready academic prose. Include parenthetical citations "
            f"for all claims drawn from sources. Integrate close readings of primary "
            f"texts where appropriate. The writing should advance the thesis: "
            f"\"{plan.thesis_statement}\""
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = self.llm_router.complete(
            task_type="writing",
            messages=messages,
        )
        return self.llm_router.get_response_text(response)

    # ------------------------------------------------------------------ #
    #  Private: Self-Refine critic
    # ------------------------------------------------------------------ #

    async def _critic_evaluate(
        self,
        draft: str,
        section: OutlineSection,
        plan: ResearchPlan,
    ) -> tuple[dict[str, int], str]:
        """Have the critic evaluate the draft and produce revision instructions.

        Returns:
            A tuple of (scores_dict, revision_instructions_string).
            scores_dict keys: close_reading_depth, argument_logic, citation_density.
        """
        system_prompt = (
            "You are a rigorous academic peer reviewer. Evaluate the following "
            "draft section and provide scores and revision instructions.\n\n"
            "You MUST respond in valid JSON with exactly this structure:\n"
            "{\n"
            "  \"close_reading_depth\": <int 1-5>,\n"
            "  \"argument_logic\": <int 1-5>,\n"
            "  \"citation_density\": <int 1-5>,\n"
            "  \"revision_instructions\": \"<detailed instructions if any score < 3, "
            "else empty string>\"\n"
            "}"
        )

        user_prompt = (
            f"Evaluate this draft section for a paper with the thesis:\n"
            f"\"{plan.thesis_statement}\"\n\n"
            f"SECTION TITLE: {section.title}\n"
            f"SECTION ARGUMENT: {section.argument}\n\n"
            f"DRAFT:\n\"\"\"\n{draft}\n\"\"\"\n\n"
            f"Score each dimension from 1 (very poor) to 5 (excellent):\n"
            f"- close_reading_depth: How deeply does the draft engage with the "
            f"  language, imagery, and structure of primary texts?\n"
            f"- argument_logic: How well-structured, coherent, and persuasive "
            f"  is the argument?\n"
            f"- citation_density: Are claims adequately supported by citations "
            f"  to primary and secondary sources?\n\n"
            f"If ANY score is below 3, provide specific, actionable revision "
            f"instructions explaining exactly what needs improvement and how."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = self.llm_router.complete(
            task_type="critique",
            messages=messages,
            temperature=0.2,
        )
        raw = self.llm_router.get_response_text(response)

        # Parse JSON response
        scores, instructions = _parse_critic_response(raw)
        return scores, instructions

    # ------------------------------------------------------------------ #
    #  Private: revision
    # ------------------------------------------------------------------ #

    async def _revise_draft(
        self,
        draft: str,
        revision_instructions: str,
        section: OutlineSection,
        plan: ResearchPlan,
        reflexion_memories: list[str],
    ) -> str:
        """Revise a draft based on critic feedback."""
        system_prompt = self._build_system_prompt(plan, reflexion_memories)

        # Retrieve reference context for grounding revisions
        reference_context = self._retrieve_reference_context(section, plan)

        user_prompt = (
            f"Revise the following draft section based on the reviewer's feedback.\n\n"
            f"SECTION TITLE: {section.title}\n"
            f"SECTION ARGUMENT: {section.argument}\n"
            f"THESIS: {plan.thesis_statement}\n\n"
            f"CURRENT DRAFT:\n\"\"\"\n{draft}\n\"\"\"\n\n"
            f"REVIEWER FEEDBACK AND REVISION INSTRUCTIONS:\n"
            f"{revision_instructions}"
            f"{reference_context}\n\n"
            f"Produce the complete revised section. Maintain all existing strengths "
            f"while addressing every point raised by the reviewer. Do NOT include "
            f"meta-commentary about revisions; output only the revised section text."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = self.llm_router.complete(
            task_type="writing",
            messages=messages,
        )
        return self.llm_router.get_response_text(response)

    # ------------------------------------------------------------------ #
    #  Private: abstract generation
    # ------------------------------------------------------------------ #

    async def _generate_abstract(self, full_text: str, plan: ResearchPlan) -> str:
        """Generate an abstract for the completed manuscript."""
        language_name = {
            Language.EN: "English",
            Language.ZH: "Chinese",
            Language.FR: "French",
        }.get(plan.target_language, "English")

        system_prompt = (
            "You are an expert academic writer. Generate a concise abstract "
            f"for the following research paper. Write in {language_name}."
        )

        user_prompt = (
            f"THESIS: {plan.thesis_statement}\n"
            f"TARGET JOURNAL: {plan.target_journal}\n\n"
            f"FULL MANUSCRIPT TEXT:\n\"\"\"\n{full_text}\n\"\"\"\n\n"
            f"Write an abstract of 150-250 words summarizing the argument, "
            f"methodology, key findings, and contribution of this paper."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = self.llm_router.complete(
            task_type="writing",
            messages=messages,
            max_tokens=500,
        )
        return self.llm_router.get_response_text(response)

    # ------------------------------------------------------------------ #
    #  Private: helpers
    # ------------------------------------------------------------------ #

    def _build_system_prompt(
        self,
        plan: ResearchPlan,
        reflexion_memories: list[str],
    ) -> str:
        """Build the system prompt, injecting reflexion memories."""
        language_name = {
            Language.EN: "English",
            Language.ZH: "Chinese",
            Language.FR: "French",
        }.get(plan.target_language, "English")

        prompt = (
            f"You are an expert academic writer composing a research paper for "
            f"*{plan.target_journal}*. Write in {language_name}.\n\n"
            f"THESIS: {plan.thesis_statement}\n\n"
            f"Guidelines:\n"
            f"- Write publication-ready academic prose.\n"
            f"- Integrate close readings of primary texts with theoretical argument.\n"
            f"- Include parenthetical citations for every claim from a source.\n"
            f"- Use sophisticated but clear academic diction.\n"
            f"- Maintain a coherent argumentative thread throughout."
        )

        if reflexion_memories:
            memory_block = "\n".join(f"- {m}" for m in reflexion_memories)
            prompt += (
                f"\n\nLESSONS FROM PAST EXPERIENCE (apply these):\n{memory_block}"
            )

        return prompt

    def _load_reflexion_memories(self, plan: ResearchPlan) -> list[str]:
        """Load reflexion memories from the database if available."""
        try:
            rows = self.db.conn.execute(
                "SELECT observation FROM reflexion_entries ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            return [row["observation"] for row in rows]
        except Exception:
            return []


# ====================================================================== #
#  Module-level helpers
# ====================================================================== #


def _parse_critic_response(raw: str) -> tuple[dict[str, int], str]:
    """Parse the JSON response from the critic LLM.

    Returns:
        (scores_dict, revision_instructions)
    """
    default_scores = {
        "close_reading_depth": 1,
        "argument_logic": 1,
        "citation_density": 1,
    }

    # Try to extract JSON from the response (may be wrapped in markdown fences)
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return default_scores, "Could not parse critic response. Please revise for depth, logic, and citations."

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return default_scores, "Could not parse critic response. Please revise for depth, logic, and citations."

    scores = {
        "close_reading_depth": int(data.get("close_reading_depth", 1)),
        "argument_logic": int(data.get("argument_logic", 1)),
        "citation_density": int(data.get("citation_density", 1)),
    }

    instructions = data.get("revision_instructions", "")
    return scores, instructions
