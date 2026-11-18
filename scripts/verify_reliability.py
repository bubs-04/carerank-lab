"""Measure backup, migration, restart and synthetic load in a disposable PostgreSQL container.

The source is read only. No destructive command accepts a source container/URL.
Requires Python backend dependencies, Docker and a locally available PostgreSQL 16 image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
LABEL = "org.carerank.disposable-verification"
DB = "carerank_test"
RESTORE_DB = "carerank_restore_test"


def docker_env():
    return {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        }
    }


def validate_disposable(name, token, details):
    """Never authorize destruction from a name alone; match this invocation's label."""
    if not re.fullmatch(r"carerank-verification-[a-f0-9]{12}", name):
        raise ValueError("Not a verification container")
    if not token or len(token) < 24:
        raise ValueError("Missing invocation ownership token")
    if details.get("Name", "").lstrip("/") != name:
        raise ValueError("Container identity mismatch")
    if details.get("Config", {}).get("Labels", {}).get(LABEL) != token:
        raise ValueError("Container ownership label mismatch")
    if any(
        m.get("Type") != "tmpfs" or m.get("Destination") != "/var/lib/postgresql/data"
        for m in details.get("Mounts", [])
    ):
        raise ValueError("Verification containers must not mount retained storage")


def validate_target(url, port, database):
    target = make_url(url)
    if target.get_backend_name() != "postgresql" or target.host != "127.0.0.1":
        raise ValueError("Verification target must be loopback PostgreSQL")
    if target.port != port or port == 5432 or target.database != database:
        raise ValueError(
            "Verification target is not this invocation's disposable database"
        )
    if database not in {DB, RESTORE_DB}:
        raise ValueError("Unexpected disposable database name")


