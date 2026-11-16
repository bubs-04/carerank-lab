from alembic import context
from app.db import get_engine
from app.models import Base
from app.ingestion.models import RegistryBase

with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=[Base.metadata, RegistryBase.metadata])
    with context.begin_transaction():
        context.run_migrations()
