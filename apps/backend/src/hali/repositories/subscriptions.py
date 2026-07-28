"""Subscriber storage for SMS / WhatsApp alerting."""
from __future__ import annotations

import json
import re
from typing import Any

import asyncpg

# Severity ordering used to honour each subscriber's min_severity setting.
SEVERITY_RANK = {"green": 1, "orange": 2, "red": 3}


def normalise_phone(phone: str) -> str:
    """Normalise to E.164 so the same person is one row across channels.

    Africa's Talking sends `+254700000000`; the WhatsApp Cloud API sends
    `254700000000`. Without this they would create two subscriptions and the
    person would be messaged twice.
    """
    cleaned = re.sub(r"[^\d+]", "", phone or "")
    if not cleaned:
        return ""
    if cleaned.startswith("+"):
        return "+" + re.sub(r"\D", "", cleaned[1:])
    return "+" + re.sub(r"\D", "", cleaned)


class SubscriptionRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def upsert(
        self,
        phone_number: str,
        channel: str,
        language: str,
        livelihood: str,
        preferred_iso2: str | None,
        opted_in_via: str,
        lat: float | None = None,
        lng: float | None = None,
    ) -> dict[str, Any]:
        """Create or refresh a subscription. Re-subscribing clears any opt-out."""
        sql = """
        INSERT INTO user_subscriptions
            (phone_number, channel, language, livelihood, preferred_iso2, opted_in_via, location)
        VALUES ($1, $2, $3, $4, $5, $6,
                CASE WHEN $7::float8 IS NULL OR $8::float8 IS NULL
                     THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint($8, $7), 4326) END)
        ON CONFLICT (phone_number) DO UPDATE SET
            channel = EXCLUDED.channel,
            language = EXCLUDED.language,
            livelihood = EXCLUDED.livelihood,
            preferred_iso2 = COALESCE(EXCLUDED.preferred_iso2, user_subscriptions.preferred_iso2),
            location = COALESCE(EXCLUDED.location, user_subscriptions.location),
            opted_in = TRUE,
            opted_in_at = NOW(),
            last_active = NOW()
        RETURNING id, phone_number, channel, language, livelihood, preferred_iso2, opted_in
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, normalise_phone(phone_number), channel, language, livelihood, preferred_iso2, opted_in_via, lat, lng)
        return dict(row)

    async def opt_out(self, phone_number: str) -> bool:
        """Mark a subscriber opted out. The row is kept so history survives."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE user_subscriptions SET opted_in = FALSE, last_active = NOW() WHERE phone_number = $1",
                normalise_phone(phone_number),
            )
        return result.endswith("1")

    async def get(self, phone_number: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, phone_number, channel, language, livelihood, preferred_iso2,
                       opted_in, min_severity, convo_state, convo_data,
                       ST_Y(location) AS lat, ST_X(location) AS lng
                FROM user_subscriptions WHERE phone_number = $1
                """,
                normalise_phone(phone_number),
            )
        if row is None:
            return None
        record = dict(row)
        if isinstance(record.get("convo_data"), str):
            record["convo_data"] = json.loads(record["convo_data"])
        return record

    async def set_convo_state(self, phone_number: str, state: str | None, data: dict[str, Any] | None = None) -> None:
        """Persist WhatsApp conversation position.

        Uses a placeholder row (opted_in = FALSE) so an abandoned opt-in never
        leaves someone subscribed to messages they did not confirm.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_subscriptions (phone_number, channel, opted_in, opted_in_via, convo_state, convo_data)
                VALUES ($1, 'whatsapp', FALSE, 'whatsapp', $2, $3::jsonb)
                ON CONFLICT (phone_number) DO UPDATE SET
                    convo_state = EXCLUDED.convo_state,
                    convo_data = EXCLUDED.convo_data,
                    last_active = NOW()
                """,
                normalise_phone(phone_number),
                state,
                json.dumps(data or {}),
            )

    async def matching_subscribers(self, alert_id: Any) -> list[dict[str, Any]]:
        """Subscribers who should receive this alert.

        Real spatial targeting: a subscriber matches when their GPS point falls
        inside the alert polygon, or when their chosen country is one the alert
        affects. Their min_severity threshold still has to be met.
        """
        sql = """
        SELECT s.phone_number, s.channel, s.language, s.livelihood
        FROM user_subscriptions s
        JOIN alerts a ON a.id = $1
        WHERE s.opted_in
          AND (
                (s.location IS NOT NULL AND ST_Intersects(s.location, a.geom))
             OR (s.preferred_iso2 IS NOT NULL AND s.preferred_iso2 = ANY(a.affected_countries))
          )
          AND CASE s.min_severity
                WHEN 'green'  THEN TRUE
                WHEN 'orange' THEN a.severity IN ('orange', 'red')
                WHEN 'red'    THEN a.severity = 'red'
                ELSE TRUE
              END
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, alert_id)
        return [dict(row) for row in rows]

    async def stats(self) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            totals = await conn.fetchrow(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE opted_in) AS opted_in,
                       COUNT(*) FILTER (WHERE NOT opted_in) AS opted_out,
                       COUNT(*) FILTER (WHERE location IS NOT NULL) AS with_location
                FROM user_subscriptions
                """
            )
            by = {}
            for field in ("channel", "language", "livelihood", "preferred_iso2", "opted_in_via"):
                rows = await conn.fetch(
                    f"SELECT {field} AS key, COUNT(*) AS count FROM user_subscriptions WHERE opted_in GROUP BY {field} ORDER BY count DESC"  # noqa: S608 - field is from a fixed literal tuple
                )
                by[field] = {(row["key"] or "unknown"): row["count"] for row in rows}
        return {**dict(totals), "by": by}
