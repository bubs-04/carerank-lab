"""python -m app.ingestion --max-rows 1000; no HTTP mutation endpoint exists."""

import argparse
import logging
import signal
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from ..db import get_engine
from .config import IngestionSettings
from .connector import CMSConnector, fixture_batch
from .models import IngestionRun
from .service import ingest, now
from .validation import canonical


def interrupt(signum, frame):
    """Let the service record a normal termination as interrupted, not successful."""
    raise KeyboardInterrupt()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int)
    parser.add_argument(
        "--fixture", type=Path, help="Explicit deterministic test CSV; never labeled live CMS"
    )
    parser.add_argument(
        "--mark-interrupted", metavar="RUN_ID", help="Only after confirming the worker is stopped"
    )
    args = parser.parse_args()
    settings = IngestionSettings(**({"max_rows": args.max_rows} if args.max_rows is not None else {}))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    signal.signal(signal.SIGTERM, interrupt)
    engine = get_engine()
    if args.mark_interrupted:
        with Session(engine) as db, db.begin():
            run = db.get(IngestionRun, args.mark_interrupted, with_for_update=True)
            if not run or run.status != "running":
                parser.error("Only an existing running audit may be marked interrupted")
            run.status, run.error_code, run.finished_at = "interrupted", "operator_marked_interrupted", now()
        from ..monitoring.service import evaluate_safely

        evaluate_safely(engine, args.mark_interrupted)
        print(canonical({"run_id": args.mark_interrupted, "status": "interrupted"}))
        return
    connector = CMSConnector(settings)
    fetch = (
        (lambda: fixture_batch(args.fixture, settings.max_rows, settings.max_bytes))
        if args.fixture
        else connector.fetch
    )
    run_id = ingest(engine, fetch, "fixture" if args.fixture else "cms", settings.max_rows)
    with Session(engine) as db:
        run = db.get(IngestionRun, run_id)
        print(
            canonical(
                {
                    "run_id": run.id,
                    "status": run.status,
                    "snapshot_id": run.snapshot_id,
                    "received": run.received,
                    "valid": run.valid,
                    "rejected": run.rejected,
                    "error_code": run.error_code,
                }
            )
        )
        if run.status == "failed":
            raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(canonical({"status": "interrupted", "error_code": "interrupted"}))
        raise SystemExit(130) from None
    except (SQLAlchemyError, ValidationError) as exc:
        print(
            canonical(
                {
                    "status": "failed",
                    "error_code": "database_or_configuration_error",
                    "exception_type": type(exc).__name__,
                }
            )
        )
        raise SystemExit(1) from None
