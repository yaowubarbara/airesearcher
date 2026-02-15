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
    ReferenceType,
    ResearchPlan,
)
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter
from src.writing_agent.citation_manager import CitationManager
from src.writing_agent.close_reader import CloseReader


_MAX_REFINE_ITERATIONS = 3
_MIN_ACCEPTABLE_SCORE = 3

# Reference types grouped by injection strategy
_PRIMARY_TYPES = {ReferenceType.PRIMARY_LITERARY}
_SECONDARY_TYPES = {ReferenceType.SECONDARY_CRITICISM, ReferenceType.HISTORICAL_CONTEXT,
                    ReferenceType.METHODOLOGY, ReferenceType.REFERENCE_WORK,
                    ReferenceType.SELF_CITATION}
_THEORY_TYPES = {ReferenceType.THEORY}


class WritingAgent:
    """Generates academic manuscript sections through Self-Refine iteration.

    The Self-Refine loop works as follows:
      1. Generate an initial draft for a section.
      2. A critic evaluates the draft on five axes (1-5 each):
         close_reading_depth, argument_logic, citation_density,
         citation_sophistication, quote_paraphrase_ratio.
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
        """Retrieve relevant passages from ChromaDB, grouped by reference type.

        Uses section argument + thesis as a query to find the most relevant
        indexed paper chunks, then groups them into PRIMARY TEXTS, SECONDARY
        CRITICISM, and THEORY with differentiated injection instructions.
        """
        try:
            from src.literature_indexer.embeddings import EmbeddingModel
            embed_model = EmbeddingModel()

            query_text = f"{section.argument} {plan.thesis_statement}"
            query_embedding = embed_model.generate_embedding(query_text, is_query=True)

            results = self.vector_store.search_papers(
                query_embedding=query_embedding,
                n_results=15,
            )

            if not results or not results.get("documents"):
                return ""

            documents = results["documents"][0] if results["documents"] else []
            metadatas = results["metadatas"][0] if results.get("metadatas") else []

            if not documents:
                return ""

            # Classify retrieved passages by reference type
            primary_parts: list[str] = []
            secondary_parts: list[str] = []
            theory_parts: list[str] = []
            unclassified_parts: list[str] = []

            for i, (doc, meta) in enumerate(zip(documents, metadatas)):
                paper_id = meta.get("paper_id", "")
                citation = ""
                ref_type = ReferenceType.UNCLASSIFIED

                if paper_id and self.db:
                    paper = self.db.get_paper(paper_id)
                    if paper:
                        first_author = paper.authors[0].split()[-1] if paper.authors else "Unknown"
                        citation = f"({first_author}, {paper.year})"

                    # Look up ref_type from references_ table
                    try:
                        row = self.db.conn.execute(
                            "SELECT ref_type FROM references_ WHERE paper_id = ? LIMIT 1",
                            (paper_id,)
                        ).fetchone()
                        if row and row["ref_type"]:
                            try:
                                ref_type = ReferenceType(row["ref_type"])
                            except ValueError:
                                pass
                    except Exception:
                        pass

                entry = f"[Source {i+1}] {citation}\n{doc[:500]}"

                if ref_type in _PRIMARY_TYPES:
                    primary_parts.append(entry)
                elif ref_type in _THEORY_TYPES:
                    theory_parts.append(entry)
                elif ref_type in _SECONDARY_TYPES:
                    secondary_parts.append(entry)
                else:
                    unclassified_parts.append(entry)

            blocks: list[str] = []

            if primary_parts:
                blocks.append(
                    "PRIMARY LITERARY TEXTS (ALWAYS quote directly -- the reader "
                    "must see the actual words; use block quotes for passages you "
                    "will close-read; provide original language + translation for "
                    "non-English texts):\n"
                    + "\n---\n".join(primary_parts)
                )

            if theory_parts:
                blocks.append(
                    "THEORETICAL SOURCES (quote key formulations where precise "
                    "language matters philosophically; paraphrase general arguments; "
                    "deploy surgically for specific concepts, not exhaustive exegesis):\n"
                    + "\n---\n".join(theory_parts)
                )

            if secondary_parts:
                blocks.append(
                    "SECONDARY CRITICISM (mostly paraphrase; quote only memorable "
                    "formulations and specific claims you intend to analyze or "
                    "contest; engage with arguments, don't just name-drop):\n"
                    + "\n---\n".join(secondary_parts)
                )

            if unclassified_parts:
                blocks.append(
                    "ADDITIONAL SOURCES (cite when making claims):\n"
                    + "\n---\n".join(unclassified_parts)
                )

            if not blocks:
                return ""

            return (
                "\n\nREFERENCE CONTEXT (real passages from indexed papers):\n\n"
                + "\n\n".join(blocks)
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
            f"MINIMUM WORD COUNT: {section.estimated_words} words. This is a HARD "
            f"MINIMUM — your section MUST reach this length. Academic journals expect "
            f"sustained, detailed argumentation. A section of {section.estimated_words} "
            f"words means approximately {section.estimated_words // 250} double-spaced "
            f"pages of dense scholarly prose. Do NOT summarize or abbreviate. Develop "
            f"every point with evidence, close reading, and scholarly engagement.\n"
            f"PRIMARY TEXTS: {', '.join(section.primary_texts)}\n"
            f"SECONDARY SOURCES: {', '.join(section.secondary_sources)}\n"
            f"{close_reading_block}"
            f"{reference_context}\n\n"
            f"Write publication-ready academic prose at the level of *Comparative "
            f"Literature* or *New Literary History*. Requirements:\n"
            f"1. Include parenthetical citations (Author Page) for ALL claims drawn "
            f"from sources — aim for 3-5 citations per page (250 words).\n"
            f"2. Directly QUOTE primary literary texts — the reader must see the actual "
            f"words. Use block quotes (indented, 35+ words) for passages you close-read.\n"
            f"3. For non-English primary texts, quote in the ORIGINAL LANGUAGE first, "
            f"then provide English translation.\n"
            f"4. PARAPHRASE secondary criticism with selective quotation of key "
            f"formulations. Engage with arguments, don't just name-drop.\n"
            f"5. Quote theoretical sources surgically for precise concepts and terms.\n"
            f"6. Vary citation verbs: writes, argues, notes, observes, contends, insists, "
            f"suggests, points out, cautions, declares.\n"
            f"7. Every paragraph must advance the argument with evidence. No filler, "
            f"no padding, but FULL development of each point.\n\n"
            f"The writing should advance the thesis: \"{plan.thesis_statement}\""
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
            scores_dict keys: close_reading_depth, argument_logic,
            citation_density, citation_sophistication, quote_paraphrase_ratio.
        """
        system_prompt = (
            "You are a rigorous academic peer reviewer specializing in comparative "
            "literature. Evaluate the following draft section and provide scores "
            "and revision instructions.\n\n"
            "You MUST respond in valid JSON with exactly this structure:\n"
            "{\n"
            "  \"close_reading_depth\": <int 1-5>,\n"
            "  \"argument_logic\": <int 1-5>,\n"
            "  \"citation_density\": <int 1-5>,\n"
            "  \"citation_sophistication\": <int 1-5>,\n"
            "  \"quote_paraphrase_ratio\": <int 1-5>,\n"
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
            f"language, imagery, and structure of primary texts?\n"
            f"- argument_logic: How well-structured, coherent, and persuasive "
            f"is the argument?\n"
            f"- citation_density: Are claims adequately supported by citations "
            f"to primary and secondary sources?\n"
            f"- citation_sophistication: Does the draft use diverse citation "
            f"methods (direct quotation, paraphrase, block quotes, footnotes, "
            f"secondary citations)? Does it vary introduction verbs (writes, "
            f"argues, notes, observes, contends, insists) rather than repeating "
            f"the same verb? Are citations integrated into the argument rather "
            f"than dropped in without engagement?\n"
            f"- quote_paraphrase_ratio: Is there an appropriate balance between "
            f"direct quotation and paraphrase? Primary texts should be directly "
            f"quoted; secondary criticism should be mostly paraphrased with "
            f"selective quotation of key formulations; theory should quote "
            f"precise terms but paraphrase general arguments. Short phrase "
            f"quotations (1-8 words) should be most common, with block quotes "
            f"reserved for close-reading passages.\n\n"
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

        # Truncate long manuscripts to fit context window.
        # Keep intro + conclusion (most important for abstract) with a middle sample.
        max_chars = 12000
        if len(full_text) > max_chars:
            head = full_text[: max_chars // 2]
            tail = full_text[-(max_chars // 2) :]
            truncated_text = head + "\n\n[...middle sections omitted...]\n\n" + tail
        else:
            truncated_text = full_text

        user_prompt = (
            f"THESIS: {plan.thesis_statement}\n"
            f"TARGET JOURNAL: {plan.target_journal}\n\n"
            f"FULL MANUSCRIPT TEXT:\n\"\"\"\n{truncated_text}\n\"\"\"\n\n"
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
        """Build the system prompt, injecting citation profile norms and reflexion memories."""
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

        # Inject citation profile norms if available
        citation_norms = self._load_citation_norms(plan.target_journal)
        if citation_norms:
            prompt += f"\n\n{citation_norms}"

        if reflexion_memories:
            memory_block = "\n".join(f"- {m}" for m in reflexion_memories)
            prompt += (
                f"\n\nLESSONS FROM PAST EXPERIENCE (apply these):\n{memory_block}"
            )

        return prompt

    def _load_citation_norms(self, journal_name: str) -> str:
        """Load citation profile norms for the target journal.

        Returns a condensed instruction block derived from the citation
        profile YAML, or empty string if no profile exists.
        """
        try:
            from src.research_planner.reference_selector import load_citation_profile
            profile = load_citation_profile(journal_name)
            if not profile:
                return ""

            parts: list[str] = []
            parts.append("CITATION NORMS FOR THIS JOURNAL:")

            # Quotation strategy
            quotation = profile.get("quotation", {})
            if quotation:
                what_to_quote = quotation.get("what_to_quote", {})
                parts.append(
                    "- Primary texts: ALWAYS directly quote (reader must see actual words)."
                )
                if what_to_quote.get("key_theoretical_formulations"):
                    parts.append(
                        "- Theory: quote key formulations where precise language matters; "
                        "paraphrase general arguments."
                    )
                if what_to_quote.get("secondary_criticism"):
                    parts.append(
                        "- Secondary criticism: mostly paraphrase; quote only memorable "
                        "formulations and claims you will analyze or contest."
                    )

                lengths = quotation.get("quote_lengths", {})
                if lengths:
                    parts.append(
                        "- Quote lengths: short phrases (1-8 words) most common; "
                        "sentence-length (9-35 words) for key propositions; "
                        "block quotes (35+ words) for close reading and programmatic statements."
                    )

            # Introduction verbs
            qi = profile.get("quote_introduction", {})
            verbs = qi.get("common_verbs", [])
            if verbs:
                parts.append(
                    f"- Vary citation verbs: {', '.join(verbs[:10])}."
                )
            patterns = qi.get("framing_patterns", [])
            if patterns:
                parts.append(
                    f"- Framing patterns: {'; '.join(patterns[:4])}."
                )

            # Multilingual
            ml = profile.get("multilingual", {})
            if ml:
                rules = ml.get("handling_rules", {})
                if rules.get("primary_text_quotations"):
                    parts.append(
                        "- Non-English primary texts: quote original language FIRST, "
                        "then provide translation."
                    )

            # Footnotes
            fn = profile.get("footnotes", {})
            if fn:
                target = fn.get("target_count", [])
                if target:
                    parts.append(
                        f"- Footnotes: {target[0]}-{target[1]} substantive notes per article "
                        "(bibliographic guidance clusters, extended arguments, translation notes)."
                    )

            # Citation density by section
            cd = profile.get("citation_density", {})
            section_norms = cd.get("section_norms", {})
            if section_norms:
                norms_str = "; ".join(f"{k}: {v}" for k, v in section_norms.items())
                parts.append(f"- Citation density by section: {norms_str}.")

            # Secondary citation
            adv = qi.get("advanced_techniques", {})
            if adv.get("secondary_citation"):
                parts.append(
                    "- Use 'qtd. in' for quoting through a mediating source."
                )

            return "\n".join(parts) if len(parts) > 1 else ""

        except Exception:
            return ""

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
        "citation_sophistication": 1,
        "quote_paraphrase_ratio": 1,
    }

    # Try to extract JSON from the response (may be wrapped in markdown fences)
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return default_scores, "Could not parse critic response. Please revise for depth, logic, citations, and citation sophistication."

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return default_scores, "Could not parse critic response. Please revise for depth, logic, citations, and citation sophistication."

    scores = {
        "close_reading_depth": int(data.get("close_reading_depth", 1)),
        "argument_logic": int(data.get("argument_logic", 1)),
        "citation_density": int(data.get("citation_density", 1)),
        "citation_sophistication": int(data.get("citation_sophistication", 3)),
        "quote_paraphrase_ratio": int(data.get("quote_paraphrase_ratio", 3)),
    }

    instructions = data.get("revision_instructions", "")
    return scores, instructions
