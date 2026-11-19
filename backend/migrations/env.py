from alembic import context
from app.db import get_engine
from app.database_safety import postgres_connection
from app.models import Base
from app.ingestion.models import RegistryBase
import app.auth.models  # noqa: F401 — register authentication tables
import app.monitoring.models  # noqa: F401 — register monitoring tables
import app.operations.telemetry  # noqa: F401
import app.operations.models  # noqa: F401 — register durable pipeline tables


def migrate(connection):
    # Also protects older revisions when a test-looking URL has been retargeted.
    if connection.dialect.name == "postgresql":
        postgres_connection(connection)
    context.configure(connection=connection, target_metadata=[Base.metadata, RegistryBase.metadata])
    with context.begin_transaction():
        context.run_migrations()


supplied = context.config.attributes.get("connection")
if supplied is not None:
    migrate(supplied)
else:
    with get_engine().begin() as connection:
        migrate(connection)
