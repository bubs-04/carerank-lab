"""Add account concurrency preconditions and indexed throttle expiry; preserve history."""

from alembic import op
import sqlalchemy as sa
from pathlib import Path

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("auth_users") as batch:
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch.create_check_constraint("ck_auth_revision", "revision >= 1")
    op.create_index("ix_auth_login_expiry", "auth_login_limits", ["window_start", "key"])


def downgrade():
    # Production/development history is forward-only. Only disposable test resets
    # may remove the concurrency precondition required by running application code.
    url = op.get_bind().engine.url
    disposable = url.database == "carerank_test" or (
        url.get_backend_name() == "sqlite" and Path(url.database or "").name == "carerank_test"
    )
    if not disposable:
        raise RuntimeError("Migration 005 is forward-only outside carerank_test")
    op.drop_index("ix_auth_login_expiry", table_name="auth_login_limits")
    with op.batch_alter_table("auth_users") as batch:
        batch.drop_constraint("ck_auth_revision", type_="check")
        batch.drop_column("revision")
