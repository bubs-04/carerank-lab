"""Idempotent, development-only preparation of the dedicated carerank_demo database."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .auth.models import User
from .auth.service import create_user
from .db import get_engine
from .ingestion.archive import read_archive
from .ingestion.connector import fixture_batch
from .ingestion.models import IngestionRun, Snapshot
from .ingestion.service import ingest
from .operations.models import Pipeline
from .operations.service import create_pipeline

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
ROLES = {"administrator", "analyst", "viewer"}


def guard(engine):
    if (
        os.environ.get("APP_ENV") != "development"
        or engine.url.get_backend_name() != "postgresql"
        or engine.url.database != "carerank_demo"
        or engine.url.username != "carerank_demo_owner"
        or engine.url.host not in {"db", "127.0.0.1", "localhost"}
    ):
        raise ValueError("Demo preparation requires the dedicated local carerank_demo development database")


def prepare(engine, accounts_path, archive_path=None):
    guard(engine)
    accounts = json.loads(Path(accounts_path).read_text())
    if not isinstance(accounts, list) or {a.get("role") for a in accounts} != ROLES or len(accounts) != 3:
        raise ValueError("Exactly three development role accounts are required")
    if any(
        set(a) != {"username", "display_name", "role", "password"}
        or not a["username"].startswith("demo-")
        or len(a["password"]) < 24
        for a in accounts
    ):
        raise ValueError("Invalid demo account file")
    archive = read_archive(Path(archive_path)) if archive_path and Path(archive_path).exists() else None
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(721600)"))
        try:
            # Existing bootstrap seeds only a pristine synthetic workspace.
            from .pipeline import run_pipeline

            with engine.connect() as db:
                pristine = db.scalar(
                    text(
                        "SELECT NOT EXISTS (SELECT 1 FROM providers) "
                        "AND NOT EXISTS (SELECT 1 FROM encounters) "
                        "AND NOT EXISTS (SELECT 1 FROM scores) "
                        "AND NOT EXISTS (SELECT 1 FROM pipeline_runs)"
                    )
                )
            if pristine:
                run_pipeline(engine=engine)
            with Session(engine) as db, db.begin():
                for account in accounts:
                    if not db.scalar(select(User).where(User.username == account["username"])):
                        create_user(db, **account)
            for name in ("a", "b"):

                def fetch(name=name):
                    return fixture_batch(FIXTURES / f"cms_registry_{name}.csv", 5)

                checksum = fetch().provenance["fixture_sha256"]
                with Session(engine) as db:
                    already = any(
                        row.provenance.get("fixture_sha256") == checksum
                        for row in db.scalars(select(Snapshot))
                    )
                if not already:
                    checked_ingest(engine, fetch, "fixture", 5)
            if archive:
                with Session(engine) as db:
                    already = any(
                        row.provenance.get("archive_payload_sha256")
                        == archive.provenance["archive_payload_sha256"]
                        for row in db.scalars(select(IngestionRun))
                    )
                if not already:
                    checked_ingest(engine, lambda: archive, "cms", len(archive.rows))
            with Session(engine) as db, db.begin():
                if not db.scalar(select(func.count()).select_from(Pipeline)):
                    create_pipeline(
                        db,
                        {
                            "name": "Garner demo · deterministic recovery",
                            "source": "fixture_retry",
                            "max_rows": 5,
                            "enabled": False,
                            "interval_seconds": 3600,
                            "max_attempts": 2,
                            "backoff_seconds": 5,
                            "timeout_seconds": 30,
                        },
                    )
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(721600)"))
    return {"prepared": True, "database": "carerank_demo", "cms_archive_loaded": bool(archive)}


def checked_ingest(engine, fetch, mode, count):
    run_id = ingest(engine, fetch, mode, count)
    with Session(engine) as db:
        if db.get(IngestionRun, run_id).status not in {"succeeded", "no_change"}:
            raise ValueError("Demo ingestion did not publish")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, required=True)
    parser.add_argument("--cms-archive", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(get_engine(), args.accounts, args.cms_archive)))
        return 0
    except Exception as exc:
        # Account documents and connection strings must never enter logs.
        print(json.dumps({"error": "demo_preparation_failed", "type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
