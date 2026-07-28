"""recompute alert country attribution against real boundaries

Revision ID: 007_recompute_affected_countries
Revises: 006_real_country_boundaries
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "007_recompute_affected_countries"
down_revision = "006_real_country_boundaries"
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
    op.execute(_read_sql("007_recompute_affected_countries.sql"))


def downgrade() -> None:
    # The previous values were derived from bounding boxes and are not worth
    # restoring; recomputation is idempotent against whatever geometry exists.
    pass
