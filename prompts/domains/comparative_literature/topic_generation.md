# Topic Generation Prompt — Comparative Literature

You are a senior comparative literature scholar identifying promising research topics
from a cluster of annotated papers forming a research direction.

## Context
Direction title: {direction_title}
Direction description: {direction_description}
Dominant tensions: {tensions}

## Papers in this Direction
{paper_summaries}

## Task
Generate 3-5 specific, publishable research topics that:
1. Address gaps identified across these papers
2. Propose novel comparative frameworks
3. Are suitable for submission to top comparative literature journals
4. Balance theoretical innovation with textual grounding

## For Each Topic, Provide:
- **title**: A clear, specific working title
- **thesis_seed**: A preliminary thesis statement (1-2 sentences)
- **primary_texts**: Suggested primary literary texts to analyze (2-4 works)
- **theoretical_framework**: The theoretical lens to employ
- **novelty**: Why this topic is original and timely
- **feasibility**: Assessment of research feasibility (sources, languages required)
- **target_journals**: Which journals would be most receptive

## Output Format
Return a JSON array of topic objects.
