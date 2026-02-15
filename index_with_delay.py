#!/usr/bin/env python3
"""Index PDFs one at a time with delays to avoid ZhipuAI rate limits."""

import os
import re
import sys
import time
import uuid
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from src.knowledge_base.db import Database
from src.knowledge_base.models import PaperStatus
from src.knowledge_base.vector_store import VectorStore
from src.literature_indexer.indexer import Indexer

DELAY_SECONDS = 15  # seconds between papers


def main():
    db = Database()
    vs = VectorStore()
    indexer = Indexer(vector_store=vs)
    folder = Path("data/papers")
    pdfs = sorted(folder.glob("*.pdf"))

    print(f"Found {len(pdfs)} PDFs\n")

    indexed = 0
    skipped = 0
    failed = 0

    for pdf in pdfs:
        fname = pdf.stem

        # DOI-based matching
        paper_id = None
        doi_candidate = re.sub(r"_", "/", fname, count=1)
        paper = db.get_paper_by_doi(doi_candidate)
        if paper:
            paper_id = paper.id
            if paper.status in (
                PaperStatus.INDEXED,
                PaperStatus.PDF_DOWNLOADED,
                PaperStatus.ANALYZED,
            ):
                print(f"  Skip (already indexed): {pdf.name}")
                skipped += 1
                continue

        if not paper_id:
            paper_id = str(uuid.uuid4())

        try:
            print(f"  Indexing: {pdf.name} ...")
            parsed = indexer.index_paper(str(pdf), paper_id)
            db.update_paper_pdf(
                paper_id,
                pdf_path=str(pdf),
                status=PaperStatus.INDEXED,
            )
            print(f"  OK: {pdf.name} -> {parsed.title or fname}")
            indexed += 1

            # Wait between papers to avoid rate limit
            print(f"  Waiting {DELAY_SECONDS}s ...")
            time.sleep(DELAY_SECONDS)

        except Exception as e:
            err = str(e)
            if "429" in err:
                print(f"  Rate limited on {pdf.name}, waiting 60s ...")
                time.sleep(60)
                # Retry once
                try:
                    parsed = indexer.index_paper(str(pdf), paper_id)
                    db.update_paper_pdf(
                        paper_id,
                        pdf_path=str(pdf),
                        status=PaperStatus.INDEXED,
                    )
                    print(f"  OK (retry): {pdf.name} -> {parsed.title or fname}")
                    indexed += 1
                    print(f"  Waiting {DELAY_SECONDS}s ...")
                    time.sleep(DELAY_SECONDS)
                except Exception as e2:
                    print(f"  FAILED (retry): {pdf.name}: {e2}")
                    failed += 1
            else:
                print(f"  FAILED: {pdf.name}: {e}")
                failed += 1

    print(f"\nResults: {indexed} indexed, {skipped} skipped, {failed} failed")
    db.close()


if __name__ == "__main__":
    main()
