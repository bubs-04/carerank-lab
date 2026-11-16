from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DATASET = "mj5m-pzi6"
BASE = "https://data.cms.gov/provider-data"
METADATA_URL = f"{BASE}/api/1/metastore/schemas/dataset/items/{DATASET}?show-reference-ids"
DICTIONARY_URL = f"{BASE}/sites/default/files/data_dictionaries/physician/DOC_Data_Dictionary.pdf"
POLICY = "cms-registry-v1"


class IngestionSettings(BaseSettings):
    """Resource bounds, not arbitrary network destinations; CLI overrides row limit."""

    model_config = SettingsConfigDict(env_prefix="CMS_", extra="ignore")
    max_rows: int = Field(1000, ge=1, le=5000)
    timeout_seconds: float = Field(20, ge=1, le=60)
    deadline_seconds: float = Field(120, ge=10, le=300)
    max_bytes: int = Field(8_000_000, ge=1000, le=25_000_000)
    attempts: int = Field(3, ge=1, le=4)