def run(command, label, *, env=None, output=None, data=None, timeout=120):
    result = subprocess.run(
        command,
        env=env,
        input=data,
        stdout=output or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        # Do not print commands, connection strings, pg_dump contents or SQL errors.
        raise RuntimeError(f"{label} failed (exit {result.returncode})")
    return result.stdout


def fingerprints(connection, tables=None):
    names = tables or sorted(inspect(connection).get_table_names())
    result = {}
    for name in names:
        quoted = connection.dialect.identifier_preparer.quote(name)
        digest, count = hashlib.sha256(), 0
        rows = connection.execute(
            text(
                f"SELECT row_to_json(t)::text FROM {quoted} t ORDER BY row_to_json(t)::text"
            )
        )
        for row in rows:
            digest.update(row[0].encode() + b"\n")
            count += 1
        result[name] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def wait_for(predicate, seconds, description):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError(f"Timed out: {description}")


def stop_process(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def summarize(samples, elapsed):
    ordered = sorted(samples)
    return {
        "samples": len(samples),
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 3),
        "max_ms": round(max(samples), 3),
        "wall_seconds": round(elapsed, 3),
        "operations_per_second": round(len(samples) / elapsed, 2),
    }


class Verification:
    def __init__(self, args):
        self.args = args
        self.name = "carerank-verification-" + secrets.token_hex(6)
        self.token = secrets.token_hex(24)
        self.password = secrets.token_hex(32)
        self.work = Path(tempfile.mkdtemp(prefix="carerank-verification-"))
        self.port = None
        self.created = False
        self.processes = []
        self.engines = []
        self.child_env = None
        self.report = {
            "schema": 1,
            "measured_at_utc": datetime.now(UTC).isoformat(),
            "source_revision": run(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], "Git revision"
            )
            .decode()
            .strip(),
            "environment": {
                "python": platform.python_version(),
                "system": platform.system(),
                "client_logical_cpus": os.cpu_count(),
                "postgres_image": args.image,
                "postgres_cpu_limit": 2,
                "postgres_memory_limit_mib": 512,
            },
            "limitations": [
                "Single shared cloud development host; not production capacity or an SLA.",
                "Load measures in-process SQLAlchemy query + count + serialization, not HTTP/network latency.",
                "Docker PostgreSQL crash/start is not AWS RDS failover or host-loss recovery.",
                "Logical backup excludes cluster roles; runtime credentials must be provisioned separately.",
                "No live CMS request or paid cloud resource is used.",
            ],
        }

    def docker(self, *args, label="Docker command", **kwargs):
        return run(DOCKER + list(args), label, env=docker_env(), **kwargs)

    def owned(self):
        data = json.loads(
            self.docker("inspect", self.name, label="Inspect disposable container")
        )[0]
        validate_disposable(self.name, self.token, data)
        return data

    def engine(self, database):
        url = f"postgresql+psycopg://verify_admin:{self.password}@127.0.0.1:{self.port}/{database}"
        validate_target(url, self.port, database)
        engine = create_engine(
            url, pool_pre_ping=True, connect_args={"connect_timeout": 2}
        )
        self.engines.append(engine)
        return engine

    def start(self):
        # No image pull: image availability is a prerequisite, never an implicit network dependency.
        self.docker(
            "image",
            "inspect",
            self.args.image,
            label="Local PostgreSQL image availability",
        )
        env = docker_env()
        env["POSTGRES_PASSWORD"] = self.password
        # Docker reassigns an anonymous published port on restart. Reserve a
        # random explicit port so reconnect tests keep the same database address.
        # A race for that port fails container creation; it never targets another DB.
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.port = reservation.getsockname()[1]
        run(
            DOCKER
            + [
                "run",
                "-d",
                "--name",
                self.name,
                "--label",
                LABEL + "=" + self.token,
                "--cpus",
                "2",
                "--memory",
                "512m",
                "-e",
                "POSTGRES_PASSWORD",
                "-e",
                "POSTGRES_USER=verify_admin",
                "-e",
                "POSTGRES_DB=" + DB,
                "-e",
                "PGDATA=/var/lib/postgresql/verifydata",
                "-p",
                f"127.0.0.1:{self.port}:5432",
                "--tmpfs",
                "/var/lib/postgresql/data:rw,size=1m",
                self.args.image,
            ],
            "Create isolated PostgreSQL",
            env=env,
        )
        self.created = True
        data = self.owned()
        assert self.port == int(
            data["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
        )
        self.db = self.engine(DB)
        self.ready()
        self.docker(
            "exec",
            self.name,
            "createdb",
            "-U",
            "verify_admin",
            RESTORE_DB,
            label="Create empty isolated restore database",
        )
        self.restore = self.engine(RESTORE_DB)

    def ready(self):
        def check():
            try:
                with self.db.connect() as connection:
                    return connection.scalar(text("SELECT 1")) == 1
            except SQLAlchemyError:
                return False

        wait_for(check, 30, "disposable PostgreSQL readiness")

    def backup_restore(self):
        source_url = os.environ.get(self.args.source_url_env)
        if not source_url:
            raise ValueError(
                "Set the configured read-only backup source URL environment variable"
            )
        source = make_url(source_url)
        if (
            source.get_backend_name() != "postgresql"
            or source.database != self.args.source_database
        ):
            raise ValueError("Backup source URL/database mismatch")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.args.source_container):
            raise ValueError("Invalid backup source container")
        # Source Docker operations are restricted to read-only pg_dump. The exported
        # snapshot binds the dump and fingerprints to one transaction-consistent point.
        source_engine = create_engine(source, connect_args={"connect_timeout": 5})
        dump = self.work / "database.dump"
        start = time.perf_counter()
        with (
            source_engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection,
            connection.begin(),
        ):
            connection.execute(text("SET TRANSACTION READ ONLY"))
            snapshot = connection.scalar(text("SELECT pg_export_snapshot()"))
            before = fingerprints(connection)
            version = connection.scalar(text("SELECT version_num FROM alembic_version"))
            with dump.open("xb") as handle:
                dump.chmod(0o600)
                self.docker(
                    "exec",
                    self.args.source_container,
                    "pg_dump",
                    "-U",
                    source.username,
                    "-d",
                    self.args.source_database,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--snapshot=" + snapshot,
                    label="Read-only source backup",
                    output=handle,
                )
        backup_seconds = time.perf_counter() - start
        source_engine.dispose()
        start = time.perf_counter()
        with dump.open("rb") as handle:
            result = subprocess.run(
                DOCKER
                + [
                    "exec",
                    "-i",
                    self.name,
                    "pg_restore",
                    "-U",
                    "verify_admin",
                    "-d",
                    RESTORE_DB,
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                ],
                env=docker_env(),
                stdin=handle,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("Restore into empty disposable database failed")
        restore_seconds = time.perf_counter() - start
        with self.restore.connect() as connection:
            after = fingerprints(connection)
        if before != after:
            raise AssertionError(
                "Restored table fingerprints differ from backup snapshot"
            )
        self.report["backup_restore"] = {
            "source_migration": version,
            "target": "new isolated container/database",
            "consistent_snapshot": True,
            "tables": before,
            "all_table_fingerprints_equal": True,
            "dump_bytes": dump.stat().st_size,
            "backup_and_fingerprint_seconds": round(backup_seconds, 3),
            "restore_seconds": round(restore_seconds, 3),
        }
        dump.unlink()  # Contains authentication hashes/history: never export or commit this archive.
        self.restore_baseline = before

    def migrate(self):
        from alembic import command
        from alembic.config import Config
        from app.db import get_engine

        cfg = Config(str(ROOT / "backend/alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "backend/migrations"))
        old = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = self.restore.url.render_as_string(
                hide_password=False
            )
            get_engine.cache_clear()
            command.upgrade(cfg, "head")
            with self.restore.connect() as connection:
                # Alembic version changes are expected; every original data table must be identical.
                names = [n for n in self.restore_baseline if n != "alembic_version"]
                after = fingerprints(connection, names)
                target = connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
            assert after == {
                k: v for k, v in self.restore_baseline.items() if k != "alembic_version"
            }
            self.report["migration_preservation"] = {
                "from": self.report["backup_restore"]["source_migration"],
                "to": target,
                "original_data_tables": len(names),
                "all_original_fingerprints_equal": True,
                "changed_revision": self.report["backup_restore"]["source_migration"]
                != target,
            }
            os.environ["DATABASE_URL"] = self.db.url.render_as_string(
                hide_password=False
            )
            get_engine().dispose()
            get_engine.cache_clear()
            command.upgrade(cfg, "head")
        finally:
            get_engine().dispose()
            get_engine.cache_clear()
            if old is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old

    def seed_and_roles(self):
        from app.pipeline import run_pipeline
        from app.runtime_role import provision

        start = time.perf_counter()
        run_pipeline(engine=self.db)
        with self.db.connect() as connection:
            self.report["environment"]["postgres_version"] = connection.scalar(
                text("SELECT version()")
            )
            counts = {
                table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("providers", "encounters", "scores")
            }
        self.report["synthetic_seed"] = {
            "seed": 42,
            "rows": counts,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
        }
        worker = self.db.url.set(
            username="verify_worker", password=secrets.token_hex(32)
        )
        provision(
            self.db.url.render_as_string(hide_password=False),
            worker.render_as_string(hide_password=False),
            worker=True,
        )
        self.child_env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "DATABASE_URL",
                "DATABASE_URL_FILE",
                "TEST_DATABASE_URL",
                "POSTGRES_PASSWORD",
                "RUNTIME_DATABASE_URL",
                "RUNTIME_DATABASE_URL_FILE",
                "WORKER_DATABASE_URL",
                "WORKER_DATABASE_URL_FILE",
            }
        }
        self.child_env.update(
            DATABASE_URL=worker.render_as_string(hide_password=False),
            APP_ENV="development",
            DQ_ENABLED="true",
            PYTHONPATH=str(ROOT / "backend"),
        )

    def enqueue(self, name):
        from app.operations import service

        with Session(self.db) as session, session.begin():
            pipeline = service.create_pipeline(
                session,
                {
                    "name": name,
                    "source": "fixture_a",
                    "max_rows": 5,
                    "enabled": False,
                    "interval_seconds": 3600,
                    "max_attempts": 2,
                    "backoff_seconds": 1,
                    "timeout_seconds": 30,
                },
            )
            row = service.enqueue(session, pipeline, str(uuid.uuid4()))
            session.flush()
            return row.id

    def state(self, execution_id):
        with self.db.connect() as connection:
            return connection.execute(
                text(
                    "SELECT status, attempt_count, published_run_id FROM pipeline_executions WHERE id=:id"
                ),
                {"id": execution_id},
            ).one()

    def slow_worker(self):
        # Test-only startup injection; no HTTP/production fault-injection endpoint.
        marker = self.work / "slow-fetch"
        marker.touch()
        (self.work / "sitecustomize.py").write_text(
            "import os,time\nfrom pathlib import Path\nfrom app.ingestion import connector\n"
            "original=connector.fixture_batch\n"
            "def slow(*args,**kwargs):\n"
            "    if Path(os.environ['CARERANK_VERIFY_MARKER']).exists(): time.sleep(15)\n"
            "    return original(*args,**kwargs)\nconnector.fixture_batch=slow\n"
        )
        env = {
            **self.child_env,
            "PYTHONPATH": str(self.work) + os.pathsep + str(ROOT / "backend"),
            "CARERANK_VERIFY_MARKER": str(marker),
        }
        return self.worker(env), marker

    def worker(self, env=None):
        log = (self.work / ("worker-" + secrets.token_hex(4) + ".log")).open("wb")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "app.operations",
                "worker",
                "--lease-seconds",
                "3",
                "--poll-seconds",
                "0.1",
            ],
            cwd=ROOT / "backend",
            env=env or self.child_env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        log.close()
        self.processes.append(process)
        return process

    def fetching(self, execution_id):
        with self.db.connect() as connection:
            return connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pipeline_attempts a "
                    "JOIN pipeline_executions e ON e.id=a.execution_id WHERE e.id=:id "
                    "AND e.status='running' AND a.ingestion_run_id IS NOT NULL)"
                ),
                {"id": execution_id},
            )

    def evidence(self, execution_id):
        with self.db.connect() as connection:
            attempts = [
                dict(r)
                for r in connection.execute(
                    text(
                        "SELECT number,status,error_code "
                        "FROM pipeline_attempts WHERE execution_id=:id ORDER BY number"
                    ),
                    {"id": execution_id},
                ).mappings()
            ]
            events = list(
                connection.scalars(
                    text(
                        "SELECT action FROM pipeline_events WHERE execution_id=:id ORDER BY created_at,id"
                    ),
                    {"id": execution_id},
                )
            )
            snapshots = connection.scalar(
                text("SELECT count(*) FROM registry_snapshots")
            )
        assert [a["status"] for a in attempts] == ["interrupted", "succeeded"]
        assert self.state(execution_id)[0] == "succeeded"
        return {
            "attempts": attempts,
            "events": events,
            "published_snapshot_count": snapshots,
        }

    def worker_restart(self):
        execution_id = self.enqueue("Synthetic worker-termination verification")
        process, marker = self.slow_worker()
        wait_for(
            lambda: self.fetching(execution_id), 20, "worker entering source fetch"
        )
        start = time.perf_counter()
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        marker.unlink()
        assert self.state(execution_id)[0] == "running"
        replacement = self.worker()
        wait_for(
            lambda: self.state(execution_id)[0] == "succeeded",
            30,
            "replacement worker recovery",
        )
        self.report["worker_restart"] = {
            "fault": "SIGKILL real supervisor and child during fixture fetch",
            "natural_lease_expiry_seconds": 3,
            "recovery_seconds": round(time.perf_counter() - start, 3),
            **self.evidence(execution_id),
        }
        stop_process(replacement)

    def database_restart(self):
        execution_id = self.enqueue("Synthetic database-crash verification")
        process, marker = self.slow_worker()
        wait_for(
            lambda: self.fetching(execution_id),
            20,
            "worker entering source fetch before DB crash",
        )
        self.owned()
        start = time.perf_counter()
        self.docker("stop", "-t", "0", self.name, label="Crash disposable PostgreSQL")
        failed_read = False
        try:
            with self.db.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            failed_read = True
        assert failed_read and process.poll() is None
        # Keep the database down beyond the 3s confirmed worker lease.
        time.sleep(4)
        marker.unlink()
        self.owned()
        self.docker("start", self.name, label="Restart disposable PostgreSQL")
        self.ready()
        database_ready_seconds = time.perf_counter() - start
        wait_for(
            lambda: self.state(execution_id)[0] == "succeeded",
            30,
            "same worker reconnect/recovery",
        )
        assert process.poll() is None
        with self.db.connect() as connection:
            counts = {
                table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in self.report["synthetic_seed"]["rows"]
            }
        assert counts == self.report["synthetic_seed"]["rows"]
        self.report["database_restart"] = {
            "fault": "SIGKILL PostgreSQL in disposable container during active fetch",
            "read_failed_while_down": failed_read,
            "same_supervisor_survived": True,
            "database_ready_seconds": round(database_ready_seconds, 3),
            "execution_recovered_seconds": round(time.perf_counter() - start, 3),
            "synthetic_counts_preserved": True,
            **self.evidence(execution_id),
        }
        stop_process(process)

    def query_load(self):
        from app.repository import search

        def requests(_):
            samples = []
            with Session(self.db) as session:
                for n in range(self.args.requests_per_client):
                    start = time.perf_counter()
                    result = search(
                        session,
                        "",
                        "Cardiology",
                        None,
                        None,
                        None,
                        n % 10 + 1,
                        20,
                        "quality",
                    )
                    assert result["total"] == 200 and len(result["items"]) == 20
                    samples.append((time.perf_counter() - start) * 1000)
            return samples

        requests(0)  # One serial warmup of the same bounded workload.
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.args.clients) as pool:
            samples = [
                v
                for batch in pool.map(requests, range(self.args.clients))
                for v in batch
            ]
        self.report["query_load"] = {
            "concurrent_clients": self.args.clients,
            "errors": 0,
            "warmup_requests": self.args.requests_per_client,
            "operation": "filtered synthetic provider search: count + page + ORM serialization",
            **summarize(samples, time.perf_counter() - start),
        }

    def query_plan(self):
        from app.operations import service

        with Session(self.db) as session, session.begin():
            pipeline = service.create_pipeline(
                session,
                {
                    "name": "Synthetic query-plan history (not real executions)",
                    "source": "fixture_a",
                    "max_rows": 5,
                    "enabled": False,
                    "interval_seconds": 3600,
                    "max_attempts": 2,
                    "backoff_seconds": 1,
                    "timeout_seconds": 30,
                },
            )
            session.flush()
            pipeline_id = pipeline.id
            config = json.dumps(service.policy(pipeline))
            session.execute(
                text(
                    "INSERT INTO pipeline_executions "
                    "(id,pipeline_id,idempotency_key,trigger,config,status,revision,attempt_count,max_attempts,created_at,available_at) "
                    "SELECT md5('verification-' || n), :pipeline, 'load-' || n, 'load_fixture', CAST(:config AS json), "
                    "'succeeded',1,1,2,now()-make_interval(secs=>n),now() FROM generate_series(1,10000) n"
                ),
                {"pipeline": pipeline_id, "config": config},
            )
        query = text(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id,status,created_at FROM pipeline_executions "
            "WHERE pipeline_id=:pipeline ORDER BY created_at DESC,id DESC LIMIT 50"
        )
        with self.db.begin() as connection:
            connection.execute(text("ANALYZE pipeline_executions"))
            # Only this invocation's isolated synthetic database. Compare the
            # actual migration-007 index against the preceding unindexed plan.
            connection.execute(text("DROP INDEX ix_pipeline_history"))
            before = connection.execute(query, {"pipeline": pipeline_id}).scalar()[0]
            connection.execute(
                text(
                    "CREATE INDEX ix_pipeline_history "
                    "ON pipeline_executions (pipeline_id,created_at,id)"
                )
            )
            after = connection.execute(query, {"pipeline": pipeline_id}).scalar()[0]
        self.report["query_plan_experiment"] = {
            "synthetic_history_rows": 10000,
            "query": "latest 50 executions of one pipeline, stable creation/id order",
            "candidate_index": "migration 007: pipeline_executions(pipeline_id,created_at,id), backward scan",
            "before": before,
            "after": after,
            "scope": "Controlled ephemeral index experiment; report the existing planner choice and measured timings, not an assumed production speedup.",
        }

    def finish(self):
        for process in self.processes:
            stop_process(process)
        for engine in self.engines:
            engine.dispose()
        if self.created:
            self.owned()
            self.docker(
                "rm", "-f", self.name, label="Remove owned disposable container"
            )
        shutil.rmtree(self.work)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-container", required=True)
    parser.add_argument("--source-database", default="carerank")
    parser.add_argument("--source-url-env", default="DATABASE_URL")
    parser.add_argument("--image", default="postgres:16-alpine")
    parser.add_argument(
        "--clients", type=int, default=8, choices=range(1, 17), metavar="1..16"
    )
    parser.add_argument(
        "--requests-per-client",
        type=int,
        default=30,
        choices=range(1, 201),
        metavar="1..200",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/RELIABILITY_6.0.json"
    )
    args = parser.parse_args()
    os.umask(0o077)
    check = Verification(args)
    try:
        for phase in (
            check.start,
            check.backup_restore,
            check.migrate,
            check.seed_and_roles,
            check.worker_restart,
            check.database_restart,
            check.query_load,
            check.query_plan,
        ):
            print("Verification phase: " + phase.__name__, flush=True)
            phase()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(check.report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "report": str(args.output),
                    "backup_tables": len(check.report["backup_restore"]["tables"]),
                    "load_requests": check.report["query_load"]["samples"],
                }
            )
        )
    except Exception:
        diagnostic = Path(tempfile.mkdtemp(prefix="carerank-verification-failure-"))
        if check.created:
            check.owned()
            (diagnostic / "postgres.log").write_bytes(check.docker("logs", check.name))
        for log in check.work.glob("worker-*.log"):
            shutil.copyfile(log, diagnostic / log.name)
        print("Private failure diagnostics: " + str(diagnostic), file=sys.stderr)
        raise
    finally:
        check.finish()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never expose SQL parameters or credentials
        print(
            "Reliability verification failed: "
            + type(exc).__name__
            + ": "
            + (
                str(exc)
                if isinstance(exc, (ValueError, AssertionError, RuntimeError))
                else "inspect the failing phase"
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
