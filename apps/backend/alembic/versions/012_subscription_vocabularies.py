"""Widen user_subscriptions language and livelihood to the opt-in menu options

Revision ID: 012_subscription_vocabularies
Revises: 011_admin_boundaries
Create Date: 2026-07-29
"""
from pathlib import Path

from alembic import op

revision = "012_subscription_vocabularies"
down_revision = "011_admin_boundaries"
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
    op.execute(_read_sql("012_subscription_vocabularies.sql"))


def downgrade() -> None:
    """Narrow back to the original six languages and four livelihoods.

    Rows using a widened value would violate the restored constraint, so they
    are moved to the nearest original value rather than blocking the downgrade.
    """
    op.execute("UPDATE user_subscriptions SET language = 'en' WHERE language IN ('fr','ti','lg','aa')")
    op.execute(
        "UPDATE user_subscriptions SET livelihood = 'farmer' "
        "WHERE livelihood IN ('agropastoralist','trader','displaced')"
    )
    op.execute("ALTER TABLE user_subscriptions DROP CONSTRAINT IF EXISTS user_subscriptions_language_check")
    op.execute(
        "ALTER TABLE user_subscriptions ADD CONSTRAINT user_subscriptions_language_check "
        "CHECK (language IN ('sw','so','am','om','ar','en'))"
    )
    op.execute("ALTER TABLE user_subscriptions DROP CONSTRAINT IF EXISTS user_subscriptions_livelihood_check")
    op.execute(
        "ALTER TABLE user_subscriptions ADD CONSTRAINT user_subscriptions_livelihood_check "
        "CHECK (livelihood IN ('farmer','pastoralist','fisherfolk','urban'))"
    )
