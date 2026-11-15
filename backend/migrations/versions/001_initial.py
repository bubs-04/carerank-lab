"""Frozen initial schema, independent of later model edits."""

from alembic import op
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared SQLAlchemy schema registry."""


class Provider(Base):
    """Fictional provider identity; one specialty and location per provider."""

    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    specialty: Mapped[str] = mapped_column(String(50), index=True)
    location: Mapped[str] = mapped_column(String(50), index=True)


class Encounter(Base):
    """Synthetic events, without patient identifiers; nullable outcomes are intentional."""

    __tablename__ = "encounters"
    __table_args__ = (
        CheckConstraint("cost > 0 AND risk >= 0 AND risk <= 1"),
        CheckConstraint("outcome IS NULL OR outcome IN (0, 1)"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    procedure: Mapped[str] = mapped_column(String(30))
    risk: Mapped[float] = mapped_column(Float)
    cost: Mapped[float] = mapped_column(Float)
    outcome: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Score(Base):
    """One materialized score per provider in the current dataset."""

    __tablename__ = "scores"
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), primary_key=True)
    encounters: Mapped[int] = mapped_column(Integer)
    observed: Mapped[int] = mapped_column(Integer)
    avg_cost: Mapped[float] = mapped_column(Float)
    quality: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    components: Mapped[dict] = mapped_column(JSON)


class PipelineRun(Base):
    """Durable execution audit independent of dataset replacement."""

    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    seed: Mapped[int] = mapped_column(Integer)
    providers: Mapped[int] = mapped_column(Integer)
    encounters: Mapped[int] = mapped_column(Integer)
    seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(100), nullable=True)


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    Base.metadata.drop_all(op.get_bind())
