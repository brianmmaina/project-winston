"""Singleton sentence-transformer for semantic memory embeddings.

Uses all-MiniLM-L6-v2 (22 MB download on first use, 384-dim output).
torch + transformers are already in requirements for FinBERT, so no new
heavy dependencies are introduced.

Embeddings are L2-normalised, making cosine similarity equivalent to dot product.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
_MODEL_NAME = "all-MiniLM-L6-v2"

_model: Any = None
_lock = threading.Lock()


def _get_model() -> Any:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading embedding model %s (first run downloads ~22 MB)…", _MODEL_NAME)
                _model = SentenceTransformer(_MODEL_NAME)
                logger.info("Embedding model ready.")
    return _model


def embed(text: str) -> list[float]:
    """Return a 384-dim L2-normalised embedding for a single string."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return vec.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings in one forward pass (faster than individual calls)."""
    if not texts:
        return []
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vecs]
