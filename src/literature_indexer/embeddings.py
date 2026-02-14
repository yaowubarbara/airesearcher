"""Embedding generation using GLM embedding-3 API (ZhipuAI).

Replaces the previous local sentence-transformers approach to avoid
the ~9GB disk footprint of torch + nvidia + the E5-large model weights.

The GLM embedding-3 model produces 2048-dim vectors by default.  We
request 1024-dim output to stay consistent with the previous E5-large
dimensionality and to reduce storage in ChromaDB.

Environment variable required:
    ZHIPUAI_API_KEY  –  your ZhipuAI platform API key.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# GLM embedding API endpoint
_API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"

# Model name on the ZhipuAI platform
MODEL_NAME = "embedding-3"

# Dimension of the returned vectors (embedding-3 supports 256 / 1024 / 2048)
EMBEDDING_DIM = 1024

# Maximum texts per single API call (ZhipuAI batch limit)
_MAX_BATCH_SIZE = 64

# HTTP timeout in seconds
_TIMEOUT = 60


def _get_api_key() -> str:
    """Return the ZhipuAI API key from environment."""
    key = os.environ.get("ZHIPUAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "ZHIPUAI_API_KEY environment variable is not set. "
            "Get an API key at https://open.bigmodel.cn/"
        )
    return key


class EmbeddingModel:
    """GLM embedding-3 API wrapper.

    Drop-in replacement for the previous sentence-transformers based class.

    Usage::

        model = EmbeddingModel()
        vec = model.generate_embedding("Some passage text")
        vecs = model.generate_embeddings(["Text A", "Text B"])
    """

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        dimensions: int = EMBEDDING_DIM,
    ):
        self._model_name = model_name
        self._dimensions = dimensions
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=_TIMEOUT)
        return self._client

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Call the GLM embedding API for a batch of texts.

        Args:
            texts: Up to _MAX_BATCH_SIZE texts.

        Returns:
            List of embedding vectors in the same order as *texts*.
        """
        api_key = _get_api_key()
        client = self._get_client()

        response = client.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model_name,
                "input": texts,
                "dimensions": self._dimensions,
            },
        )
        response.raise_for_status()

        data = response.json()
        # Response data[i] has {"index": i, "embedding": [...]}
        # Sort by index to guarantee order matches input order.
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    # ------------------------------------------------------------------
    # Public API (same interface as the old sentence-transformers class)
    # ------------------------------------------------------------------

    def generate_embedding(
        self,
        text: str,
        *,
        is_query: bool = False,
    ) -> list[float]:
        """Generate an embedding vector for a single text string.

        Args:
            text: The input text to embed.
            is_query: Accepted for API compatibility but not used by GLM.

        Returns:
            A list of floats representing the embedding vector.
        """
        return self.generate_embeddings([text], is_query=is_query)[0]

    def generate_embeddings(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
        batch_size: int = _MAX_BATCH_SIZE,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts.

        Args:
            texts: List of input texts to embed.
            is_query: Accepted for API compatibility but not used by GLM.
            batch_size: Number of texts per API call (max 64).
            show_progress: Ignored (kept for interface compatibility).

        Returns:
            A list of embedding vectors, one per input text.
        """
        if not texts:
            return []

        effective_batch = min(batch_size, _MAX_BATCH_SIZE)
        all_embeddings: list[list[float]] = []

        for start in range(0, len(texts), effective_batch):
            batch = texts[start : start + effective_batch]
            logger.debug(
                "Embedding batch %d–%d of %d texts",
                start,
                start + len(batch),
                len(texts),
            )
            all_embeddings.extend(self._call_api(batch))

        return all_embeddings

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        return self._dimensions


# ---------------------------------------------------------------------------
# Module-level convenience functions (use a shared singleton instance).
# ---------------------------------------------------------------------------

_default_model: Optional[EmbeddingModel] = None


def _get_default_model() -> EmbeddingModel:
    global _default_model
    if _default_model is None:
        _default_model = EmbeddingModel()
    return _default_model


def generate_embedding(text: str, *, is_query: bool = False) -> list[float]:
    """Generate an embedding for a single text using the default model."""
    return _get_default_model().generate_embedding(text, is_query=is_query)


def generate_embeddings(
    texts: list[str],
    *,
    is_query: bool = False,
    batch_size: int = _MAX_BATCH_SIZE,
    show_progress: bool = False,
) -> list[list[float]]:
    """Generate embeddings for a batch of texts using the default model."""
    return _get_default_model().generate_embeddings(
        texts,
        is_query=is_query,
        batch_size=batch_size,
        show_progress=show_progress,
    )
