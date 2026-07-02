from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hali.config import get_settings
from hali.database import db
from hali.logging import configure_logging
from hali.middleware import RequestIdMiddleware
from hali.routers import alerts, health, reports, ussd
from hali.scheduler import build_scheduler

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    scheduler = None
    if not settings.test_mode:
        await db.connect(settings.asyncpg_dsn)
        if settings.enable_scheduler:
            scheduler = build_scheduler(settings, db.pool)
            scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await db.close()


app = FastAPI(title="HALI API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "HALI", "service": "early-warning-api", "region": "East Africa"}


app.include_router(health.router)
app.include_router(alerts.router)
app.include_router(reports.router)
app.include_router(ussd.router)
