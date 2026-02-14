"""Response-to-reviewers template generator for revise & resubmit."""

from __future__ import annotations

from typing import Optional

from src.llm.router import LLMRouter


class ResponseTemplateGenerator:
    """Generates response-to-reviewers templates for R&R decisions."""

    def __init__(self, llm_router: LLMRouter):
        self.llm = llm_router

    async def generate_response(
        self,
        reviewer_comments: list[dict[str, str]],
        changes_made: list[str],
        manuscript_title: str,
        language: str = "en",
    ) -> str:
        """Generate a point-by-point response to reviewer comments.

        Args:
            reviewer_comments: List of dicts with 'reviewer' and 'comment' keys
            changes_made: List of changes made in revision
            manuscript_title: Title of the manuscript
            language: Language of the response
        """
        comments_text = ""
        for i, rc in enumerate(reviewer_comments):
            reviewer = rc.get("reviewer", f"Reviewer {i+1}")
            comment = rc.get("comment", "")
            comments_text += f"\n{reviewer}:\n{comment}\n"

        changes_text = "\n".join(f"- {c}" for c in changes_made)

        lang_instruction = {
            "en": "Write the response in English.",
            "zh": "用中文撰写回复。",
            "fr": "Rédigez la réponse en français.",
        }.get(language, "Write the response in English.")

        prompt = f"""Generate a professional point-by-point response to reviewer comments
for a revised manuscript submission.

Manuscript: {manuscript_title}

Reviewer comments:
{comments_text}

Changes made in revision:
{changes_text}

{lang_instruction}

Format as:
1. Brief thank you to editor and reviewers
2. For each reviewer comment:
   - Quote the comment
   - Provide a response explaining what was changed (or a respectful explanation if not changed)
   - Reference specific page/section numbers where changes were made
3. Closing

Output the complete response document."""

        response = self.llm.complete(
            task_type="correspondence",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return self.llm.get_response_text(response)

    def generate_blank_template(
        self, reviewer_comments: list[dict[str, str]], language: str = "en"
    ) -> str:
        """Generate a blank template with reviewer comments ready to be filled in."""
        header = {
            "en": "Response to Reviewers",
            "zh": "审稿意见回复",
            "fr": "Réponse aux évaluateurs",
        }.get(language, "Response to Reviewers")

        thanks = {
            "en": "We thank the editor and reviewers for their careful reading and constructive feedback. Below we address each comment point by point.",
            "zh": "感谢编辑和审稿人的仔细阅读和建设性意见。以下逐条回复审稿意见。",
            "fr": "Nous remercions l'éditeur et les évaluateurs pour leur lecture attentive et leurs commentaires constructifs. Nous répondons ci-dessous point par point.",
        }.get(language, "")

        lines = [f"# {header}", "", thanks, ""]

        for i, rc in enumerate(reviewer_comments):
            reviewer = rc.get("reviewer", f"Reviewer {i+1}")
            comment = rc.get("comment", "")
            lines.append(f"## {reviewer}")
            lines.append("")

            # Split multi-point comments
            points = [p.strip() for p in comment.split("\n") if p.strip()]
            for j, point in enumerate(points):
                lines.append(f"**Comment {j+1}**: {point}")
                lines.append("")
                lines.append("**Response**: [Your response here]")
                lines.append("")

        return "\n".join(lines)
