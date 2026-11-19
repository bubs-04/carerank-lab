from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator, ValidationError
from sqlalchemy.exc import ArgumentError
from .secrets import resolve_secret
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class Settings(BaseSettings):
    """Read database configuration from environment; no credential defaults."""

    database_url: str | None = None
    database_url_file: str | None = None
    db_statement_timeout_ms: int = Field(30000, ge=1000, le=300000)

    @model_validator(mode="after")
    def connection_secret(self):
        self.database_url = resolve_secret("DATABASE_URL", self.database_url, self.database_url_file)
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_engine():
    """Build one pooled SQLAlchemy engine per process."""
    from sqlalchemy.engine import make_url

    try:
        settings = Settings()
        options = {}
        if make_url(settings.database_url).get_backend_name() == "postgresql":
            options = {
                "connect_timeout": 5,
                "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
            }
        return create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=options,
            **({"pool_timeout": 5} if options else {}),
        )
    except (ValueError, ValidationError, ArgumentError):
        raise RuntimeError("Database configuration invalid") from None


def get_session():
    """Close each request's database session even if a request fails."""
    with Session(get_engine()) as session:
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        yield session
