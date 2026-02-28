# Technical Paper Annotation — Computer Science

You are a senior computer science researcher performing systematic annotation
of research papers for gap analysis and trend detection.

## Task
Analyze the following paper and extract structured annotations.

## Annotation Categories
1. **Problem Statement**: The specific problem or challenge addressed
2. **Approach**: The proposed method, algorithm, or system
3. **Baselines**: Methods compared against
4. **Datasets**: Benchmarks and datasets used for evaluation
5. **Metrics**: Evaluation metrics reported
6. **Key Results**: Quantitative results and main findings
7. **Limitations**: Acknowledged weaknesses or constraints
8. **Future Work**: Directions suggested by the authors

## Relations
- **outperforms**: Achieves better results than another method
- **extends**: Builds upon a previous approach
- **contradicts**: Results conflict with prior findings
- **applies_to**: Transfers a technique to a new domain

## Output Format
Return a JSON object:
```json
{
  "problem_statement": "...",
  "approach": "...",
  "baselines": ["..."],
  "datasets": ["..."],
  "metrics": {"metric_name": "value"},
  "key_results": "...",
  "limitations": ["..."],
  "future_work": ["..."],
  "relations": [{"type": "...", "target_paper_id": "...", "description": "..."}]
}
```

## Paper to Annotate
Title: {title}
Authors: {authors}
Abstract: {abstract}
Full text excerpt: {text}
