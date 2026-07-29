"""widen language, livelihood and hazard vocabularies to 10/7/10

Revision ID: 009_expand_domain_vocabularies
Revises: 008_report_location_precision
Create Date: 2026-07-28
"""
from pathlib import Path

from alembic import op

revision = "009_expand_domain_vocabularies"
down_revision = "008_report_location_precision"
branch_labels = None
depends_on = None

_LANGS_BEFORE = "'sw', 'so', 'am', 'om', 'ar', 'en'"
_HAZARDS_BEFORE = "'flood', 'drought', 'locust', 'cyclone', 'health', 'other'"
_LIVELIHOODS_BEFORE = "'farmer', 'pastoralist', 'fisherfolk', 'urban'"


def _read_sql(name: str) -> str:
    """See 002_create_tables._read_sql — resolves in both checkout and image layouts."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "sql" / "migrations" / name
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"sql/migrations/{name} not found in any parent of {here}")


def upgrade() -> None:
    op.execute(_read_sql("009_expand_domain_vocabularies.sql"))


def downgrade() -> None:
    # Narrowing again only succeeds if no row uses a new value; that is the
    # correct behaviour — silently deleting alerts to fit an old constraint
    # would be worse than failing the downgrade.
    op.execute("ALTER TABLE alert_translations DROP CONSTRAINT IF EXISTS alert_translations_language_check")
    op.execute(
        f"ALTER TABLE alert_translations ADD CONSTRAINT alert_translations_language_check "
        f"CHECK (language IN ({_LANGS_BEFORE}))"
    )
    op.execute(
        "ALTER TABLE alert_translations DROP CONSTRAINT IF EXISTS alert_translations_fallback_language_check"
    )
    op.execute("ALTER TABLE alert_translations DROP COLUMN IF EXISTS fallback_language")

    op.execute("ALTER TABLE action_cards DROP CONSTRAINT IF EXISTS action_cards_language_check")
    op.execute(
        f"ALTER TABLE action_cards ADD CONSTRAINT action_cards_language_check "
        f"CHECK (language IN ({_LANGS_BEFORE}))"
    )
    op.execute("ALTER TABLE action_cards DROP CONSTRAINT IF EXISTS action_cards_livelihood_check")
    op.execute(
        f"ALTER TABLE action_cards ADD CONSTRAINT action_cards_livelihood_check "
        f"CHECK (livelihood IN ({_LIVELIHOODS_BEFORE}))"
    )

    for table in ("alerts", "community_reports"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_hazard_type_check")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_hazard_type_check "
            f"CHECK (hazard_type IN ({_HAZARDS_BEFORE}))"
        )
