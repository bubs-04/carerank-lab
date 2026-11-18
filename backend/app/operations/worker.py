"""Small supervisor: a subprocess isolates blocking source I/O from heartbeats/timeouts."""

import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from sqlalchemy.exc import SQLAlchemyError
from .service import claim, heartbeat, recover_expired, reconcile_monitoring, schedule_due, finish_claim

log = logging.getLogger(__name__)


def terminate(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def work_once(engine, worker_id, lease_seconds=30):
    recover_expired(engine)
    reconcile_monitoring(engine)
    schedule_due(engine)
    claim_started = time.monotonic()
    token = claim(engine, worker_id, lease_seconds)
    if token is None:
        return False
    child = subprocess.Popen(
        [sys.executable, "-m", "app.operations", "execute", token.execution_id, token.attempt_id]
    )
    # Anchor before each database call: this underestimates the confirmed lease
    # rather than assuming time spent waiting for PostgreSQL extends ownership.
    confirmed_until = claim_started + lease_seconds
    next_heartbeat = time.monotonic()
    try:
        while child.poll() is None:
            if time.monotonic() >= confirmed_until:
                terminate(child)
                recover_expired(engine)
                return True
            if time.monotonic() >= next_heartbeat:
                renewal_started = time.monotonic()
                try:
                    valid = heartbeat(engine, token, lease_seconds)
                except SQLAlchemyError:
                    # Publication holds the execution lock until its atomic commit.
                    # A short heartbeat lock timeout is not itself a lost lease.
                    # Retry only inside the last confirmed lease; the child also
                    # checks its database lease/deadline immediately before commit.
                    next_heartbeat = time.monotonic() + 0.2
                else:
                    if not valid:
                        terminate(child)
                        recover_expired(engine)
                        return True
                    confirmed_until = renewal_started + lease_seconds
                    next_heartbeat = time.monotonic() + min(5, lease_seconds / 3)
            time.sleep(0.1)
        if child.returncode:
            finish_claim(engine, token, "worker_process_exit")
        recover_expired(engine)
    finally:
        terminate(child)
    return True


def run(engine, once=False, lease_seconds=30, poll_seconds=2):
    if engine.dialect.name != "postgresql":
        raise ValueError("Workers require PostgreSQL")
    worker_id = f"worker-{uuid.uuid4()}-{os.getpid()}"

    def stop(signum, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, stop)
    try:
        while True:
            try:
                worked = work_once(engine, worker_id, lease_seconds)
            except SQLAlchemyError as exc:
                log.error("pipeline_worker_database_error type=%s", type(exc).__name__)
                if once:
                    return 1
                worked = False
            if once:
                return 0
            if not worked:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        # The supervisor stops its child; its retained lease/attempt is recovered normally.
        log.info("pipeline_worker_stopped; outstanding leases remain recoverable")
        return 0
