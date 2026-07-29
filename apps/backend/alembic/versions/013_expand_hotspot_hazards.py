"""keep emerging hotspot hazards aligned with community reports

Revision ID: 013_expand_hotspot_hazards
Revises: 012_subscription_vocabularies
Create Date: 2026-07-30
"""
from pathlib import Path

from alembic import op

revision = "013_expand_hotspot_hazards"
down_revision = "012_subscription_vocabularies"
branch_labels = None
depends_on = None


def _read_sql(name: str) -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "sql" / "migrations" / name
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"sql/migrations/{name} not found")


def upgrade() -> None:
    op.execute(_read_sql("013_expand_hotspot_hazards.sql"))


def downgrade() -> None:
    op.execute("DELETE FROM emerging_hotspots WHERE dominant_hazard NOT IN ('flood','drought','locust','cyclone','health','other')")
    op.execute("ALTER TABLE emerging_hotspots DROP CONSTRAINT IF EXISTS emerging_hotspots_dominant_hazard_check")
    op.execute(
        "ALTER TABLE emerging_hotspots ADD CONSTRAINT emerging_hotspots_dominant_hazard_check "
        "CHECK (dominant_hazard IN ('flood','drought','locust','cyclone','health','other'))"
    )
