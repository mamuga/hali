"""HALI ingestion package public interface."""
from __future__ import annotations

from .base import BaseAdapter
from .models import IngestionResult, SourceName
from .registry import get_enabled_adapters

__all__ = ["BaseAdapter", "IngestionResult", "SourceName", "get_enabled_adapters"]
