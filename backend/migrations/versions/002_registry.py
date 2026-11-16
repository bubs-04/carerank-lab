"""Frozen CMS registry schema; adds tables only, no synthetic data changes."""

from alembic import op
from datetime import datetime
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class RegistryBase(DeclarativeBase):
    pass


class DataSource(RegistryBase):
    __tablename__ = "registry_sources"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(300))


class Snapshot(RegistryBase):
    __tablename__ = "registry_snapshots"
    __table_args__ = (
        UniqueConstraint("source_id", "scope_hash", "checksum", "policy", name="uq_registry_content"),
        CheckConstraint(
            "received = valid + rejected AND valid > 0 AND rejected >= 0 AND received <= 5000",
            name="ck_registry_snapshot_counts",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("registry_sources.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str] = mapped_column(String(64))
    scope_hash: Mapped[str] = mapped_column(String(64))
    scope: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    policy: Mapped[str] = mapped_column(String(40))
    received: Mapped[int] = mapped_column(Integer)
    valid: Mapped[int] = mapped_column(Integer)
    rejected: Mapped[int] = mapped_column(Integer)
    warnings: Mapped[int] = mapped_column(Integer)
    finding_counts: Mapped[dict] = mapped_column(JSON)


class IngestionRun(RegistryBase):
    __tablename__ = "registry_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','succeeded','no_change','failed','interrupted')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("registry_sources.id"), index=True)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("registry_snapshots.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    requested: Mapped[int] = mapped_column(Integer)
    received: Mapped[int | None] = mapped_column(Integer)
    valid: Mapped[int | None] = mapped_column(Integer)
    rejected: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(100))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceRecord(RegistryBase):
    __tablename__ = "registry_records"
    __table_args__ = (UniqueConstraint("snapshot_id", "accepted_key", name="uq_registry_accepted_identity"),)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("registry_snapshots.id"), primary_key=True)
    row_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_key: Mapped[str] = mapped_column(String(64), index=True)
    accepted_key: Mapped[str | None] = mapped_column(String(64))
    accepted: Mapped[bool] = mapped_column(Boolean)
    content_hash: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class ValidationFinding(RegistryBase):
    __tablename__ = "registry_findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("registry_runs.id"), index=True)
    row_number: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(100))
    field: Mapped[str] = mapped_column(String(100))


class SnapshotChange(RegistryBase):
    __tablename__ = "registry_changes"
    old_id: Mapped[str] = mapped_column(ForeignKey("registry_snapshots.id"), primary_key=True)
    new_id: Mapped[str] = mapped_column(ForeignKey("registry_snapshots.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict] = mapped_column(JSON)


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    RegistryBase.metadata.create_all(op.get_bind())


def downgrade():
    RegistryBase.metadata.drop_all(op.get_bind())
