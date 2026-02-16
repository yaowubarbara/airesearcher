"""Research planner - creates detailed research and writing plans."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    Language,
    MissingPrimaryText,
    PaperStatus,
    PrimaryTextReport,
    ResearchPlan,
    TopicProposal,
)
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter

from .outline_generator import OutlineGenerator
from .reference_selector import ReferenceSelector

logger = logging.getLogger(__name__)


class ResearchPlanner:
    """Creates detailed research plans from topic proposals."""

    def __init__(
        self,
        db: Database,
        vector_store: VectorStore,
        llm_router: LLMRouter,
    ):
        self.db = db
        self.vs = vector_store
        self.llm = llm_router
        self.ref_selector = ReferenceSelector(db, vector_store, llm_router)
        self.outline_gen = OutlineGenerator(llm_router)

    async def create_plan(
        self,
        topic: TopicProposal,
        target_journal: str,
        language: Language = Language.EN,
        journal_style_path: Optional[str] = None,
        skip_acquisition: bool = False,
    ) -> ResearchPlan:
        """Create a comprehensive research plan for a given topic.

        Steps:
        1. Generate thesis statement from the research question
        2. Select references using Corrective RAG
        3. Load journal style profile if available
        4. Generate detailed outline
        5. Store plan in database

        Args:
            topic: Topic proposal with research question and gap.
            target_journal: Target journal name.
            language: Target writing language.
            journal_style_path: Optional path to journal style YAML.
            skip_acquisition: If True, skip the reference acquisition step
                (useful when references are already in the DB).
        """
        # Step 1: Generate thesis statement
        thesis = await self._generate_thesis(
            topic.research_question, topic.gap_description, target_journal, language
        )

        # Step 1.5: Acquire references from APIs for this topic
        if not skip_acquisition:
            try:
                from src.reference_acquisition.pipeline import ReferenceAcquisitionPipeline
                acq_pipeline = ReferenceAcquisitionPipeline(self.db, self.vs)
                acq_report = await acq_pipeline.acquire_references(
                    topic.research_question, max_results=50
                )
                import logging
                logging.getLogger(__name__).info(
                    "Acquired references: %s", acq_report.summary()
                )
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Reference acquisition failed, proceeding with existing data",
                    exc_info=True,
                )
        else:
            import logging
            logging.getLogger(__name__).info(
                "Skipping reference acquisition (skip_acquisition=True)"
            )

        # Step 2: Select references with Corrective RAG
        reference_ids = await self.ref_selector.select_references(
            research_question=topic.research_question,
            thesis=thesis,
            target_count=35,
        )

        # Gather reference metadata for outline generation
        ref_metadata = []
        for ref_id in reference_ids:
            paper = self.db.get_paper(ref_id)
            if paper:
                ref_metadata.append({
                    "authors": paper.authors,
                    "title": paper.title,
                    "year": paper.year,
                    "journal": paper.journal,
                })

        # Step 3: Load journal style if available
        journal_style = None
        if journal_style_path:
            style_path = Path(journal_style_path)
            if style_path.exists():
                with open(style_path) as f:
                    journal_style = yaml.safe_load(f)

        # Step 4: Generate outline
        outline = await self.outline_gen.generate_outline(
            research_question=topic.research_question,
            thesis=thesis,
            target_journal=target_journal,
            language=language,
            available_references=ref_metadata,
            journal_style=journal_style,
        )

        # Step 5: Create and store plan
        plan = ResearchPlan(
            topic_id=topic.id or "",
            thesis_statement=thesis,
            target_journal=target_journal,
            target_language=language,
            outline=outline,
            reference_ids=reference_ids,
            status="draft",
        )

        plan_id = self.db.insert_plan(plan)
        plan.id = plan_id
        return plan

    async def _generate_thesis(
        self,
        research_question: str,
        gap_description: str,
        target_journal: str,
        language: Language,
    ) -> str:
        """Generate a clear thesis statement from the research question."""
        lang_instruction = {
            Language.EN: "Write the thesis statement in English.",
            Language.ZH: "用中文撰写论文的核心论点。",
            Language.FR: "Rédigez la thèse en français.",
        }.get(language, "Write the thesis statement in English.")

        prompt = f"""You are a comparative literature scholar formulating a thesis statement.

Research question: {research_question}
Research gap identified: {gap_description}
Target journal: {target_journal}

{lang_instruction}

