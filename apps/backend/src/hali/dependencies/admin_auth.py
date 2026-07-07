"""
Admin authentication dependency.

Uses the X-Admin-Key header with a constant-time comparison. Constant-time
comparison prevents timing attacks that could guess the key character by
character via response latency.

Usage:
  router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from hali.config import settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(
    name="X-Admin-Key",
    auto_error=False,
    description="Admin API key. Required for all /api/admin/* endpoints.",
)


async def require_admin(key: str | None = Security(_api_key_header)) -> None:
    """FastAPI dependency - raises 401/403 if the admin key is missing or wrong.

    Skips auth entirely when ADMIN_API_KEY is not configured (dev mode), but
    logs a warning so the gap is visible in server logs.
    """
    if not settings.enable_admin_endpoints:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin endpoints disabled")

    if not settings.admin_auth_enabled:
        logger.warning("Admin endpoints are unprotected - set ADMIN_API_KEY in env")
        return

    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Admin-Key header required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    expected = hashlib.sha256(settings.admin_api_key.encode()).digest()
    provided = hashlib.sha256(key.encode()).digest()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")
