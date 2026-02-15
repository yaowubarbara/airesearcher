"""Citation verification pipeline: parse, verify, annotate."""

from __future__ import annotations

from typing import Optional

from src.citation_verifier.annotator import VerificationReport, annotate_manuscript
from src.citation_verifier.engine import CitationVerificationEngine
from src.citation_verifier.parser import parse_mla_citations


async def verify_manuscript_citations(
    text: str,
    crossref_email: Optional[str] = None,
    openalex_email: Optional[str] = None,
) -> tuple[str, VerificationReport]:
    """Run the full citation verification pipeline.

    1. Parse MLA-style inline citations from the manuscript text.
    2. Verify each citation against CrossRef and OpenAlex.
    3. Annotate the text with [VERIFY] tags where needed.
    4. Generate a summary report.

    Returns:
        (annotated_text, report)
    """
    # Step 1: Parse
    citations = parse_mla_citations(text)

    if not citations:
        report = VerificationReport(total=0)
        return text, report

    # Step 2: Verify
    engine = CitationVerificationEngine(
        crossref_email=crossref_email,
        openalex_email=openalex_email,
    )
    try:
        verifications = await engine.verify_all(citations, text)
    finally:
        await engine.close()

    # Step 3: Annotate
    annotated = annotate_manuscript(text, verifications)

    # Step 4: Report
    report = VerificationReport.from_verifications(verifications)

    return annotated, report
