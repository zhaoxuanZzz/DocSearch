"""FastAPI application entry point."""

import logging
import logging.config

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.db import close_raw_pool, get_raw_pool
from src.core.middleware import http_exception_handler, request_id_middleware

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("DocSearch API starting up…")
    await get_raw_pool()  # pre-warm psycopg3 pool
    yield
    # Shutdown
    await close_raw_pool()
    logger.info("DocSearch API shut down.")


app = FastAPI(
    title="DocSearch — Agent 文档检索与 RAG 增强系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (for frontend dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID + structured logging middleware
app.middleware("http")(request_id_middleware)

# Unified HTTP exception handler
app.exception_handler(HTTPException)(http_exception_handler)
app.exception_handler(Exception)(http_exception_handler)


@app.get("/healthz", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


# Register routers (imported lazily to avoid circular imports at startup)
from src.api import documents, metrics, routing, skills  # noqa: E402

app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(skills.router, prefix="/api/v1/skills", tags=["Skills"])
app.include_router(routing.router, prefix="/api/v1/routing", tags=["Routing"])
app.include_router(metrics.router, prefix="/api/v1", tags=["Metrics"])
