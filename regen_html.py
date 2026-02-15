"""Regenerate HTML with Works Cited from existing manuscript.md."""

import os
import sys
from pathlib import Path
from datetime import datetime

os.environ["OPENROUTER_API_KEY"] = "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"

from src.knowledge_base.db import Database
from src.llm.router import LLMRouter
from run_demo import create_demo_plan, render_html, generate_works_cited

OUTPUT_DIR = Path("data/demo_output")

def main():
    # Read existing manuscript
    md_path = OUTPUT_DIR / "manuscript.md"
    md_text = md_path.read_text(encoding="utf-8")

    # Parse sections from markdown
    plan = create_demo_plan()

    # Extract abstract and sections from existing markdown
    lines = md_text.split("\n")
    abstract = ""
    sections: dict[str, str] = {}
    current_section = None
    current_content: list[str] = []
    in_abstract = False

    for line in lines:
        if line.startswith("## Abstract"):
            in_abstract = True
            continue
        elif line.startswith("## "):
            if in_abstract:
                abstract = "\n".join(current_content).strip()
                in_abstract = False
                current_content = []
            elif current_section:
                sections[current_section] = "\n".join(current_content).strip()
                current_content = []
            current_section = line[3:].strip()
        else:
            current_content.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_content).strip()

    full_text = "\n\n".join(f"## {t}\n\n{c}" for t, c in sections.items())
    print(f"Loaded manuscript: {len(full_text.split())} words, {len(sections)} sections")

    # Generate Works Cited via LLM
    db = Database(":memory:")
    router = LLMRouter(config_path="config/llm_routing_openrouter.yaml", db=db)

    print("Generating Works Cited...")
    works_cited = generate_works_cited(full_text, plan, router)
    wc_entries = [l for l in works_cited.strip().split("\n") if l.strip()]
    print(f"Done: {len(wc_entries)} entries")

    # Render HTML
    html = render_html(sections, plan, abstract, 1644.4, works_cited)
    html = html.replace(
        "{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        datetime.now().strftime('%Y-%m-%d %H:%M')
    )
    output_path = OUTPUT_DIR / "manuscript.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Saved: {output_path}")

    # Update markdown too
    md_content = f"# {plan.thesis_statement}\n\n"
    md_content += f"**Journal**: {plan.target_journal}\n\n"
    md_content += f"## Abstract\n\n{abstract}\n\n"
    md_content += full_text
    md_content += f"\n\n## Works Cited\n\n{works_cited}"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Updated: {md_path}")


if __name__ == "__main__":
    main()
