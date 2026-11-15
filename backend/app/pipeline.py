import argparse
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import delete, insert, text, update
from .db import get_engine
from .generator import generate
from .models import Encounter, PipelineRun, Provider, Score
from .scoring import rank_specialties, score_provider
from .validation import validate

log = logging.getLogger(__name__)


def run_pipeline(
    providers: int = 1000, encounters: int = 100000, seed: int = 42, engine=None, source=None
) -> str:
    """Audit separately, serialize writers, and replace data+scores in one transaction."""
    engine = engine or get_engine()
    run_id = str(uuid4())
    started = time.perf_counter()
    with engine.begin() as conn:
        conn.execute(
            insert(PipelineRun).values(
                id=run_id,
                started_at=datetime.now(timezone.utc),
                status="running",
                seed=seed,
                providers=providers,
                encounters=encounters,
            )
        )
    try:
        ps, es = source if source is not None else generate(providers, encounters, seed)
        report = validate(ps, es)
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(721304)"))
            conn.execute(delete(Score))
            conn.execute(delete(Encounter))
            conn.execute(delete(Provider))
            conn.execute(insert(Provider), ps)
            for offset in range(0, len(es), 5000):
                conn.execute(insert(Encounter), es[offset : offset + 5000])
            aggregates = (
                conn.execute(text(Path(__file__).with_name("aggregate.sql").read_text())).mappings().all()
            )
            rows = []
            for a in aggregates:
                parts = score_provider(a["encounters"], a["observed"], a["residual"], a["cost_ratio"])
                rows.append(
                    {
                        "provider_id": a["provider_id"],
                        "specialty": a["specialty"],
                        "encounters": a["encounters"],
                        "observed": a["observed"],
                        "avg_cost": a["avg_cost"],
                        "quality": parts["quality"],
                        "components": parts,
                    }
                )
            ranked = rank_specialties(rows)
            conn.execute(insert(Score), [{k: v for k, v in r.items() if k != "specialty"} for r in ranked])
            conn.execute(
                update(PipelineRun)
                .where(PipelineRun.id == run_id)
                .values(
                    status="success",
                    finished_at=datetime.now(timezone.utc),
                    seconds=time.perf_counter() - started,
                    providers=report["providers"],
                    encounters=report["encounters"],
                )
            )
        log.info("pipeline_success run_id=%s missing_outcomes=%s", run_id, report["missing_outcomes"])
    except Exception as error:
        with engine.begin() as conn:
            conn.execute(
                update(PipelineRun)
                .where(PipelineRun.id == run_id)
                .values(
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                    seconds=time.perf_counter() - started,
                    error=type(error).__name__,
                )
            )
        log.error("pipeline_failed run_id=%s error_type=%s", run_id, type(error).__name__)
        raise
    return run_id


def main():
    """Expose reproducible dataset size and seed as CLI flags."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", type=int, default=1000)
    parser.add_argument("--encounters", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    logging.basicConfig(level=logging.INFO)
    print(run_pipeline(**vars(parser.parse_args())))


if __name__ == "__main__":
    main()
