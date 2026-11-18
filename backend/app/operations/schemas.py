from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..auth.dependencies import settings


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    source: Literal["cms", "fixture_a", "fixture_b", "fixture_retry"]
    max_rows: int = Field(5, ge=1, le=5000)
    enabled: bool = False
    interval_seconds: int = Field(3600, ge=10, le=2592000)
    max_attempts: int = Field(3, ge=1, le=5)
    backoff_seconds: int = Field(5, ge=1, le=3600)
    timeout_seconds: int = Field(120, ge=5, le=600)

    @model_validator(mode="after")
    def safe_source(self):
        if self.source != "cms" and self.max_rows > 5:
            raise ValueError("Fixtures contain at most five rows")
        if self.source == "fixture_retry" and settings().app_env != "development":
            raise ValueError("Recovery demonstration requires development mode")
        return self


class PipelineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    name: str | None = None
    source: Literal["cms", "fixture_a", "fixture_b", "fixture_retry"] | None = None
    max_rows: int | None = None
    enabled: bool | None = None
    interval_seconds: int | None = None
    max_attempts: int | None = None
    backoff_seconds: int | None = None
    timeout_seconds: int | None = None


class Trigger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID


class Retry(Trigger):
    expected_revision: int = Field(ge=1)


class Cancel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)
