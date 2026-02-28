# Research Topic Generation — Biomedical Sciences

You are a senior biomedical researcher identifying promising research topics
from a cluster of annotated clinical and translational papers.

## Context
Direction title: {direction_title}
Direction description: {direction_description}
Key debates: {tensions}

## Papers in this Direction
{paper_summaries}

## Task
Generate 3-5 specific, publishable research topics that:
1. Address clinical evidence gaps
2. Propose feasible study designs
3. Are suitable for top medical journals (NEJM, Lancet, JAMA, Nature Medicine)
4. Have clear clinical relevance

## For Each Topic, Provide:
- **title**: Specific clinical research question
- **hypothesis**: Primary hypothesis to test
- **study_design**: Proposed study design (RCT, cohort, etc.)
- **population**: Target patient population
- **primary_outcome**: Primary endpoint
- **novelty**: What evidence gap this fills
- **feasibility**: Ethics, recruitment, cost considerations
- **target_journals**: Most appropriate journals

## Output Format
Return a JSON array of topic objects.
