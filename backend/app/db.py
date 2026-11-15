from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class Settings(BaseSettings):
    """Read database configuration from environment; no credential defaults."""

    database_url: str
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_engine():
    """Build one pooled SQLAlchemy engine per process."""
    return create_engine(Settings().database_url, pool_pre_ping=True)


def get_session():
    """Close each request's database session even if a request fails."""
    with Session(get_engine()) as session:
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        yield session
