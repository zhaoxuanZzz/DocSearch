"""T030: Text embedding service using BAAI/bge-m3.

Provides a singleton encoder loaded lazily on first call.
Supports batch encoding and automatic truncation to 512 tokens.
"""

from __future__ import annotations

import logging

from src.core.config import settings

logger = logging.getLogger(__name__)

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", settings.embedding_model)
        _encoder = SentenceTransformer(settings.embedding_model)
    return _encoder


MAX_CHAR_LEN = 2048  # rough proxy for 512 tokens


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Encode a batch of texts to 1024-dim embeddings (bge-m3).

    Texts longer than MAX_CHAR_LEN are truncated before encoding.
    Returns a list of float lists, one per input text.
    """
    encoder = _get_encoder()
    truncated = [t[:MAX_CHAR_LEN] for t in texts]
    vectors = encoder.encode(
        truncated,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> tuple[list[float], bool]:
    """Encode a single query text.

    Returns (embedding, was_truncated).
    """
    truncated = len(text) > MAX_CHAR_LEN
    result = embed_texts([text[:MAX_CHAR_LEN]])[0]
    return result, truncated
