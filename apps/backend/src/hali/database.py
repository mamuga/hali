from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self, dsn: str) -> None:
        self.pool = await asyncpg.create_pool(dsn=self._asyncpg_dsn(dsn), min_size=1, max_size=10)

    def _asyncpg_dsn(self, dsn: str) -> str:
        return dsn.replace("postgresql+asyncpg://", "postgresql://")

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def ready(self) -> dict[str, Any]:
        if self.pool is None:
            return {"status": "ok", "db": "not_connected"}
        async with self.pool.acquire() as conn:
            postgres_version = await conn.fetchval("SELECT version()")
            postgis_version = await conn.fetchval("SELECT postgis_version()")
            return {
                "status": "ok",
                "db": "connected",
                "postgres_version": postgres_version,
                "postgis_version": postgis_version,
            }

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        if self.pool is None:
            raise RuntimeError("database pool is not initialized")
        async with self.pool.acquire() as conn:
            yield conn


db = Database()


def get_pool() -> asyncpg.Pool:
    if db.pool is None:
        raise RuntimeError("database pool is not initialized")
    return db.pool
