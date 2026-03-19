"""T023 / T037: Cross-encoder reranker using bge-reranker-v2-m3.

Reranks top-N candidates to top-K final results.
Controlled by RERANKER_ENABLED env var.
"""

from __future__ import annotations

import logging
import time

from src.core.config import settings

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading reranker model: %s", settings.reranker_model)
        _model = CrossEncoder(settings.reranker_model)
    return _model


def rerank(
    query: str,
    candidates: list[dict],  # list of {"chunk_id": int, "content": str, ...}
    top_k: int = 5,
) -> tuple[list[dict], float]:
    """
    T023: Rerank candidates using cross-encoder.

    Returns (reranked candidates[:top_k], latency_ms).
    Each candidate dict is returned with an added 'rerank_score' key.
    """
    if not settings.reranker_enabled or not candidates:
        # Return as-is, normalizing scores to 0-1 by rank position
        for i, c in enumerate(candidates[:top_k]):
            c["rerank_score"] = max(0.0, 1.0 - i * (1.0 / max(len(candidates), 1)))
        return candidates[:top_k], 0.0

    t0 = time.monotonic()
    model = _get_model()

    pairs = [(query, c["content"]) for c in candidates]
    scores = model.predict(pairs, show_progress_bar=False).tolist()

    # Attach scores
    for c, score in zip(candidates, scores):
        c["rerank_score"] = float(score)

    # Sort descending by rerank score
    candidates.sort(key=lambda c: c["rerank_score"], reverse=True)

    latency_ms = (time.monotonic() - t0) * 1000

    # Normalize to 0-1 using sigmoid
    import math

    top = candidates[:top_k]
    for c in top:
        c["rerank_score"] = 1.0 / (1.0 + math.exp(-c["rerank_score"]))

    return top, round(latency_ms, 2)
