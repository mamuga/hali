import asyncpg

from hali.repositories.spatial import SpatialRepository


class SpatialService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = SpatialRepository(pool)

    async def compound_risk(self) -> dict:
        return await self.repo.compound_risk()

    async def emerging_hotspots(self) -> dict:
        return await self.repo.emerging_hotspots()

    async def analyse(self, lat: float, lng: float, lang: str) -> dict:
        return await self.repo.analyse(lat, lng, lang)
