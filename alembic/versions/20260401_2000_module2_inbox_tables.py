"""Add Module 2 inbox tables."""

from alembic import op
import sqlalchemy as sa

revision = "0004_module2_inbox_tables"
down_revision = "0003_avito_account_inbox_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the read-only inbox data tables for Module 2."""
    op.create_table(
        "avito_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["avito_accounts.id"],
            name=op.f("fk_avito_clients_account_id_avito_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_avito_clients")),
        sa.UniqueConstraint(
            "account_id",
            "external_user_id",
            name=op.f("uq_avito_clients_account_id"),
        ),
    )

    op.create_table(
        "avito_listings_ref",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("external_item_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("price_string", sa.String(length=255), nullable=True),
        sa.Column("status_id", sa.String(length=64), nullable=True),
        sa.Column("owner_external_user_id", sa.String(length=255), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["avito_accounts.id"],
            name=op.f("fk_avito_listings_ref_account_id_avito_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_avito_listings_ref")),
        sa.UniqueConstraint(
            "account_id",
            "external_item_id",
            name=op.f("uq_avito_listings_ref_account_id"),
        ),
    )

    op.create_table(
        "avito_chats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("external_chat_id", sa.String(length=255), nullable=False),
        sa.Column("chat_type", sa.String(length=32), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=True),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("external_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_message_direction", sa.String(length=32), nullable=True),
        sa.Column("last_message_type", sa.String(length=32), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["avito_accounts.id"],
            name=op.f("fk_avito_chats_account_id_avito_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["avito_clients.id"],
            name=op.f("fk_avito_chats_client_id_avito_clients"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["avito_listings_ref.id"],
            name=op.f("fk_avito_chats_listing_id_avito_listings_ref"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_avito_chats")),
        sa.UniqueConstraint(
            "account_id",
            "external_chat_id",
            name=op.f("uq_avito_chats_account_id"),
        ),
    )
    op.create_index(
        "ix_avito_chats_account_id_last_message_at",
        "avito_chats",
        ["account_id", "last_message_at"],
        unique=False,
    )
    op.create_index(
        "ix_avito_chats_account_id_external_updated_at",
        "avito_chats",
        ["account_id", "external_updated_at"],
        unique=False,
    )

    op.create_table(
        "avito_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=False),
        sa.Column("author_external_id", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("quote_json", sa.JSON(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["avito_accounts.id"],
            name=op.f("fk_avito_messages_account_id_avito_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["avito_chats.id"],
            name=op.f("fk_avito_messages_chat_id_avito_chats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_avito_messages")),
        sa.UniqueConstraint(
            "account_id",
            "external_message_id",
            name=op.f("uq_avito_messages_account_id"),
        ),
    )
    op.create_index(
        "ix_avito_messages_chat_id_external_created_at",
        "avito_messages",
        ["chat_id", "external_created_at"],
        unique=False,
    )
    op.create_index(
        "ix_avito_messages_account_id_external_created_at",
        "avito_messages",
        ["account_id", "external_created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the read-only inbox data tables for Module 2."""
    op.drop_index(
        "ix_avito_messages_account_id_external_created_at",
        table_name="avito_messages",
    )
    op.drop_index(
        "ix_avito_messages_chat_id_external_created_at",
        table_name="avito_messages",
    )
    op.drop_table("avito_messages")

    op.drop_index(
        "ix_avito_chats_account_id_external_updated_at",
        table_name="avito_chats",
    )
    op.drop_index(
        "ix_avito_chats_account_id_last_message_at",
        table_name="avito_chats",
    )
    op.drop_table("avito_chats")

    op.drop_table("avito_listings_ref")
    op.drop_table("avito_clients")
