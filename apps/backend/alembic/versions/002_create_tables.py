"""create hali tables

Revision ID: 002_create_tables
Revises: 001_enable_postgis
Create Date: 2026-07-02
"""
from pathlib import Path

from alembic import op

revision = "002_create_tables"
down_revision = "001_enable_postgis"
branch_labels = None
depends_on = None


def _read_sql(name: str) -> str:
    """Locate a sql/migrations mirror by walking up from this file.

    A fixed parents[N] index only resolves in a source checkout: inside the
    Docker image the revision lives at /app/alembic/versions/, which has fewer
    ancestors than apps/backend/alembic/versions/ in the repo. Walking up finds
    sql/migrations in both layouts.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "sql" / "migrations" / name
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"sql/migrations/{name} not found in any parent of {here}")


def upgrade() -> None:
    op.execute(_read_sql("002_create_tables.sql"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS community_reports, action_cards, alert_translations, alerts, raw_ingestion, countries CASCADE")
