from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .generator import SPECIALTIES, LOCATIONS


class ProviderInput(BaseModel):
    """Strict incoming provider schema."""

    model_config = ConfigDict(extra="forbid", strict=True)
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    specialty: str
    location: str


class EncounterInput(BaseModel):
    """Strict incoming event schema; only outcomes may be missing."""

    model_config = ConfigDict(extra="forbid", strict=True)
    id: int = Field(gt=0)
    provider_id: int = Field(gt=0)
    procedure: Literal["Consultation", "Diagnostic", "Follow-up"]
    risk: float = Field(ge=0, le=1, allow_inf_nan=False)
    cost: float = Field(gt=0, allow_inf_nan=False)
    outcome: Literal[0, 1] | None


def validate(providers: list[dict], encounters: list[dict]) -> dict:
    """Reject invalid batches; report missing outcomes without silently imputing them."""
    if not providers:
        raise ValueError("At least one provider is required")
    ids = set()
    for raw in providers:
        p = ProviderInput.model_validate(raw)
        if p.id in ids or p.specialty not in SPECIALTIES or p.location not in LOCATIONS:
            raise ValueError("Duplicate provider or invalid category")
        ids.add(p.id)
    seen = set()
    missing = 0
    for raw in encounters:
        e = EncounterInput.model_validate(raw)
        if e.id in seen or e.provider_id not in ids:
            raise ValueError("Duplicate encounter or unknown provider")
        seen.add(e.id)
        missing += e.outcome is None
    return {"missing_outcomes": missing, "providers": len(ids), "encounters": len(seen)}
