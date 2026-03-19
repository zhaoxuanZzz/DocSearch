from contextlib import asynccontextmanager
from typing import AsyncGenerator

import psycopg
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings

# SQLAlchemy async engine
engine = create_async_engine(
    settings.database_url.replace("postgresql+psycopg://", "postgresql+psycopg://"),
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Raw psycopg3 async pool for direct SQL (vector search, BM25)
_raw_pool: AsyncConnectionPool | None = None


async def _configure_connection(conn: psycopg.AsyncConnection) -> None:
    """Set per-session PostgreSQL performance parameters."""
    from pgvector.psycopg import register_vector_async
    await register_vector_async(conn)
    await conn.execute("SET work_mem = '256MB'")
    try:
        await conn.execute(f"SET hnsw.ef_search = {settings.hnsw_ef_search}")
    except Exception:
        pass  # pgvector GUC may not be available in all PG versions
    await conn.rollback()  # Clear implicit transaction left by SET statements


async def get_raw_pool() -> AsyncConnectionPool:
    global _raw_pool
    if _raw_pool is None:
        _raw_pool = AsyncConnectionPool(
            conninfo=settings.database_url.replace("postgresql+psycopg://", "postgresql://"),
            min_size=2,
            max_size=settings.db_pool_size,
            configure=_configure_connection,
            open=False,
        )
        await _raw_pool.open()
    return _raw_pool


async def close_raw_pool() -> None:
    global _raw_pool
    if _raw_pool is not None:
        await _raw_pool.close()
        _raw_pool = None


# Alias for backwards compatibility with callers that import get_pool
get_pool = get_raw_pool