Generate a clear, arguable, and specific thesis statement for an academic paper.
The thesis should:
- Make a specific claim (not just describe a topic)
- Be falsifiable and debatable
- Address the identified research gap
- Be appropriate for the target journal's scope

Output ONLY the thesis statement (1-3 sentences)."""

        task_type = f"writing_{language.value}" if language.value != "en" else "writing_en"
        response = self.llm.complete(
            task_type=task_type,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return self.llm.get_response_text(response).strip()

    async def refine_plan(
        self,
        plan_id: str,
        feedback: str,
        conversation_history: list[dict] | None = None,
    ) -> tuple[dict, str]:
        """Refine a plan based on user feedback.

        Args:
            plan_id: The plan to refine.
            feedback: The user's latest refinement request.
            conversation_history: Optional prior conversation turns
                ``[{role, content}, ...]`` for multi-turn context.

        Returns:
            A tuple of (updated_plan_data, assistant_message).
        """
        plan_data = self.db.get_plan(plan_id)
        if not plan_data:
            raise ValueError(f"Plan {plan_id} not found")

        outline_json = json.dumps(plan_data["outline"], ensure_ascii=False, indent=2)

        system_prompt = """You are a comparative literature research planner.
You will be given a current research plan (thesis + outline) and user feedback.
Revise the plan according to the feedback.

