"""seed igad country bounding boxes

Revision ID: 003_seed_igad_countries
Revises: 002_create_tables
Create Date: 2026-07-02
"""
from pathlib import Path

from alembic import op

revision = "003_seed_igad_countries"
down_revision = "002_create_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).resolve().parents[4] / "sql/migrations/003_seed_igad_countries.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DELETE FROM countries WHERE iso2 IN ('KE','ET','SO','UG','DJ','ER','SD','SS')")
