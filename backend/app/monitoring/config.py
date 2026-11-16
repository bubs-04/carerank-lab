"""Environment thresholds are persisted as immutable, content-addressed rule versions."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitoringSettings(BaseSettings):
    enabled: bool = True
    rejected_percent: float = Field(5, ge=0, le=100, allow_inf_nan=False)
    missing_percent: float = Field(5, ge=0, le=100, allow_inf_nan=False)
    duplicate_percent: float = Field(1, ge=0, le=100, allow_inf_nan=False)
    warning_rate_change: float = Field(10, ge=0, allow_inf_nan=False)
    accepted_change_percent: float = Field(20, ge=0, allow_inf_nan=False)
    membership_percent: float = Field(25, ge=0, le=100, allow_inf_nan=False)
    model_config = SettingsConfigDict(env_prefix="DQ_", extra="ignore")
