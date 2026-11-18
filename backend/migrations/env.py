from alembic import context
from app.db import get_engine
from app.models import Base
from app.ingestion.models import RegistryBase
import app.auth.models  # noqa: F401 — register authentication tables
import app.monitoring.models  # noqa: F401 — register monitoring tables
import app.operations.models  # noqa: F401 — register durable pipeline tables

with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=[Base.metadata, RegistryBase.metadata])
    with context.begin_transaction():
        context.run_migrations()
