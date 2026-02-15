#!/usr/bin/env python3
"""Clear ChromaDB and re-index all PDFs with OpenRouter embeddings.

Usage:
    export OPENROUTER_API_KEY="sk-or-v1-..."
    export EMBEDDING_BACKEND="openrouter"
    python3 -u reindex_all.py
"""

import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.knowledge_base.db import Database
from src.knowledge_base.models import PaperStatus
from src.knowledge_base.vector_store import VectorStore, DEFAULT_CHROMA_PATH
from src.literature_indexer.indexer import Indexer

DELAY_SECONDS = 3  # OpenRouter has much higher rate limits


def main():
    print("=== Re-indexing all PDFs with OpenRouter embeddings ===\n")

    # Step 1: Clear ChromaDB
    chroma_path = Path(DEFAULT_CHROMA_PATH)
    if chroma_path.exists():
        print(f"Clearing ChromaDB at {chroma_path} ...")
        shutil.rmtree(chroma_path)
        chroma_path.mkdir(parents=True, exist_ok=True)
        print("  Done.\n")

    # Step 2: Reset paper statuses in SQLite
    db = Database()
    print("Resetting paper statuses to DISCOVERED ...")
    conn = db.conn
    conn.execute(
        "UPDATE papers SET status = ? WHERE status IN (?, ?, ?)",
        (
            PaperStatus.DISCOVERED.value,
            PaperStatus.INDEXED.value,
            PaperStatus.PDF_DOWNLOADED.value,
            PaperStatus.ANALYZED.value,
        ),
    )
    conn.commit()
    # Count papers with PDFs
    row = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE pdf_path IS NOT NULL AND pdf_path != ''"
    ).fetchone()
    print(f"  Papers with PDF paths: {row[0]}\n")

    # Step 3: Re-index all PDFs
    vs = VectorStore()
    indexer = Indexer(vector_store=vs)
    folder = Path("data/papers")
    pdfs = sorted(folder.glob("*.pdf"))

    print(f"Found {len(pdfs)} PDFs to index\n")

    indexed = 0
    failed = 0

    for i, pdf in enumerate(pdfs, 1):
        fname = pdf.stem

        # Try DOI-based matching
        paper_id = None
        doi_candidate = re.sub(r"_", "/", fname, count=1)
        paper = db.get_paper_by_doi(doi_candidate)
        if paper:
            paper_id = paper.id

        if not paper_id:
            paper_id = str(uuid.uuid4())

        try:
            print(f"  [{i}/{len(pdfs)}] Indexing: {pdf.name} ...")
            parsed = indexer.index_paper(str(pdf), paper_id)
            db.update_paper_pdf(
                paper_id,
                pdf_path=str(pdf),
                status=PaperStatus.INDEXED,
            )
            title = (parsed.title or fname)[:60]
            print(f"    OK -> {title}")
            indexed += 1

            # Small delay between papers
            if i < len(pdfs):
                time.sleep(DELAY_SECONDS)

        except Exception as e:
            err = str(e)
            print(f"    FAILED: {err[:120]}")
            if "429" in err:
                print(f"    Rate limited, waiting 30s ...")
                time.sleep(30)
                # Retry once
                try:
                    parsed = indexer.index_paper(str(pdf), paper_id)
                    db.update_paper_pdf(
                        paper_id,
                        pdf_path=str(pdf),
                        status=PaperStatus.INDEXED,
                    )
                    title = (parsed.title or fname)[:60]
                    print(f"    OK (retry) -> {title}")
                    indexed += 1
                    time.sleep(DELAY_SECONDS)
                except Exception as e2:
                    print(f"    FAILED (retry): {str(e2)[:120]}")
                    failed += 1
            else:
                failed += 1

    print(f"\n=== Results: {indexed} indexed, {failed} failed ===")
    db.close()


if __name__ == "__main__":
    main()
