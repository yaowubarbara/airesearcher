# Direction Synthesis Prompt — Comparative Literature

You are synthesizing annotated papers into coherent research directions.

## Task
Given the following annotated papers, cluster them into research directions
based on shared problématiques, theoretical approaches, and textual corpora.

## Annotations
{annotations}

## Instructions
1. Identify 5-10 distinct research directions
2. For each direction:
   - Provide a descriptive title
   - Summarize the shared problématique
   - List dominant tensions or debates
   - Identify which papers belong to this direction
   - Assess the direction's growth trajectory (emerging, established, declining)
3. Prioritize directions that reveal genuine gaps in the scholarship

## Output Format
Return a JSON array of direction objects with: title, description,
dominant_tensions, paper_ids, growth_trajectory.
