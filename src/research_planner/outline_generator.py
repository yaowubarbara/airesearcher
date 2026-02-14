"""Research paper outline generator."""

from __future__ import annotations

import json
import re
from typing import Optional

from src.knowledge_base.models import Language, OutlineSection, ResearchPlan
from src.llm.router import LLMRouter


class OutlineGenerator:
    """Generates structured research paper outlines."""

    def __init__(self, llm_router: LLMRouter):
        self.llm = llm_router

    async def generate_outline(
        self,
        research_question: str,
        thesis: str,
        target_journal: str,
        language: Language,
        available_references: list[dict],
        journal_style: Optional[dict] = None,
    ) -> list[OutlineSection]:
        """Generate a detailed section-by-section outline.

        Args:
            research_question: The central research question
            thesis: The thesis statement
            target_journal: Name of the target journal
            language: Writing language
            available_references: List of dicts with reference metadata
            journal_style: Optional journal style profile

        Returns:
            List of OutlineSection objects
        """
        # Build reference summary for the prompt
        ref_summary = self._format_reference_summary(available_references[:40])

        style_instructions = ""
        if journal_style:
            typical_structure = journal_style.get("learned_patterns", {}).get(
                "typical_structure", ""
            )
            word_limit = journal_style.get("formatting", {}).get("word_limit", "8000-10000")
            close_reading_count = journal_style.get("learned_patterns", {}).get(
                "avg_close_reading_passages", "4-6"
            )
            style_instructions = f"""
Journal style notes:
- Typical structure: {typical_structure}
- Word limit: {word_limit}
- Expected close reading passages: {close_reading_count}
- Conventions: {journal_style.get('formatting', {}).get('writing_conventions', [])}
"""

        lang_instruction = {
            Language.EN: "Write the outline in English.",
            Language.ZH: "用中文撰写大纲。",
            Language.FR: "Rédigez le plan en français.",
        }.get(language, "Write the outline in English.")

        prompt = f"""You are an expert comparative literature scholar creating a detailed paper outline.

Research question: {research_question}
Thesis statement: {thesis}
Target journal: {target_journal}
{style_instructions}
{lang_instruction}

Available references (use these to plan which sources to cite in each section):
{ref_summary}

Generate a detailed outline with 5-7 sections. For each section provide:
1. Section title
2. The argument/point made in this section
3. Primary texts to close-read (specific works and passages)
4. Secondary sources to cite (from the available references)
5. Estimated word count for this section

Output as a JSON array of objects with keys:
"title", "argument", "primary_texts" (array of strings),
"passages_to_analyze" (array of specific passage descriptions),
"secondary_sources" (array of author-title strings), "estimated_words" (integer)

Ensure:
- The outline builds a coherent argument from introduction to conclusion
- Multiple close reading passages are distributed across sections
- Each section has 3-6 secondary sources
- The total word count matches the journal's expectations
- Include genuine comparative analysis across languages/traditions

Output ONLY the JSON array."""

        task_type = f"writing_{language.value}" if language.value != "en" else "writing_en"
        response = self.llm.complete(
            task_type=task_type,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        text = self.llm.get_response_text(response)

        return self._parse_outline(text)

    def _format_reference_summary(self, references: list[dict]) -> str:
        """Format references into a concise summary for the prompt."""
        lines = []
        for i, ref in enumerate(references):
            authors = ref.get("authors", [])
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            title = ref.get("title", "Untitled")
            year = ref.get("year", "n.d.")
            journal = ref.get("journal", "")
            lines.append(f"[{i+1}] {author_str}. \"{title}\". {journal} ({year})")
        return "\n".join(lines)

    def _parse_outline(self, text: str) -> list[OutlineSection]:
        """Parse LLM output into OutlineSection objects."""
        # Try to extract JSON from the response
        try:
            # Find JSON array in the text
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: create a minimal outline
            return [
                OutlineSection(
                    title="Introduction",
                    argument="Introduce the research question and thesis",
                    estimated_words=1500,
                ),
                OutlineSection(
                    title="Analysis",
                    argument="Main analysis section",
                    estimated_words=5000,
                ),
                OutlineSection(
                    title="Conclusion",
                    argument="Synthesize findings",
                    estimated_words=1500,
                ),
            ]

        sections = []
        for item in data:
            sections.append(
                OutlineSection(
                    title=item.get("title", "Untitled Section"),
                    argument=item.get("argument", ""),
                    primary_texts=item.get("primary_texts", []),
                    passages_to_analyze=item.get("passages_to_analyze", []),
                    secondary_sources=item.get("secondary_sources", []),
                    estimated_words=item.get("estimated_words", 1000),
                )
            )
        return sections
