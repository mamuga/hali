"""track alert broadcast state

Revision ID: 005_alert_broadcast_tracking
Revises: 004_spatial_and_subscribers
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "005_alert_broadcast_tracking"
down_revision = "004_spatial_and_subscribers"
branch_labels = None
depends_on = None


def _read_sql(name: str) -> str:
    """See 002_create_tables._read_sql — resolves in both checkout and image layouts."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "sql" / "migrations" / name
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"sql/migrations/{name} not found in any parent of {here}")


def upgrade() -> None:
    op.execute(_read_sql("005_alert_broadcast_tracking.sql"))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS alerts_broadcast_pending_idx")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS broadcast_at")
