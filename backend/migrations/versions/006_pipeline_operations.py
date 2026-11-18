"""Add durable pipeline operations without rewriting existing data."""

from alembic import op
import sqlalchemy as sa
from pathlib import Path

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pipeline_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("max_rows", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("backoff_seconds", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision >= 1 AND interval_seconds >= 10 AND max_attempts BETWEEN 1 AND 5 AND backoff_seconds >= 1 AND timeout_seconds >= 5 AND max_rows BETWEEN 1 AND 5000",
            name="ck_pipeline_policy",
        ),
    )
    op.create_index("ix_pipeline_definitions_next_run_at", "pipeline_definitions", ["next_run_at"])
    op.create_table(
        "pipeline_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pipeline_id", sa.String(36), sa.ForeignKey("pipeline_definitions.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        *[
            sa.Column(name, sa.DateTime(timezone=True), nullable=name not in ("created_at", "available_at"))
            for name in (
                "scheduled_for",
                "created_at",
                "available_at",
                "started_at",
                "finished_at",
                "heartbeat_at",
                "lease_expires_at",
                "deadline_at",
            )
        ],
        sa.Column("active_attempt_id", sa.String(36)),
        sa.Column("published_run_id", sa.String(36), sa.ForeignKey("registry_runs.id")),
        sa.Column("error_code", sa.String(100)),
        sa.UniqueConstraint("pipeline_id", "idempotency_key", name="uq_pipeline_execution_key"),
        sa.CheckConstraint(
            "status IN ('queued','running','retry_wait','succeeded','failed','cancelled','timed_out')",
            name="ck_pipeline_execution_state",
        ),
        sa.CheckConstraint(
            "revision >= 1 AND attempt_count >= 0 AND max_attempts BETWEEN 1 AND 5",
            name="ck_pipeline_execution_attempts",
        ),
    )
    op.create_index("ix_pipeline_executions_pipeline_id", "pipeline_executions", ["pipeline_id"])
    op.create_index("ix_pipeline_execution_due", "pipeline_executions", ["status", "available_at"])
    op.create_index("ix_pipeline_execution_lease", "pipeline_executions", ["status", "lease_expires_at"])
    op.create_index(
        "uq_pipeline_one_running",
        "pipeline_executions",
        ["pipeline_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
        sqlite_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "pipeline_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), sa.ForeignKey("pipeline_executions.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("ingestion_run_id", sa.String(36), sa.ForeignKey("registry_runs.id")),
        sa.UniqueConstraint("execution_id", "number", name="uq_pipeline_attempt_number"),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','interrupted','cancelled','timed_out')",
            name="ck_pipeline_attempt_state",
        ),
    )
    op.create_index("ix_pipeline_attempts_execution_id", "pipeline_attempts", ["execution_id"])
    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pipeline_id", sa.String(36), sa.ForeignKey("pipeline_definitions.id"), nullable=False),
        sa.Column("execution_id", sa.String(36), sa.ForeignKey("pipeline_executions.id")),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("auth_users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20)),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    for name in ("pipeline_id", "execution_id"):
        op.create_index("ix_pipeline_events_" + name, "pipeline_events", [name])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER pipeline_events_immutable BEFORE UPDATE OR DELETE ON pipeline_events FOR EACH ROW EXECUTE FUNCTION monitor_audit_immutable()"
        )
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER pipeline_events_no_{operation.lower()} BEFORE {operation} ON pipeline_events BEGIN SELECT RAISE(ABORT, 'pipeline events are append-only'); END"
            )


def downgrade():
    url = op.get_bind().engine.url
    if url.database != "carerank_test" and not (
        url.get_backend_name() == "sqlite" and Path(url.database or "").name == "carerank_test"
    ):
        raise RuntimeError("Migration 006 is forward-only outside carerank_test")
    for table in ("pipeline_events", "pipeline_attempts", "pipeline_executions", "pipeline_definitions"):
        op.drop_table(table)
