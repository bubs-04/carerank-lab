"""Local CLI: evaluate/backfill, inspect, and investigate. No HTTP write surface."""

import argparse
import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
from ..db import get_engine
from ..ingestion.models import DataSource, IngestionRun
from ..ingestion.validation import canonical
from .models import Alert, AuditEvent
from .schemas import AlertView, EventView
from .service import TERMINAL, evaluate_run, investigate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--run-id")
    evaluate.add_argument("--mode", choices=("cms", "fixture"), default="cms")
    evaluate.add_argument(
        "--limit", type=int, default=100, help="Bounded oldest-first missing-profile backfill, 1–1000"
    )
    inspect = commands.add_parser("inspect")
    inspect.add_argument("alert_id")
    triage = commands.add_parser("investigate")
    triage.add_argument("alert_id")
    triage.add_argument(
        "--actor", required=True, help="Self-reported local operator, not authenticated identity"
    )
    triage.add_argument("--note", required=True)
    triage.add_argument("--expected-revision", required=True, type=int)
    triage.add_argument("--status", choices=("open", "acknowledged", "investigating", "resolved"))
    triage.add_argument("--assign", help="Empty string clears assignment")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = get_engine()
    if args.command == "evaluate":
        if not 1 <= args.limit <= 1000:
            parser.error("limit must be 1–1000")
        if args.run_id:
            ids = [args.run_id]
        else:
            from .models import Evaluation
            from .rules import definitions, profile_id
            from .config import MonitoringSettings

            profile = profile_id(definitions(MonitoringSettings()))
            with Session(engine) as db:
                ids = list(
                    db.scalars(
                        select(IngestionRun.id)
                        .join(DataSource)
                        .where(
                            DataSource.mode == args.mode,
                            IngestionRun.status.in_(TERMINAL),
                            IngestionRun.finished_at.is_not(None),
                            ~select(Evaluation.id)
                            .where(Evaluation.run_id == IngestionRun.id, Evaluation.profile == profile)
                            .exists(),
                        )
                        .order_by(IngestionRun.started_at, IngestionRun.id)
                        .limit(args.limit)
                    )
                )
        for run_id in ids:
            print(canonical(evaluate_run(engine, run_id)))
        print(canonical({"evaluated_attempts": len(ids), "more_may_remain": len(ids) == args.limit}))
    elif args.command == "inspect":
        with Session(engine) as db:
            alert = db.get(Alert, args.alert_id)
            if not alert:
                raise LookupError("alert_not_found")
            print(
                canonical(
                    {
                        "alert": AlertView.model_validate(alert).model_dump(mode="json"),
                        "events": [
                            EventView.model_validate(e).model_dump(mode="json")
                            for e in db.scalars(
                                select(AuditEvent)
                                .where(AuditEvent.alert_id == alert.id)
                                .order_by(AuditEvent.revision)
                            )
                        ],
                    }
                )
            )
    else:
        print(
            canonical(
                investigate(
                    engine,
                    args.alert_id,
                    actor=args.actor,
                    note=args.note,
                    expected_revision=args.expected_revision,
                    status=args.status,
                    assignee=args.assign,
                )
            )
        )


if __name__ == "__main__":
    try:
        main()
    except (SQLAlchemyError, ValidationError, ValueError, LookupError) as exc:
        # Known service errors are safe codes; DB messages/credentials are never printed.
        code = str(exc) if type(exc) in (ValueError, LookupError) else "database_or_configuration_error"
        print(canonical({"status": "error", "error_code": code, "exception_type": type(exc).__name__}))
        raise SystemExit(1) from None
