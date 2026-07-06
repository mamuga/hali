from fastapi import APIRouter

from hali.database import db

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    if db.pool is None:
        return {"status": "ok"}
    return await db.ready()


@router.get("/ready")
async def ready() -> dict:
    return await db.ready()
