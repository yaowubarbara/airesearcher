"""Cover letter generator for journal submissions."""

from __future__ import annotations

from typing import Optional

from src.knowledge_base.models import Language, Manuscript
from src.llm.router import LLMRouter


class CoverLetterGenerator:
    """Generates cover letters tailored to target journals."""

    def __init__(self, llm_router: LLMRouter):
        self.llm = llm_router

    async def generate(
        self,
        manuscript: Manuscript,
        journal_profile: Optional[dict] = None,
        author_name: str = "[Author Name]",
        author_affiliation: str = "[Affiliation]",
        author_email: str = "[email]",
    ) -> str:
        """Generate a cover letter for journal submission."""
        journal_name = manuscript.target_journal
        journal_scope = ""
        editor_name = "the Editors"

        if journal_profile:
            journal_scope = journal_profile.get("journal", {}).get("scope", "")
            editor_name = journal_profile.get("journal", {}).get("editor", "the Editors")

        lang_map = {
            Language.EN: "English",
            Language.ZH: "Chinese",
            Language.FR: "French",
        }
        writing_lang = lang_map.get(manuscript.language, "English")

        prompt = f"""Write a professional academic cover letter for submitting a paper to {journal_name}.

Paper title: {manuscript.title}
Paper abstract: {manuscript.abstract or 'Not provided'}
Word count: {manuscript.word_count}
Author: {author_name}
Affiliation: {author_affiliation}
Journal scope: {journal_scope}

The cover letter should:
1. Address {editor_name}
2. State the paper title and that it is being submitted for consideration
3. Briefly describe the paper's contribution (2-3 sentences)
4. Explain why it fits {journal_name} specifically (reference the journal's scope/recent interests)
5. Confirm it is original work not under consideration elsewhere
6. Provide author contact information
7. Be written in {writing_lang}
8. Be professional and concise (under 300 words)

Output ONLY the cover letter text."""

        task_type = "correspondence"
        response = self.llm.complete(
            task_type=task_type,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return self.llm.get_response_text(response)
