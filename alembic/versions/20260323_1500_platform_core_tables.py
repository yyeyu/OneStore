"""Platform core tables aligned with the simplified schema."""

from alembic import op
import sqlalchemy as sa

# Kept unchanged to avoid breaking already-initialized local Alembic histories.
revision = "0002_module0_core_tables"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create simplified platform core tables."""
    op.create_table(
        "avito_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.UniqueConstraint("client_id", name=op.f("uq_avito_accounts_client_id")),
    )

    op.create_table(
        "modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modules")),
        sa.UniqueConstraint("name", name=op.f("uq_modules_name")),
    )

    op.create_table(
        "module_account_settings",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["modules.id"],
            name=op.f("fk_module_account_settings_module_id_modules"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "account_id",
            "module_id",
            name=op.f("pk_module_account_settings"),
        ),
    )

    op.create_table(
        "module_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=128), nullable=False),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["modules.id"],
            name=op.f("fk_module_runs_module_id_modules"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_module_runs")),
    )
    op.create_index("ix_module_runs_account_id", "module_runs", ["account_id"], unique=False)
    op.create_index("ix_module_runs_module_id", "module_runs", ["module_id"], unique=False)
    op.create_index(
        "ix_module_runs_status_started_at",
        "module_runs",
        ["status", "started_at"],
        unique=False,
    )

    op.create_table(
        "action_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("action_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
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
    op.create_index("ix_action_logs_account_id", "action_logs", ["account_id"], unique=False)
    op.create_index("ix_action_logs_run_id", "action_logs", ["run_id"], unique=False)


def downgrade() -> None:
    """Drop simplified platform core tables."""
    op.drop_index("ix_action_logs_run_id", table_name="action_logs")
    op.drop_index("ix_action_logs_account_id", table_name="action_logs")
    op.drop_table("action_logs")

    op.drop_index("ix_module_runs_status_started_at", table_name="module_runs")
    op.drop_index("ix_module_runs_module_id", table_name="module_runs")
    op.drop_index("ix_module_runs_account_id", table_name="module_runs")
    op.drop_table("module_runs")

    op.drop_table("module_account_settings")
    op.drop_table("modules")
    op.drop_table("avito_accounts")
