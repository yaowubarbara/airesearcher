"""Close reading module for detailed textual analysis."""

from __future__ import annotations

from src.llm.router import LLMRouter


class CloseReader:
    """Performs detailed close reading analysis of textual passages.

    Close reading is a method of literary criticism that focuses on careful,
    sustained interpretation of a brief passage of text. This class generates
    publication-ready analytical prose examining linguistic features, imagery,
    narrative structure, and intertextual connections.
    """

    CLOSE_READING_SYSTEM_PROMPT = (
        "You are an expert literary scholar performing close reading analysis. "
        "Your output must be publication-ready analytical prose suitable for an "
        "academic journal. Do NOT use bullet points, numbered lists, or headings. "
        "Write in flowing, well-structured paragraphs with sophisticated academic "
        "diction. Every claim must be grounded in the specific language of the passage."
    )

    @staticmethod
    async def perform_close_reading(
        passage: str,
        context: dict,
        language: str,
        llm_router: LLMRouter,
    ) -> str:
        """Perform a detailed close reading of a textual passage.

        Args:
            passage: The passage to analyze.
            context: A dict containing:
                - work_title: Title of the literary work.
                - author: Author of the work.
                - page: Page or location reference.
                - surrounding_text: Text surrounding the passage for context.
                - thesis: The thesis statement the analysis should support.
            language: The language to write the analysis in (e.g. "en", "zh", "fr").
            llm_router: The LLM router instance for making completion calls.

        Returns:
            Publication-ready analytical prose as a string.
        """
        work_title = context.get("work_title", "")
        author = context.get("author", "")
        page = context.get("page", "")
        surrounding_text = context.get("surrounding_text", "")
        thesis = context.get("thesis", "")

        language_instruction = _language_instruction(language)

        user_prompt = (
            f"Perform a close reading of the following passage from "
            f"{author}, *{work_title}*"
            f"{f' (p. {page})' if page else ''}.\n\n"
            f"PASSAGE:\n\"\"\"\n{passage}\n\"\"\"\n\n"
        )

        if surrounding_text:
            user_prompt += (
                f"SURROUNDING CONTEXT:\n\"\"\"\n{surrounding_text}\n\"\"\"\n\n"
            )

        user_prompt += (
            f"THESIS BEING ARGUED:\n{thesis}\n\n"
            f"Your analysis must cover ALL of the following dimensions in a unified, "
            f"flowing argument (do NOT use section headers or bullet points):\n\n"
            f"1. LINGUISTIC FEATURES: Examine diction, syntax, verb tenses, "
            f"pronouns, register shifts, and any notable grammatical or phonological "
            f"patterns (alliteration, assonance, rhythm) in the passage.\n\n"
            f"2. IMAGERY AND METAPHOR: Identify and interpret figurative language, "
            f"sensory imagery, symbols, and metaphorical structures. Explain how "
            f"they produce meaning.\n\n"
            f"3. NARRATIVE STRUCTURE: Analyze point of view, focalization, temporal "
            f"ordering, narrative voice, and how the passage fits into the broader "
            f"narrative arc.\n\n"
            f"4. INTERTEXTUAL CONNECTIONS: Identify allusions, echoes of other "
            f"texts, generic conventions, or cultural references. Situate the "
            f"passage within relevant literary or intellectual traditions.\n\n"
            f"5. SUPPORT FOR THESIS: Demonstrate explicitly how the passage provides "
            f"evidence for the thesis stated above. The analysis should build toward "
            f"this argument organically.\n\n"
            f"{language_instruction}"
        )

        messages = [
            {"role": "system", "content": CloseReader.CLOSE_READING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = llm_router.complete(
            task_type="close_reading",
            messages=messages,
            temperature=0.4,
        )

        return llm_router.get_response_text(response)


def _language_instruction(language: str) -> str:
    """Return a writing-language instruction string."""
    lang_map = {
        "en": "Write the entire analysis in English.",
        "zh": "Write the entire analysis in Chinese (Mandarin).",
        "fr": "Write the entire analysis in French.",
    }
    return lang_map.get(language, f"Write the entire analysis in the language code: {language}.")
