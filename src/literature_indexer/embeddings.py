"""Embedding generation via OpenRouter or ZhipuAI API.

Supports two backends (selected via EMBEDDING_BACKEND env var):
  - "openrouter" (default): Uses OpenRouter API with OpenAI-compatible
    embedding models (e.g. text-embedding-3-small).  Requires
    OPENROUTER_API_KEY env var.
  - "zhipuai": Uses GLM embedding-3 API.  Requires ZHIPUAI_API_KEY env var.

Both produce 1024-dim vectors to stay consistent with ChromaDB storage.

Environment variables:
    EMBEDDING_BACKEND     – "openrouter" or "zhipuai" (default: "openrouter")
    OPENROUTER_API_KEY    – OpenRouter API key (when backend=openrouter)
    ZHIPUAI_API_KEY       – ZhipuAI API key (when backend=zhipuai)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backend configuration
# ---------------------------------------------------------------------------

_BACKEND = os.environ.get("EMBEDDING_BACKEND", "openrouter").lower()

# OpenRouter settings
_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/embeddings"
_OPENROUTER_MODEL = "openai/text-embedding-3-large"

# ZhipuAI settings
_ZHIPUAI_API_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
_ZHIPUAI_MODEL = "embedding-3"

# Shared settings
EMBEDDING_DIM = 1024
_MAX_BATCH_SIZE = 64
_TIMEOUT = 60

# Retry settings
_MAX_RETRIES = 3
_RETRY_DELAY = 10  # seconds


def _get_api_key() -> str:
    """Return the API key for the configured backend."""
    if _BACKEND == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY environment variable is not set. "
                "Get an API key at https://openrouter.ai/"
            )
        return key
    else:
        key = os.environ.get("ZHIPUAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "ZHIPUAI_API_KEY environment variable is not set. "
                "Get an API key at https://open.bigmodel.cn/"
            )
        return key


# Keep old name for backward compatibility
MODEL_NAME = _ZHIPUAI_MODEL if _BACKEND == "zhipuai" else _OPENROUTER_MODEL


class EmbeddingModel:
    """Embedding API wrapper supporting OpenRouter and ZhipuAI backends.

    Drop-in replacement for the previous sentence-transformers based class.

    Usage::

        model = EmbeddingModel()
        vec = model.generate_embedding("Some passage text")
        vecs = model.generate_embeddings(["Text A", "Text B"])
    """

    def __init__(
        self,
        model_name: str | None = None,
        dimensions: int = EMBEDDING_DIM,
        backend: str | None = None,
    ):
        self._backend = (backend or _BACKEND).lower()
        if model_name:
            self._model_name = model_name
        elif self._backend == "openrouter":
            self._model_name = _OPENROUTER_MODEL
        else:
            self._model_name = _ZHIPUAI_MODEL
        self._dimensions = dimensions
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=_TIMEOUT)
        return self._client

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """Call the embedding API for a batch of texts.

        Includes retry logic for rate limiting (429 errors).
        """
        api_key = _get_api_key()
        client = self._get_client()

        if self._backend == "openrouter":
            url = _OPENROUTER_API_URL
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self._model_name,
                "input": texts,
                "dimensions": self._dimensions,
            }
        else:
            url = _ZHIPUAI_API_URL
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self._model_name,
                "input": texts,
                "dimensions": self._dimensions,
            }

        for attempt in range(1, _MAX_RETRIES + 1):
            response = client.post(url, headers=headers, json=payload)
            if response.status_code == 429:
                wait = _RETRY_DELAY * attempt
                logger.warning(
                    "Rate limited (attempt %d/%d), waiting %ds...",
                    attempt, _MAX_RETRIES, wait,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            break
        else:
            # All retries exhausted
            response.raise_for_status()

        data = response.json()
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
        """Generate an embedding vector for a single text string."""
        return self.generate_embeddings([text], is_query=is_query)[0]

    def generate_embeddings(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
        batch_size: int = _MAX_BATCH_SIZE,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts."""
        if not texts:
            return []

        effective_batch = min(batch_size, _MAX_BATCH_SIZE)
        all_embeddings: list[list[float]] = []

        for start in range(0, len(texts), effective_batch):
            batch = texts[start : start + effective_batch]
            logger.debug(
                "Embedding batch %d-%d of %d texts",
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
