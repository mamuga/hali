"""spatial layer + subscriber tables

Revision ID: 004_spatial_and_subscribers
Revises: 003_seed_igad_countries
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "004_spatial_and_subscribers"
down_revision = "003_seed_igad_countries"
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
    op.execute(_read_sql("004_spatial_and_subscribers.sql"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_subscriptions, emerging_hotspots CASCADE")
    op.execute("ALTER TABLE community_reports DROP CONSTRAINT IF EXISTS community_reports_channel_check")
    op.execute("ALTER TABLE community_reports DROP COLUMN IF EXISTS channel")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS population_exposed")
