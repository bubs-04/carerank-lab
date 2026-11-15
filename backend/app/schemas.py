from datetime import datetime
from pydantic import BaseModel, ConfigDict


class Components(BaseModel):
    quality: float | None
    outcome: float
    cost: float
    reliability: float
    volume: float
    completeness: float
    shrinkage: float
    residual: float
    cost_ratio: float
    status: str
    version: str


class ProviderView(BaseModel):
    id: int
    name: str
    specialty: str
    location: str
    encounters: int
    observed: int
    avg_cost: float
    quality: float | None
    rank: int | None
    components: Components


class ProviderPage(BaseModel):
    items: list[ProviderView]
    total: int
    page: int
    page_size: int


class RunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    seed: int
    providers: int
    encounters: int
    seconds: float | None
    error: str | None


class Bucket(BaseModel):
    name: str
    count: int


class Analytics(BaseModel):
    providers: int
    encounters: int
    scored: int
    mean_score: float | None
    specialties: list[Bucket]
    distribution: list[Bucket]
    locations: list[str]
    latest_run: RunView | None
    last_success: RunView | None


class CohortPoint(BaseModel):
    id: int
    name: str
    avg_cost: float
    quality: float
    highlighted: bool


class QualityCost(BaseModel):
    specialty: str
    count: int
    mean_cost: float | None
    mean_score: float | None
    items: list[CohortPoint]


class SpecialtyEvidence(BaseModel):
    specialty: str
    eligible: int
    insufficient_outcomes: int
    low_completeness: int
    not_processed: int


class Evidence(BaseModel):
    total: int
    specialties: list[SpecialtyEvidence]
    completeness: list[Bucket]
