import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hali.config import settings
from hali.database import db
from hali.logging_config import configure_logging
from hali.middleware import RequestIdMiddleware
from hali.routers import admin, alerts, health, reports, spatial, subscriptions, ussd, whatsapp
from hali.scheduler import setup_scheduler

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    sched = None
    if not settings.test_mode:
        await db.connect(settings.asyncpg_dsn)
        if settings.enable_scheduler:
            sched = setup_scheduler()
            sched.start()
        if settings.ai_enabled:
            from hali.ai.processor import process_backlog

            asyncio.create_task(process_backlog(db.pool))
    try:
        yield
    finally:
        if sched is not None:
            sched.shutdown(wait=False)
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
app.include_router(spatial.router)
app.include_router(subscriptions.router)
app.include_router(ussd.router)
app.include_router(admin.router)
app.include_router(whatsapp.router)
