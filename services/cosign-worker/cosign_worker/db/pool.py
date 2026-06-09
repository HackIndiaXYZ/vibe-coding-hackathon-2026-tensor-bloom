"""asyncpg connection pool."""

from __future__ import annotations

import asyncio
import socket

import asyncpg
import structlog

log = structlog.get_logger(__name__)


def normalize_dsn(url: str) -> str:
    # asyncpg wants postgres://; strip any sqlalchemy-style +driver and unknown args.
    return url.replace("postgresql+asyncpg://", "postgres://").replace(
        "postgresql://", "postgres://"
    )


async def create_pool(database_url: str, *, attempts: int = 15, delay_s: float = 1.0) -> asyncpg.Pool:
    """Create the pool, retrying transient startup failures.

    On a fresh compose container the embedded DNS (127.0.0.11) and Postgres may
    not be reachable for the first moments after start, even with depends_on:
    healthy — the dependent's network namespace is still settling. Retry briefly.
    """
    dsn = normalize_dsn(database_url)
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10, command_timeout=30)
        except (socket.gaierror, OSError, asyncpg.PostgresError) as e:
            last = e
            log.warning("db not ready, retrying", attempt=i + 1, err=str(e))
            await asyncio.sleep(delay_s)
    raise last or RuntimeError("could not create pool")
