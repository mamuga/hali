"""replace bounding-box country placeholders with real boundaries

Revision ID: 006_real_country_boundaries
Revises: 005_alert_broadcast_tracking
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "006_real_country_boundaries"
down_revision = "005_alert_broadcast_tracking"
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
    op.execute(_read_sql("006_real_country_boundaries.sql"))


def downgrade() -> None:
    # Restore the bounding boxes from 003 rather than leaving geometry empty.
    op.execute(_read_sql("003_seed_igad_countries.sql"))
