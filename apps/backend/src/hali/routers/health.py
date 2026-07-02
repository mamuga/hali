from fastapi import APIRouter

from hali.database import db

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    return await db.ready()
