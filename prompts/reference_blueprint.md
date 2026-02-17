You are a comparative literature research librarian. Given a research topic,
generate a structured bibliography blueprint.

## Topic
Title: {title}
Research Question: {research_question}
Gap: {gap_description}

## Task
Create a bibliography blueprint with 5-8 reference categories. For each category:

1. **Category name** and brief description (what kind of sources belong here)
2. **5-10 specific references** you believe exist — give author surname, approximate title, and approximate year. Be as specific as possible. It is OK if some details are imprecise — they will be verified.
3. **3-5 targeted search queries** — keyword phrases that would find more references in this category via academic search APIs
4. **Key authors** (2-4 scholars whose other work should be explored)
5. **Key journals** (1-3 journals likely to contain relevant articles)

## Rules
- ONLY suggest references you are reasonably confident exist (published in real journals/presses)
- Include a mix of: foundational/classic works, recent scholarship (2015+), and methodological/theoretical works
- Each category should have a clear function in the article (e.g., "provides theoretical framework" vs "supplies primary criticism")
- Suggest references in multiple languages if relevant to the topic

## Output
Return a JSON object:
```json
{{
  "categories": [
    {{
      "name": "Category Name",
      "description": "What this category covers and why it's needed",
      "suggested_refs": [
        {{"author": "Surname", "title": "Approximate Title", "year": 2020}}
      ],
      "search_queries": ["query 1", "query 2"],
      "key_authors": ["Author Name 1", "Author Name 2"],
      "key_journals": ["Journal Name"]
    }}
  ]
}}
```
