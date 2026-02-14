"""Main indexer that ties together PDF parsing, embedding, and storage.

Typical usage::

    from literature_indexer.indexer import Indexer

    indexer = Indexer()
    indexer.index_paper("/path/to/paper.pdf", paper_id="abc123")
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from src.knowledge_base.models import Paper, PaperStatus, Quotation
from src.knowledge_base.vector_store import VectorStore
from src.literature_indexer.embeddings import EmbeddingModel
from src.literature_indexer.pdf_parser import ParsedPaper, parse_pdf
from src.utils.text_processing import chunk_text, detect_language

logger = logging.getLogger(__name__)

# Default chunking parameters -- tuned for scholarly prose.
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 200


class Indexer:
    """Orchestrates the full indexing pipeline for academic papers.

    The pipeline for a PDF-based paper is:

    1. Parse the PDF into structured content (title, abstract, sections, etc.)
    2. Chunk the body text into overlapping segments.
    3. Generate embeddings for each chunk (and for quotations separately).
    4. Store chunks + embeddings in ChromaDB via :class:`VectorStore`.
    5. Persist paper and quotation metadata in the SQLite database.

    When no PDF is available, :meth:`index_from_metadata` indexes whatever
    textual metadata exists (title, abstract).
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedding_model: Optional[EmbeddingModel] = None,
        db_session=None,
        chunk_size: int = _CHUNK_SIZE,
        chunk_overlap: int = _CHUNK_OVERLAP,
    ):
        """
        Args:
            vector_store: A :class:`VectorStore` instance.  If *None* a
                default instance is created.
            embedding_model: An :class:`EmbeddingModel` instance.  If *None*
                a default instance with lazy loading is created.
            db_session: An optional SQLAlchemy session (or similar) for
                persisting paper / quotation records.  When *None*, only the
                vector store is populated.
            chunk_size: Target character count per text chunk.
            chunk_overlap: Overlap in characters between consecutive chunks.
        """
        self.vector_store = vector_store or VectorStore()
        self.embedding_model = embedding_model or EmbeddingModel()
        self.db_session = db_session
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_paper(self, pdf_path: str, paper_id: str) -> ParsedPaper:
        """Run the full indexing pipeline on a PDF file.

        1. Parse the PDF.
        2. Chunk body text and generate embeddings.
        3. Store paper chunks in the vector store.
        4. Extract and store quotations.
        5. Update the SQLite record (if a db_session is configured).

        Args:
            pdf_path: Absolute or relative path to the PDF on disk.
            paper_id: Unique identifier for this paper in the system.

        Returns:
            The :class:`ParsedPaper` produced by the parser, so callers can
            inspect the structured content without re-parsing.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info("Indexing paper %s from %s", paper_id, pdf_path)

        # Step 1: Parse
        parsed = parse_pdf(str(path))
        detected_lang = detect_language(parsed.full_text or parsed.abstract or "")
        parsed.language = detected_lang

        # Step 2: Chunk
        chunks = self._build_chunks(parsed)
        if not chunks:
            logger.warning("No text chunks produced for paper %s", paper_id)
            return parsed

        # Step 3: Embed chunks
        logger.info(
            "Generating embeddings for %d chunks of paper %s",
            len(chunks),
            paper_id,
        )
        embeddings = self.embedding_model.generate_embeddings(
            chunks, batch_size=32
        )

        # Step 4: Store chunks in vector store
        metadatas = [
            {
                "paper_id": paper_id,
                "chunk_index": i,
                "language": detected_lang,
                "source": "pdf",
            }
            for i in range(len(chunks))
        ]
        self.vector_store.add_paper_chunks(
            paper_id=paper_id,
            chunks=chunks,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        logger.info(
            "Stored %d chunks for paper %s in vector store",
            len(chunks),
            paper_id,
        )

        # Step 5: Process quotations
        self._index_quotations(parsed, paper_id, detected_lang)

        # Step 6: Update SQLite metadata (if session available)
        self._update_paper_record(paper_id, parsed, pdf_path)

        return parsed

    def index_from_metadata(self, paper: Paper) -> None:
        """Index a paper using only its metadata (no PDF required).

        This is useful when the system has discovered a paper via an API
        (Semantic Scholar, OpenAlex, etc.) but hasn't downloaded the PDF yet.
        The title and abstract are embedded and stored so they are
        searchable.

        Args:
            paper: A :class:`Paper` model instance with at least *title*
                populated.  *abstract* is highly recommended.
        """
        paper_id = paper.id or str(uuid.uuid4())
        logger.info(
            "Indexing paper %s from metadata (title=%s)",
            paper_id,
            paper.title[:80],
        )

        # Build indexable text fragments from available metadata.
        texts: list[str] = []
        if paper.title:
            texts.append(paper.title)
        if paper.abstract:
            texts.append(paper.abstract)
        if paper.keywords:
            texts.append("Keywords: " + ", ".join(paper.keywords))

        if not texts:
            logger.warning(
                "No indexable text for paper %s -- skipping", paper_id
            )
            return

        # Chunk abstract if it is long; otherwise treat each text as a chunk.
        chunks: list[str] = []
        for t in texts:
            if len(t) > self.chunk_size:
                chunks.extend(
                    chunk_text(t, self.chunk_size, self.chunk_overlap)
                )
            else:
                chunks.append(t)

        detected_lang = detect_language(
            paper.abstract or paper.title
        )

        embeddings = self.embedding_model.generate_embeddings(chunks)

        metadatas = [
            {
                "paper_id": paper_id,
                "chunk_index": i,
                "language": detected_lang,
                "source": "metadata",
            }
            for i in range(len(chunks))
        ]

        self.vector_store.add_paper_chunks(
            paper_id=paper_id,
            chunks=chunks,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        logger.info(
            "Stored %d metadata chunks for paper %s", len(chunks), paper_id
        )

        # Persist status update.
        if self.db_session is not None:
            self._set_paper_status(paper_id, PaperStatus.METADATA_ONLY)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_chunks(self, parsed: ParsedPaper) -> list[str]:
        """Create text chunks from the parsed paper.

        The strategy prepends section headings to their content so each
        chunk carries contextual information about where it belongs in the
        paper structure.
        """
        parts: list[str] = []

        # Include abstract as its own chunk if present.
        if parsed.abstract:
            parts.append(f"Abstract: {parsed.abstract}")

        for section in parsed.sections:
            if section.content:
                section_text = (
                    f"{section.heading}\n\n{section.content}"
                    if section.heading
                    else section.content
                )
                parts.append(section_text)

        # If no sections were detected, fall back to full text.
        if not parts and parsed.full_text:
            parts.append(parsed.full_text)

        # Now chunk each section-level block.
        chunks: list[str] = []
        for part in parts:
            if len(part) > self.chunk_size:
                chunks.extend(
                    chunk_text(
                        part,
                        chunk_size=self.chunk_size,
                        overlap=self.chunk_overlap,
                    )
                )
            else:
                chunks.append(part)

        return chunks

    def _index_quotations(
        self,
        parsed: ParsedPaper,
        paper_id: str,
        language: str,
    ) -> None:
        """Embed and store quotations in the vector store (and optionally DB)."""
        if not parsed.quotations:
            return

        logger.info(
            "Indexing %d quotations for paper %s",
            len(parsed.quotations),
            paper_id,
        )

        for idx, eq in enumerate(parsed.quotations):
            quotation_id = f"{paper_id}_quote_{idx}"
            embedding = self.embedding_model.generate_embedding(eq.text)

            metadata = {
                "paper_id": paper_id,
                "page": str(eq.page),
                "language": language,
            }

            self.vector_store.add_quotation(
                quotation_id=quotation_id,
                text=eq.text,
                metadata=metadata,
                embedding=embedding,
            )

            # Persist to SQLite if session is available.
            if self.db_session is not None:
                quotation = Quotation(
                    id=quotation_id,
                    paper_id=paper_id,
                    text=eq.text,
                    page=str(eq.page),
                    context=eq.context,
                    language=language,
                )
                self._save_quotation(quotation)

        logger.info(
            "Stored %d quotations for paper %s",
            len(parsed.quotations),
            paper_id,
        )

    def _update_paper_record(
        self,
        paper_id: str,
        parsed: ParsedPaper,
        pdf_path: str,
    ) -> None:
        """Update the paper's SQLite record after indexing."""
        if self.db_session is None:
            return

        try:
            # Attempt to load and update existing record.
            paper = self.db_session.query(Paper).filter_by(id=paper_id).first()
            if paper is not None:
                if not paper.title and parsed.title:
                    paper.title = parsed.title
                if not paper.abstract and parsed.abstract:
                    paper.abstract = parsed.abstract
                paper.pdf_path = pdf_path
                paper.status = PaperStatus.INDEXED
                paper.language = parsed.language
                self.db_session.commit()
                logger.info("Updated paper record %s to INDEXED", paper_id)
        except Exception:
            logger.exception(
                "Failed to update paper record %s in database", paper_id
            )
            if self.db_session is not None:
                self.db_session.rollback()

    def _set_paper_status(self, paper_id: str, status: PaperStatus) -> None:
        """Set the status field on a paper record."""
        if self.db_session is None:
            return
        try:
            paper = self.db_session.query(Paper).filter_by(id=paper_id).first()
            if paper is not None:
                paper.status = status
                self.db_session.commit()
        except Exception:
            logger.exception(
                "Failed to set status for paper %s", paper_id
            )
            if self.db_session is not None:
                self.db_session.rollback()

    def _save_quotation(self, quotation: Quotation) -> None:
        """Persist a quotation to the database."""
        if self.db_session is None:
            return
        try:
            self.db_session.add(quotation)
            self.db_session.commit()
        except Exception:
            logger.exception(
                "Failed to save quotation %s", quotation.id
            )
            if self.db_session is not None:
                self.db_session.rollback()
