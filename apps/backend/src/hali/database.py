from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self, dsn: str) -> None:
        self.pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def ready(self) -> dict[str, Any]:
        if self.pool is None:
            return {"ok": False, "database": "not_connected"}
        async with self.pool.acquire() as conn:
            postgis = await conn.fetchval("SELECT postgis_version()")
            return {"ok": True, "database": "connected", "postgis": postgis}

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        if self.pool is None:
            raise RuntimeError("database pool is not initialized")
        async with self.pool.acquire() as conn:
            yield conn


db = Database()
