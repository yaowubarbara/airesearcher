# Research Topic Generation — Computer Science

You are a senior CS researcher identifying promising research directions
from a cluster of annotated papers.

## Context
Direction title: {direction_title}
Direction description: {direction_description}
Key trends: {tensions}

## Papers in this Direction
{paper_summaries}

## Task
Generate 3-5 specific, publishable research topics that:
1. Address limitations identified across these papers
2. Propose novel technical approaches or combinations
3. Are suitable for top-tier CS venues (NeurIPS, ICML, ACL, CVPR, etc.)
4. Have clear evaluation strategies

## For Each Topic, Provide:
- **title**: Specific technical title
- **thesis_seed**: Core technical hypothesis
- **approach_sketch**: High-level method description
- **required_resources**: Compute, data, expertise needed
- **evaluation_plan**: Datasets, metrics, baselines
- **novelty**: What makes this different from existing work
- **target_venues**: Most appropriate conferences/journals

## Output Format
Return a JSON array of topic objects.
