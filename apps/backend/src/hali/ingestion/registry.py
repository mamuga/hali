"""Adapter registry and config-driven factory."""
from __future__ import annotations

import asyncpg

from hali.config import settings

from .base import BaseAdapter


def get_enabled_adapters(pool: asyncpg.Pool) -> list[BaseAdapter]:
    adapters: list[BaseAdapter] = []
    if settings.enable_gdacs:
        from .gdacs import GdacsAdapter

        adapters.append(GdacsAdapter(pool))
    if settings.enable_chirps:
        from .chirps import ChirpsAdapter

        adapters.append(ChirpsAdapter(pool))
    if settings.enable_gfs:
        from .gfs import GfsAdapter

        adapters.append(GfsAdapter(pool))
    if settings.enable_glofas:
        from .glofas import GloFASAdapter

        adapters.append(GloFASAdapter(pool))
    if settings.enable_icpac:
        from .icpac import IcpacAdapter

        adapters.append(IcpacAdapter(pool))
    return adapters
