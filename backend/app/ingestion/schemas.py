from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceView(ORMModel):
    id: str
    dataset_id: str
    mode: str
    title: str
    url: str


class RunView(ORMModel):
    id: str
    source_id: str
    snapshot_id: str | None
    started_at: datetime
    finished_at: datetime | None
    seconds: float | None
    status: str
    requested: int
    received: int | None
    valid: int | None
    rejected: int | None
    warnings: int | None
    error_code: str | None
    provenance: dict


class SnapshotView(ORMModel):
    id: str
    source_id: str
    created_at: datetime
    checksum: str
    scope_hash: str
    scope: dict
    provenance: dict
    policy: str
    received: int
    valid: int
    rejected: int
    warnings: int
    finding_counts: dict[str, int]


class StatusView(BaseModel):
    sources: list[SourceView]
    latest_attempt: RunView | None
    latest_success: RunView | None
    snapshot_count: int


class SnapshotPage(BaseModel):
    items: list[SnapshotView]
    total: int
    page: int
    page_size: int


class RunPage(BaseModel):
    items: list[RunView]
    total: int
    page: int
    page_size: int


class FindingView(ORMModel):
    row_number: int | None
    severity: str
    code: str
    field: str


class FindingPage(BaseModel):
    items: list[FindingView]
    total: int
    page: int
    page_size: int


class RecordView(ORMModel):
    row_number: int
    record_key: str
    accepted: bool
    data: dict[str, str]


class RecordPage(BaseModel):
    items: list[RecordView]
    total: int
    page: int
    page_size: int


class ChangeExample(BaseModel):
    record_key: str
    fields: list[str]
    before: dict[str, str]
    after: dict[str, str]


class MembershipExample(BaseModel):
    record_key: str
    data: dict[str, str]


class ComparisonView(BaseModel):
    old_id: str
    new_id: str
    added: int
    removed: int
    changed: int
    unchanged: int
    specialty_changes: int
    location_changes: int
    field_changes: dict[str, int]
    examples: list[ChangeExample]
    examples_truncated: bool
    added_examples: list[MembershipExample]
    removed_examples: list[MembershipExample]
    validation_delta: dict[str, int]
    valid_delta: int
    rejected_delta: int
    caveat: str
