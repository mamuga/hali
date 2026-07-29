"""OCHA COD administrative boundaries, for subnational alert geometry

Revision ID: 011_admin_boundaries
Revises: 010_pop_grid
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "011_admin_boundaries"
down_revision = "010_pop_grid"
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
    op.execute(_read_sql("011_admin_boundaries.sql"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_boundaries")
