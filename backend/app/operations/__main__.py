"""Run durable pipeline scheduling and execution; live CMS is opt-in per definition."""

import argparse
import logging
from sqlalchemy.orm import Session
from ..db import get_engine
from .models import Execution
from .service import Claim, execute_claim, recover_expired, reconcile_monitoring, schedule_due
from .worker import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--lease-seconds", type=int, default=30, choices=range(3, 301), metavar="3..300")
    worker.add_argument("--poll-seconds", type=float, default=2)
    commands.add_parser("tick", help="Schedule due work and recover leases once without fetching data")
    execute = commands.add_parser("execute", help=argparse.SUPPRESS)
    execute.add_argument("execution_id")
    execute.add_argument("attempt_id")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    engine = get_engine()
    if args.command == "worker":
        if not 0.1 <= args.poll_seconds <= 60:
            parser.error("poll-seconds must be between 0.1 and 60")
        return run(engine, args.once, args.lease_seconds, args.poll_seconds)
    if args.command == "tick":
        print(
            {
                "recovered": recover_expired(engine),
                "monitoring": reconcile_monitoring(engine),
                "scheduled": schedule_due(engine),
            }
        )
        return 0
    with Session(engine) as db:
        row = db.get(Execution, args.execution_id)
        if not row or row.active_attempt_id != args.attempt_id or row.status != "running":
            return 1
        token = Claim(
            row.id, args.attempt_id, row.attempt_count, row.config, row.published_run_id, row.deadline_at
        )
    execute_claim(engine, token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        logging.getLogger(__name__).error("pipeline_command_failed type=%s", type(exc).__name__)
        raise SystemExit(1) from None
