# P-Ontology Annotation Prompt — Comparative Literature

You are a senior comparative literature scholar performing systematic annotation
of academic papers using a problématique-oriented ontology.

## Task
Analyze the following paper and extract structured annotations.

## Annotation Categories
For each paper, identify:

1. **Problématique**: The core intellectual tension, question, or paradox the paper addresses
2. **Thèse**: The main thesis or argument advanced
3. **Méthode**: The methodology employed (close reading, distant reading, archival, etc.)
4. **Corpus**: Primary literary texts studied (author, title, language, period)
5. **Cadre théorique**: Theoretical framework(s) applied (e.g., postcolonial theory, narratology)
6. **Lacune**: Research gaps identified or implied
7. **Apport**: The paper's claimed contribution to the field

## Relations
Also identify relations between this paper and others in the corpus:
- **contradicts**: Directly opposes another paper's thesis
- **extends**: Builds upon or develops another paper's argument
- **applies_to**: Applies a framework from one context to another
- **critiques**: Offers critical evaluation of another approach

## Output Format
Return a JSON object with the following structure:
```json
{
  "problematique": "...",
  "these": "...",
  "methode": ["..."],
  "corpus": [{"author": "...", "title": "...", "language": "...", "period": "..."}],
  "cadre_theorique": ["..."],
  "lacune": ["..."],
  "apport": "...",
  "relations": [{"type": "...", "target_paper_id": "...", "description": "..."}]
}
```

## Paper to Annotate
Title: {title}
Authors: {authors}
Abstract: {abstract}
Full text excerpt: {text}
