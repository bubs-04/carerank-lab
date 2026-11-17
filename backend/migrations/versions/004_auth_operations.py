"""Frozen additive auth schema and authenticated incident attribution; no history rewriting."""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('administrator','analyst','viewer')", name="ck_auth_role"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_login_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_table(
        "auth_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("auth_users.id")),
        sa.Column("subject_user_id", sa.String(36), sa.ForeignKey("auth_users.id")),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Nullable attribution retains legacy CLI/system labels without claiming authentication.
    for table in ("monitor_alerts", "monitor_events"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("assigned_user_id", sa.String(36)))
            batch.create_foreign_key(f"fk_{table}_assignee", "auth_users", ["assigned_user_id"], ["id"])
    with op.batch_alter_table("monitor_events") as batch:
        batch.add_column(sa.Column("actor_user_id", sa.String(36)))
        batch.add_column(sa.Column("previous_assigned_to", sa.String(100)))
        batch.add_column(sa.Column("previous_assigned_user_id", sa.String(36)))
        batch.create_foreign_key("fk_monitor_events_actor", "auth_users", ["actor_user_id"], ["id"])
        batch.create_foreign_key(
            "fk_monitor_events_previous_assignee", "auth_users", ["previous_assigned_user_id"], ["id"]
        )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE TRIGGER auth_events_immutable BEFORE UPDATE OR DELETE ON auth_events
          FOR EACH ROW EXECUTE FUNCTION monitor_audit_immutable()""")
    elif op.get_bind().dialect.name == "sqlite":
        for table in ("monitor_events", "auth_events"):
            for operation in ("UPDATE", "DELETE"):
                # SQLite batch ALTER recreates tables and loses table-local triggers.
                op.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table}
                  BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""")


def downgrade():
    for table in ("monitor_alerts", "monitor_events"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_assignee", type_="foreignkey")
            batch.drop_column("assigned_user_id")
    with op.batch_alter_table("monitor_events") as batch:
        batch.drop_constraint("fk_monitor_events_actor", type_="foreignkey")
        batch.drop_constraint("fk_monitor_events_previous_assignee", type_="foreignkey")
        batch.drop_column("actor_user_id")
        batch.drop_column("previous_assigned_to")
        batch.drop_column("previous_assigned_user_id")
    for table in ("auth_events", "auth_login_limits", "auth_sessions", "auth_users"):
        op.drop_table(table)
    if op.get_bind().dialect.name == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER IF NOT EXISTS monitor_events_no_{operation.lower()} BEFORE {operation} ON monitor_events
              BEGIN SELECT RAISE(ABORT, 'monitor_events is append-only'); END""")
