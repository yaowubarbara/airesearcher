"""ChromaDB vector store for semantic search over papers and quotations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

DEFAULT_CHROMA_PATH = Path("data/chroma")

# Embedding model used across the system (GLM embedding-3 via API)
EMBEDDING_MODEL = "embedding-3"


class VectorStore:
    """ChromaDB-backed vector store for semantic search."""

    def __init__(self, persist_dir: Path | str = DEFAULT_CHROMA_PATH):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client: Optional[chromadb.ClientAPI] = None

    @property
    def client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    def _get_or_create_collection(self, name: str) -> chromadb.Collection:
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    # --- Paper abstracts / full-text chunks ---

    def add_paper_chunks(
        self,
        paper_id: str,
        chunks: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        """Add text chunks from a paper to the papers collection."""
        collection = self._get_or_create_collection("papers")
        ids = [f"{paper_id}_chunk_{i}" for i in range(len(chunks))]
        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def search_papers(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: Optional[dict] = None,
    ) -> dict:
        """Semantic search over paper chunks."""
        collection = self._get_or_create_collection("papers")
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    # --- Quotations ---

    def add_quotation(
        self,
        quotation_id: str,
        text: str,
        metadata: dict,
        embedding: list[float],
    ) -> None:
        """Add a quotation to the quotations collection."""
        collection = self._get_or_create_collection("quotations")
        collection.add(
            ids=[quotation_id],
            documents=[text],
            metadatas=[metadata],
            embeddings=[embedding],
        )

    def search_quotations(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: Optional[dict] = None,
    ) -> dict:
        """Semantic search over quotations."""
        collection = self._get_or_create_collection("quotations")
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    # --- References ---

    def add_reference(
        self,
        ref_id: str,
        text: str,
        metadata: dict,
        embedding: list[float],
    ) -> None:
        """Add a reference to the references collection for semantic lookup."""
        collection = self._get_or_create_collection("references")
        collection.add(
            ids=[ref_id],
            documents=[text],
            metadatas=[metadata],
            embeddings=[embedding],
        )

    def search_references(
        self,
        query_embedding: list[float],
        n_results: int = 10,
    ) -> dict:
        """Semantic search over references."""
        collection = self._get_or_create_collection("references")
        return collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )

    # --- Topic proposals (for deduplication) ---

    def add_topic(
        self,
        topic_id: str,
        text: str,
        metadata: dict,
        embedding: list[float],
    ) -> None:
        collection = self._get_or_create_collection("topics")
        collection.add(
            ids=[topic_id],
            documents=[text],
            metadatas=[metadata],
            embeddings=[embedding],
        )

    def search_topics(
        self,
        query_embedding: list[float],
        n_results: int = 5,
    ) -> dict:
        collection = self._get_or_create_collection("topics")
        return collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )

    def get_collection_count(self, name: str) -> int:
        try:
            collection = self.client.get_collection(name)
            return collection.count()
        except Exception:
            return 0
