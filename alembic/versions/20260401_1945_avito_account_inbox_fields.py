"""Add Avito inbox identification and sync state to accounts."""

from alembic import op
import sqlalchemy as sa

revision = "0003_avito_account_inbox_fields"
down_revision = "0002_module0_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Messenger API identification and sync state fields to accounts."""
    op.add_column(
        "avito_accounts",
        sa.Column("avito_user_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "avito_accounts",
        sa.Column("last_inbox_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "avito_accounts",
        sa.Column("last_inbox_sync_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "avito_accounts",
        sa.Column("last_inbox_error", sa.Text(), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_avito_accounts_avito_user_id"),
        "avito_accounts",
        ["avito_user_id"],
    )


def downgrade() -> None:
    """Remove Messenger API identification and sync state fields from accounts."""
    op.drop_constraint(
        op.f("uq_avito_accounts_avito_user_id"),
        "avito_accounts",
        type_="unique",
    )
    op.drop_column("avito_accounts", "last_inbox_error")
    op.drop_column("avito_accounts", "last_inbox_sync_status")
    op.drop_column("avito_accounts", "last_inbox_sync_at")
    op.drop_column("avito_accounts", "avito_user_id")
