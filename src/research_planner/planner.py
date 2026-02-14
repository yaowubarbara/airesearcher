"""Research planner - creates detailed research and writing plans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml

from src.knowledge_base.db import Database
from src.knowledge_base.models import Language, ResearchPlan, TopicProposal
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter

from .outline_generator import OutlineGenerator
from .reference_selector import ReferenceSelector


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

    async def refine_plan(self, plan_id: str, feedback: str) -> ResearchPlan:
        """Refine a plan based on user feedback."""
        plan_data = self.db.get_plan(plan_id)
        if not plan_data:
            raise ValueError(f"Plan {plan_id} not found")

        prompt = f"""Revise this research plan based on the following feedback.

Current thesis: {plan_data['thesis_statement']}
Current outline: {plan_data['outline']}

Feedback: {feedback}

Output a revised thesis statement and outline in the same JSON format.
Respond with JSON: {{"thesis": "...", "outline": [...]}}"""

        response = self.llm.complete(
            task_type="writing_en",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        text = self.llm.get_response_text(response)

        try:
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                if "thesis" in data:
                    self.db.conn.execute(
                        "UPDATE research_plans SET thesis_statement = ? WHERE id = ?",
                        (data["thesis"], plan_id),
                    )
                if "outline" in data:
                    self.db.conn.execute(
                        "UPDATE research_plans SET outline = ? WHERE id = ?",
                        (json.dumps(data["outline"]), plan_id),
                    )
                self.db.conn.commit()
        except (json.JSONDecodeError, ValueError):
            pass

        return plan_data
