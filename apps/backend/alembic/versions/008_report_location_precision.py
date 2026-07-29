"""mark reports as GPS- or country-precision so DBSCAN can ignore the latter

Revision ID: 008_report_location_precision
Revises: 007_recompute_affected_countries
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "008_report_location_precision"
down_revision = "007_recompute_affected_countries"
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
    op.execute(_read_sql("008_report_location_precision.sql"))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS community_reports_gps_recent_idx")
    op.execute(
        "ALTER TABLE community_reports "
        "DROP CONSTRAINT IF EXISTS community_reports_location_precision_check"
    )
    op.execute("ALTER TABLE community_reports DROP COLUMN IF EXISTS location_precision")
