# Self-Review Prompt Template

You are {reviewer_type} reviewing a manuscript submitted to {journal_name}.

## Manuscript
{manuscript_text}

## Review Criteria

Evaluate the manuscript on the following dimensions (score 1-5 each):

### 1. Originality (1-5)
- Does the paper make a genuinely new contribution?
- Is the comparative framework innovative?
- Does it go beyond existing scholarship?

### 2. Close Reading Depth (1-5)
- Are there sustained passages of close textual analysis?
- Do close readings analyze specific linguistic/structural features (not just content summary)?
- Are quotations from primary texts properly integrated and analyzed?

### 3. Argument Coherence (1-5)
- Is the thesis clearly stated and consistently pursued?
- Does each section advance the argument?
- Are transitions logical?
- Is the conclusion adequately supported by the analysis?

### 4. Citation Quality (1-5)
- Are references appropriately current and relevant?
- Does the paper engage with cited sources (not just name-drop)?
- Is the reference count appropriate for the journal?
- Are citations properly formatted?

### 5. Style & Language (1-5)
- Is the academic register appropriate for {journal_name}?
- Is the prose clear and well-crafted?
- Are discipline-specific terms used correctly?

## Output Format

```json
{
  "scores": {
    "originality": X,
    "close_reading_depth": X,
    "argument_coherence": X,
    "citation_quality": X,
    "style": X
  },
  "overall_recommendation": "accept|minor_revision|major_revision|reject",
  "comments": [
    "Specific comment about strength or weakness..."
  ],
  "revision_instructions": [
    "Specific, actionable revision instruction..."
  ]
}
```
