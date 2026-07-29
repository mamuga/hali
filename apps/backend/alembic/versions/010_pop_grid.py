"""population grid for local zonal-statistics exposure

Revision ID: 010_pop_grid
Revises: 009_expand_domain_vocabularies
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "010_pop_grid"
down_revision = "009_expand_domain_vocabularies"
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
    op.execute(_read_sql("010_pop_grid.sql"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pop_grid")