IMPORTANT: Each outline section MUST have these fields:
- title (string)
- argument (string — the section's core claim; see PROBLEMATIQUE below)
- primary_texts (list of strings)
- passages_to_analyze (list of strings)
- secondary_sources (list of strings — works available in the corpus)
- missing_references (list of strings — works needed but not yet available)
- estimated_words (integer)

PROBLEMATIQUE REQUIREMENT:
Each section's "argument" MUST be a specific, falsifiable claim — NOT a vague description.
BAD: "This section discusses the role of translation."
GOOD: "Celan's post-1960 translations reveal a strategy of interlingual mourning that contradicts Steiner's claim of untranslatability."
The argument must name specific authors, texts, or concepts, and make a claim that could be wrong.

Respond with a JSON object containing exactly two keys:
1. "plan" — an object with "thesis" (string) and "outline" (array of sections)
2. "message" — a brief summary (1-3 sentences) of what you changed and why

Example response format:
```json
{
  "plan": {
    "thesis": "Revised thesis...",
    "outline": [
      {
        "title": "Introduction",
        "argument": "...",
        "primary_texts": ["Author, Title"],
        "passages_to_analyze": ["..."],
        "secondary_sources": ["..."],
        "missing_references": ["..."],
        "estimated_words": 1500
      }
    ]
  },
  "message": "I revised the thesis to focus on X and added a new section on Y."
}
```"""

        # Build messages: system + conversation history + current request
        messages: list[dict] = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            for turn in conversation_history:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        user_msg = f"""Current thesis:
{plan_data['thesis_statement']}

Current outline:
{outline_json}

User feedback: {feedback}"""
        messages.append({"role": "user", "content": user_msg})

        response = self.llm.complete(
            task_type="writing_en",
            messages=messages,
            temperature=0.5,
        )
        text = self.llm.get_response_text(response)

        assistant_message = "Plan updated."
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())

                # Extract plan data (support both nested and flat formats)
                plan_obj = data.get("plan", data)
                thesis = plan_obj.get("thesis")
                outline = plan_obj.get("outline")

                if thesis:
                    self.db.conn.execute(
                        "UPDATE research_plans SET thesis_statement = ? WHERE id = ?",
                        (thesis, plan_id),
                    )
                if outline:
                    self.db.conn.execute(
                        "UPDATE research_plans SET outline = ? WHERE id = ?",
                        (json.dumps(outline, ensure_ascii=False), plan_id),
                    )
                self.db.conn.commit()

                if data.get("message"):
                    assistant_message = data["message"]
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse refine response: %s", exc)
            assistant_message = "I attempted to refine the plan but couldn't parse the result. Please try again."

        updated = self.db.get_plan(plan_id)
        return updated, assistant_message


def _extract_title(text: str) -> str:
    """Extract the work title from a primary_texts entry.

    Patterns handled:
      "Paul Celan, Atemwende"                     -> "Atemwende"
      "Glissant, Poétique de la Relation (1990)"   -> "Poétique de la Relation"
      "Celan, 'Psalm' (Die Niemandsrose, 1963)"    -> "Psalm"
      "Celan, \"Todesfuge\""                        -> "Todesfuge"
      "Atemwende"                                   -> "Atemwende"
      "Can Xue, 黄泥街"                             -> "黄泥街"
    """
    text = text.strip()
    if not text:
        return text

    # Split on first comma to separate author from title
    if "," in text:
        _, _, after_comma = text.partition(",")
        title_part = after_comma.strip()
    else:
        title_part = text

    # Strip surrounding quotes (single or double) or italic markers (*)
    quote_chars = "''\u2018\u2019\"\"*\u201c\u201d"
    title_part = title_part.strip(quote_chars).strip()

    # Remove trailing parenthetical (year or collection info)
    # e.g. "(1990)" or "(Die Niemandsrose, 1963)"
    title_part = re.sub(r"\s*\([^)]*\)\s*$", "", title_part).strip()

    # Strip quotes again (they may surround the inner title before a parenthetical)
    title_part = title_part.strip(quote_chars).strip()

    return title_part


def _jaccard_word_overlap(a: str, b: str) -> float:
    """Compute Jaccard similarity over lowercased word sets."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def detect_missing_primary_texts(
    plan: ResearchPlan,
    db: Database,
    vector_store: VectorStore,
) -> PrimaryTextReport:
    """Detect which primary literary texts in an outline are not indexed.

    For each unique primary_texts entry across all outline sections:
      Tier 1: SQLite LIKE search by extracted title
      Tier 2: ChromaDB semantic search (if Tier 1 finds nothing indexed)

    Returns a PrimaryTextReport with available/missing lists.
    """
    # Collect unique primary texts and which sections need them
    text_sections: dict[str, list[str]] = {}  # text_name -> [section titles]
    text_passages: dict[str, list[str]] = {}  # text_name -> [passages]
    text_purposes: dict[str, str] = {}  # text_name -> purpose

    for section in plan.outline:
        for pt in section.primary_texts:
            pt_stripped = pt.strip()
            if not pt_stripped:
                continue
            text_sections.setdefault(pt_stripped, [])
            if section.title not in text_sections[pt_stripped]:
                text_sections[pt_stripped].append(section.title)

            text_passages.setdefault(pt_stripped, [])
            for passage in section.passages_to_analyze:
                if passage not in text_passages[pt_stripped]:
                    text_passages[pt_stripped].append(passage)

            if pt_stripped not in text_purposes:
                text_purposes[pt_stripped] = section.argument[:200] if section.argument else ""

    if not text_sections:
        return PrimaryTextReport(total_unique=0)

    available: list[str] = []
    missing: list[MissingPrimaryText] = []

    for text_name in text_sections:
        title = _extract_title(text_name)
        found = False

        # Tier 1: SQLite LIKE search
        if title:
            papers = db.search_papers_by_title(title, limit=5)
            for p in papers:
                if p.status in (PaperStatus.INDEXED, PaperStatus.ANALYZED):
                    found = True
                    break

        # Tier 2: ChromaDB semantic search
        if not found and title:
            try:
                from src.literature_indexer.embeddings import get_embedding

                embedding = get_embedding(title)
                results = vector_store.search_papers(embedding, n_results=3)
                if results and results.get("metadatas") and results["metadatas"][0]:
                    for i, meta in enumerate(results["metadatas"][0]):
                        paper_id = meta.get("paper_id", "")
                        if paper_id:
                            paper = db.get_paper(paper_id)
                            if paper and paper.status in (PaperStatus.INDEXED, PaperStatus.ANALYZED):
                                paper_title = paper.title or ""
                                if _jaccard_word_overlap(title, paper_title) > 0.5:
                                    found = True
                                    break
                        # Also check document text overlap as fallback
                        if results.get("documents") and results["documents"][0]:
                            doc = results["documents"][0][i]
                            if _jaccard_word_overlap(title, doc[:200]) > 0.5:
                                found = True
                                break
            except Exception:
                logger.debug("ChromaDB search failed for '%s', skipping Tier 2", title)

        if found:
            available.append(text_name)
        else:
            missing.append(MissingPrimaryText(
                text_name=text_name,
                sections_needing=text_sections[text_name],
                passages_needed=text_passages[text_name],
                purpose=text_purposes.get(text_name, ""),
            ))

    return PrimaryTextReport(
        total_unique=len(text_sections),
        available=available,
        missing=missing,
    )
