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


def upgrade() -> None:
    op.execute((Path(__file__).resolve().parents[4] / "sql/migrations/002_create_tables.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS community_reports, action_cards, alert_translations, alerts, raw_ingestion, countries CASCADE")
