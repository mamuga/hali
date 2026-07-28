"""PWA subscription opt-in — the third channel alongside USSD and WhatsApp."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hali.database import db
from hali.repositories.subscriptions import SubscriptionRepository, normalise_phone
from hali.schemas.alert import Language, Livelihood

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

IGAD_ISO2 = {"KE", "ET", "SO", "UG", "DJ", "ER", "SD", "SS"}


class SubscriptionCreate(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)
    channel: str = Field(default="sms", pattern="^(sms|whatsapp|both)$")
    language: Language = "sw"
    livelihood: Livelihood = "farmer"
    preferred_iso2: str | None = Field(default=None, min_length=2, max_length=2)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class OptOutRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)


@router.post("")
async def subscribe(payload: SubscriptionCreate) -> dict:
    if db.pool is None:
        raise HTTPException(status_code=503, detail="database unavailable")

    phone = normalise_phone(payload.phone_number)
    if len(phone) < 8:
        raise HTTPException(status_code=400, detail="phone_number must be in international format, e.g. +254700000000")

    iso2 = payload.preferred_iso2.upper() if payload.preferred_iso2 else None
    if iso2 and iso2 not in IGAD_ISO2:
        raise HTTPException(status_code=400, detail=f"preferred_iso2 must be one of {sorted(IGAD_ISO2)}")
    if iso2 is None and (payload.lat is None or payload.lng is None):
        raise HTTPException(status_code=400, detail="provide preferred_iso2 or a lat/lng location")

    record = await SubscriptionRepository(db.pool).upsert(
        phone_number=phone,
        channel=payload.channel,
        language=payload.language,
        livelihood=payload.livelihood,
        preferred_iso2=iso2,
        opted_in_via="pwa",
        lat=payload.lat,
        lng=payload.lng,
    )
    # Never echo the stored phone number back to a public client.
    record.pop("phone_number", None)
    record["id"] = str(record["id"])
    return record


@router.post("/opt-out")
async def opt_out(payload: OptOutRequest) -> dict:
    if db.pool is None:
        raise HTTPException(status_code=503, detail="database unavailable")
    removed = await SubscriptionRepository(db.pool).opt_out(payload.phone_number)
    return {"opted_out": removed}
