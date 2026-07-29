import asyncio
import json
import time

import asyncpg
import structlog

from hali.repositories.spatial import SpatialRepository
from hali.schemas.spatial import MAX_AREA_KM2

logger = structlog.get_logger(__name__)

# The compound-risk choropleth unions 521 subnational polygons against eight
# country outlines. Measured at 3.7 s against the live database — too slow to sit
# on the map's first paint, and it is recomputed identically for every visitor.
#
# The inputs change when ingestion runs, which is daily at most, so a short TTL
# is very conservative: the worst case is a choropleth up to five minutes behind
# a feed that refreshes once a day.
COMPOUND_RISK_TTL_SECONDS = 300

_compound_risk_cache: tuple[float, dict] | None = None
_compound_risk_lock = asyncio.Lock()


class SpatialService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = SpatialRepository(pool)

    async def compound_risk(self) -> dict:
        global _compound_risk_cache

        cached = _compound_risk_cache
        if cached and time.monotonic() - cached[0] < COMPOUND_RISK_TTL_SECONDS:
            return cached[1]

        # The lock stops a cold start from firing one 3.7 s union per concurrent
        # visitor; the second check covers the request that waited on it.
        async with _compound_risk_lock:
            cached = _compound_risk_cache
            if cached and time.monotonic() - cached[0] < COMPOUND_RISK_TTL_SECONDS:
                return cached[1]

            started = time.monotonic()
            result = await self.repo.compound_risk()
            _compound_risk_cache = (time.monotonic(), result)
            logger.info("spatial.compound_risk_computed", seconds=round(time.monotonic() - started, 2))
            return result

    async def countries_geojson(self, tolerance: float) -> dict:
        return await self.repo.countries_geojson(tolerance)

    async def emerging_hotspots(self) -> dict:
        return await self.repo.emerging_hotspots()

    async def analyse(self, lat: float, lng: float, lang: str) -> dict:
        return await self.repo.analyse(lat, lng, lang)

    async def query_polygon(self, geometry: dict, lang: str) -> dict:
        """Analyse a drawn area of interest.

        Raises ValueError if the area is implausibly large. Vertex and ring
        counts are bounded by the schema, but a four-point rectangle can still
        span the planet, and that one intersects every row we hold — so the
        area is measured on its own first, before any table is touched.
        """
        geojson = json.dumps(geometry)

        area_km2 = await self.repo.aoi_area_km2(geojson)
        if area_km2 is None:
            raise ValueError("geometry could not be interpreted as an area")
        if area_km2 > MAX_AREA_KM2:
            raise ValueError(
                f"area of {area_km2:,.0f} km2 exceeds the "
                f"{MAX_AREA_KM2:,} km2 limit — draw a smaller region"
            )

        return await self.repo.query_polygon(geojson, lang)
