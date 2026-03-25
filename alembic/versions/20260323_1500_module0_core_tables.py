"""Module 0 stage 0.3 technical tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_module0_core_tables"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Module 0 technical tables only."""
    op.create_table(
        "avito_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("external_account_id", sa.String(length=128), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_avito_accounts")),
        sa.UniqueConstraint("account_code", name=op.f("uq_avito_accounts_account_code")),
        sa.UniqueConstraint(
            "external_account_id", name=op.f("uq_avito_accounts_external_account_id")
        ),
    )

    op.create_table(
        "module_account_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("module_name", sa.String(length=64), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            name=op.f("fk_module_account_settings_account_id_avito_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_module_account_settings")),
        sa.UniqueConstraint(
            "account_id",
            "module_name",
            name="uq_module_account_settings_account_id_module_name",
        ),
    )
    op.create_index(
        op.f("ix_module_account_settings_account_id"),
        "module_account_settings",
        ["account_id"],
        unique=False,
    )

    op.create_table(
        "module_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_name", sa.String(length=64), nullable=False),
        sa.Column("job_name", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["avito_accounts.id"],
            name=op.f("fk_module_runs_account_id_avito_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_module_runs")),
    )
    op.create_index(op.f("ix_module_runs_account_id"), "module_runs", ["account_id"], unique=False)
    op.create_index(
        "ix_module_runs_module_name_job_name",
        "module_runs",
        ["module_name", "job_name"],
        unique=False,
    )
    op.create_index(
        "ix_module_runs_status_started_at",
        "module_runs",
        ["status", "started_at"],
        unique=False,
    )

    op.create_table(
        "action_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_name", sa.String(length=64), nullable=False),
        sa.Column("action_name", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=191), nullable=True),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["avito_accounts.id"],
            name=op.f("fk_action_logs_account_id_avito_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["module_runs.id"],
            name=op.f("fk_action_logs_run_id_module_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_logs")),
    )
    op.create_index(op.f("ix_action_logs_account_id"), "action_logs", ["account_id"], unique=False)
    op.create_index(
        "ix_action_logs_module_name_action_name",
        "action_logs",
        ["module_name", "action_name"],
        unique=False,
    )
    op.create_index(op.f("ix_action_logs_run_id"), "action_logs", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_action_logs_idempotency_key"),
        "action_logs",
        ["idempotency_key"],
        unique=False,
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=191), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(length=128), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["avito_accounts.id"],
            name=op.f("fk_idempotency_keys_account_id_avito_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["module_runs.id"],
            name=op.f("fk_idempotency_keys_run_id_module_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_keys_scope_key"),
    )
    op.create_index(
        op.f("ix_idempotency_keys_account_id"),
        "idempotency_keys",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_idempotency_keys_status_locked_until",
        "idempotency_keys",
        ["status", "locked_until"],
        unique=False,
    )
    op.create_index(op.f("ix_idempotency_keys_run_id"), "idempotency_keys", ["run_id"], unique=False)


def downgrade() -> None:
    """Drop Module 0 technical tables."""
    op.drop_index(op.f("ix_idempotency_keys_run_id"), table_name="idempotency_keys")
    op.drop_index(
        "ix_idempotency_keys_status_locked_until",
        table_name="idempotency_keys",
    )
    op.drop_index(op.f("ix_idempotency_keys_account_id"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index(op.f("ix_action_logs_idempotency_key"), table_name="action_logs")
    op.drop_index(op.f("ix_action_logs_run_id"), table_name="action_logs")
    op.drop_index("ix_action_logs_module_name_action_name", table_name="action_logs")
    op.drop_index(op.f("ix_action_logs_account_id"), table_name="action_logs")
    op.drop_table("action_logs")

    op.drop_index("ix_module_runs_status_started_at", table_name="module_runs")
    op.drop_index("ix_module_runs_module_name_job_name", table_name="module_runs")
    op.drop_index(op.f("ix_module_runs_account_id"), table_name="module_runs")
    op.drop_table("module_runs")

    op.drop_index(
        op.f("ix_module_account_settings_account_id"),
        table_name="module_account_settings",
    )
    op.drop_table("module_account_settings")

    op.drop_table("avito_accounts")
