"""Add worker presence and bounded-history query indexes; preserve all prior evidence."""

from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pipeline_workers",
        sa.Column("worker_id", sa.String(100), primary_key=True),
        sa.Column("instance_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("execution_id", sa.String(36)),
    )
    op.create_index("ix_pipeline_workers_instance_id", "pipeline_workers", ["instance_id"])
    op.create_index("ix_pipeline_workers_heartbeat", "pipeline_workers", ["heartbeat_at"])
    op.create_index("ix_pipeline_execution_finished", "pipeline_executions", ["finished_at"])
    op.create_index("ix_pipeline_attempt_started", "pipeline_attempts", ["started_at"])
    op.create_index("ix_pipeline_history", "pipeline_executions", ["pipeline_id", "created_at", "id"])


def downgrade():
    url = op.get_bind().engine.url
    if url.database != "carerank_test" and not (
        url.get_backend_name() == "sqlite" and Path(url.database or "").name == "carerank_test"
    ):
        raise RuntimeError("Migration 007 is forward-only outside carerank_test")
    op.drop_index("ix_pipeline_history", "pipeline_executions")
    op.drop_index("ix_pipeline_attempt_started", "pipeline_attempts")
    op.drop_index("ix_pipeline_execution_finished", "pipeline_executions")
    op.drop_table("pipeline_workers")
