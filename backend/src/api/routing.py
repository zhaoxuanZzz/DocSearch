"""T051: Routing suggestion API endpoint.

POST /api/v1/routing/suggest
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from src.core.db import get_pool
from src.models.schemas import RoutingRequest
from src.skills.routing_advisor import get_routing_suggestion

router = APIRouter(tags=["routing"])
logger = logging.getLogger(__name__)

VALID_INTENTS = {"semantic", "exact", "pattern", "sequential"}


@router.post("/suggest")
async def routing_suggest(body: RoutingRequest):
    """POST /api/v1/routing/suggest — T051"""
    if body.query_intent not in VALID_INTENTS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INTENT",
                "message": f"query_intent '{body.query_intent}' is not valid. "
                f"Allowed values: {sorted(VALID_INTENTS)}",
            },
        )

    pool = await get_pool()
    try:
        return await get_routing_suggestion(pool, body)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("NO_DOCS_FOUND"):
            raise HTTPException(status_code=404, detail={"error": "NO_DOCS_FOUND", "message": msg})
        raise HTTPException(status_code=500, detail={"error": "INTERNAL_ERROR", "message": msg})
