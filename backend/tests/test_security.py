"""Real PostgreSQL authentication and authorization boundaries, without identity mocks.

Every schema reset is guarded by the exact disposable database name. Existing
domain tests use a viewer override; this module exercises real passwords/cookies.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event, Lock
import json
import os
import subprocess
import sys
import uuid

from alembic import command
from alembic.config import Config
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, delete, event, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.main import app
from app.db import get_engine
from app.auth.models import AuthSession, LoginLimit, SecurityEvent, User
from app.auth.security import hash_password, now, token_hash, verify_password
from app.auth.service import create_user
from app.ingestion.connector import fixture_batch
from app.ingestion.service import ingest
from app.monitoring.models import Alert, AuditEvent

ORIGIN = "http://testserver"
PASSWORD = "Test-only high entropy password!42"


@pytest.fixture(scope="module")
def security_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL carerank_test")
    target = make_url(url)
    if target.get_backend_name() != "postgresql" or target.database != "carerank_test":
        pytest.fail("Security integration tests require PostgreSQL database carerank_test")
    keys = (
        "DATABASE_URL",
        "APP_ENV",
        "AUTH_COOKIE_SECURE",
        "AUTH_ALLOWED_ORIGINS",
        "AUTH_TRUSTED_PROXIES",
        "DQ_ENABLED",
    )
    original = {k: os.environ.get(k) for k in keys}
    os.environ.update(
        DATABASE_URL=url,
        APP_ENV="development",
        AUTH_COOKIE_SECURE="false",
        AUTH_ALLOWED_ORIGINS=ORIGIN,
        AUTH_TRUSTED_PROXIES="",
        DQ_ENABLED="true",
    )
    get_engine.cache_clear()
    app.dependency_overrides.clear()
    command.upgrade(Config("alembic.ini"), "head")
    command.downgrade(Config("alembic.ini"), "base")
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()
    get_engine.cache_clear()
    app.dependency_overrides.clear()
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def accounts(security_engine):
    suffix = uuid.uuid4().hex[:10]
    with Session(security_engine) as db, db.begin():
        db.execute(delete(LoginLimit))
        users = {
            role: create_user(db, f"{role}-{suffix}", f"Test {role}", role, PASSWORD)
            for role in ("administrator", "analyst", "viewer")
        }
        result = {role: {"id": user.id, "username": user.username} for role, user in users.items()}
    return result


def login(account):
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": account["username"], "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client, {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def incident(security_engine):
    path = Path(__file__).parent / "fixtures/cms_registry_a.csv"
    run = ingest(security_engine, lambda: fixture_batch(path, 5), "fixture", 5)
    with Session(security_engine) as db:
        return db.scalar(select(Alert.id).where(Alert.run_id == run))


def test_bootstrap_pristine_then_preserves_all_history(security_engine):
    # A subprocess timeout catches regressions where bootstrap and pipeline take
    # the same advisory lock on two different connections and deadlock.
    result = subprocess.run(
        [sys.executable, "-m", "app.bootstrap"], capture_output=True, text=True, timeout=60, check=True
    )
    assert "Initialized pristine" in result.stdout
    with security_engine.connect() as db:
        before = {
            table: db.scalar(text(f'SELECT count(*) FROM "{table}"'))
            for table in inspect(db).get_table_names()
        }
    assert before["providers"] == 1000 and before["encounters"] == 100000
    second = subprocess.run(
        [sys.executable, "-m", "app.bootstrap"], capture_output=True, text=True, timeout=15, check=True
    )
    assert "preserved" in second.stdout
    with security_engine.connect() as db:
        assert before == {table: db.scalar(text(f'SELECT count(*) FROM "{table}"')) for table in before}


def test_migration_003_to_004_preserves_legacy_data_and_audit(security_engine, incident):
    command.downgrade(Config("alembic.ini"), "003")
    with security_engine.connect() as db:
        tables = [name for name in inspect(db).get_table_names() if name != "alembic_version"]
        columns = {table: [c["name"] for c in inspect(db).get_columns(table)] for table in tables}
        before = {
            table: list(
                db.execute(
                    text("SELECT " + ",".join(f'"{c}"' for c in cols) + f' FROM "{table}" ORDER BY 1')
                ).mappings()
            )
            for table, cols in columns.items()
        }
    command.upgrade(Config("alembic.ini"), "004")
    with security_engine.connect() as db:
        for table, cols in columns.items():
            assert before[table] == list(
                db.execute(
                    text("SELECT " + ",".join(f'"{c}"' for c in cols) + f' FROM "{table}" ORDER BY 1')
                ).mappings()
            )
        assert db.scalar(text("SELECT actor_user_id FROM monitor_events LIMIT 1")) is None
    for table in ("monitor_events",):
        with pytest.raises(DBAPIError), security_engine.begin() as db:
            db.execute(text(f"UPDATE {table} SET note='changed'"))
    command.upgrade(Config("alembic.ini"), "head")


def test_password_hashing_and_production_configuration():
    from app.auth.config import AuthSettings
    from pydantic import ValidationError

    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first and first.startswith("scrypt$")
    assert verify_password(PASSWORD, first)
    assert not verify_password("incorrect", first)
    assert not verify_password(PASSWORD, "invalid hash")
    with pytest.raises(ValueError):
        hash_password("short")
    with pytest.raises(ValidationError):
        AuthSettings(app_env="production", auth_cookie_secure=False)


def test_development_provisioning_refuses_production(security_engine):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.auth",
            "create-user",
            "--username",
            "forbidden-prod",
            "--display-name",
            "Forbidden",
            "--role",
            "administrator",
            "--password-stdin",
        ],
        input=PASSWORD,
        capture_output=True,
        text=True,
        env={**os.environ, "APP_ENV": "production", "AUTH_COOKIE_SECURE": "true"},
    )
    assert result.returncode != 0 and PASSWORD not in result.stdout + result.stderr
    with Session(security_engine) as db:
        assert db.scalar(select(User.id).where(User.username == "forbidden-prod")) is None


@pytest.mark.parametrize(
    "path",
    [
        "/api/providers",
        "/api/providers/1",
        "/api/analytics",
        "/api/pipeline",
        "/api/analytics/quality-cost",
        "/api/analytics/evidence",
        "/api/dataops/status",
        "/api/dataops/monitoring/summary",
        "/api/dataops/monitoring/alerts",
        "/api/auth/users",
        "/api/auth/admin/users",
        "/api/auth/admin/events",
    ],
)
def test_anonymous_and_forged_identity_cannot_read(security_engine, path):
    with TestClient(app) as client:
        response = client.get(path, headers={"X-User": "administrator", "X-Role": "administrator"})
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_login_cookie_rotation_expiration_and_logout(security_engine, accounts):
    client, headers = login(accounts["analyst"])
    raw = client.cookies.get("carerank_session")
    with Session(security_engine) as db:
        session = db.get(AuthSession, token_hash(raw))
        assert session and session.token_hash != raw
        assert session.user_id == accounts["analyst"]["id"]
    assert client.get("/api/auth/me").json()["user"]["role"] == "analyst"
    rotated = client.post(
        "/api/auth/login",
        headers={"Origin": ORIGIN},
        json={"username": accounts["analyst"]["username"], "password": PASSWORD},
    )
    assert rotated.status_code == 200
    cookie = rotated.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=" in cookie
    assert client.cookies.get("carerank_session") != raw
    with Session(security_engine) as db:
        assert db.get(AuthSession, token_hash(raw)) is None
    headers["X-CSRF-Token"] = rotated.json()["csrf_token"]
    token = client.cookies.get("carerank_session")
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    client.cookies.set("carerank_session", token)
    assert client.get("/api/auth/me").status_code == 401
    client, headers = login(accounts["analyst"])
    with Session(security_engine) as db, db.begin():
        db.get(AuthSession, token_hash(client.cookies.get("carerank_session"))).expires_at = (
            now() - timedelta(seconds=1)
        )
    assert client.get("/api/providers").status_code == 401


def test_login_origin_failure_uniformity_and_sanitized_validation(security_engine, accounts):
    with TestClient(app) as client:
        data = {"username": accounts["analyst"]["username"], "password": PASSWORD}
        assert client.post("/api/auth/login", json=data).status_code == 403
        assert (
            client.post("/api/auth/login", headers={"Origin": "https://evil.invalid"}, json=data).status_code
            == 403
        )
        headers = {"Origin": ORIGIN}
        wrong = client.post("/api/auth/login", headers=headers, json={**data, "password": "wrong"})
        unknown = client.post(
            "/api/auth/login", headers=headers, json={**data, "username": "unknown-account"}
        )
        assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
        invalid = client.post("/api/auth/login", headers=headers, json={**data, "password": PASSWORD * 30})
        assert invalid.status_code == 422 and PASSWORD not in invalid.text


def test_https_login_sets_secure_cookie(security_engine, accounts, monkeypatch):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_ALLOWED_ORIGINS", "https://testserver")
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": "https://testserver"},
            json={"username": accounts["viewer"]["username"], "password": PASSWORD},
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
        assert client.get("/api/providers").status_code == 200
        assert "password_hash" not in response.text


def test_login_rate_limit_shared_across_clients(security_engine, accounts):
    username = accounts["analyst"]["username"]
    for _ in range(10):
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                headers={"Origin": ORIGIN, "X-Forwarded-For": str(uuid.uuid4())},
                json={"username": username, "password": "wrong"},
            )
        assert response.status_code == 401
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login", headers={"Origin": ORIGIN}, json={"username": username, "password": PASSWORD}
        )
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    with Session(security_engine) as db:
        assert all(username not in key for key in db.scalars(select(LoginLimit.key)))


@pytest.mark.parametrize("role", ["viewer", "analyst"])
def test_non_admin_cannot_manage_accounts_or_read_security_audit(security_engine, accounts, role):
    client, headers = login(accounts[role])
    assert client.get("/api/auth/admin/users").status_code == 403
    assert client.get("/api/auth/admin/events").status_code == 403
    assert (
        client.patch(
            f"/api/auth/users/{accounts[role]['id']}",
            headers=headers,
            json={"expected_revision": 1, "role": "administrator"},
        ).status_code
        == 403
    )


def test_incident_mutation_requires_identity_role_csrf_and_origin(security_engine, accounts, incident):
    url = f"/api/dataops/monitoring/alerts/{incident}/actions"
    data = {"expected_revision": 1, "status": "acknowledged", "note": "Verified source evidence"}
    with TestClient(app) as anonymous:
        assert (
            anonymous.post(url, headers={"Origin": ORIGIN, "X-User": "admin"}, json=data).status_code == 401
        )
    viewer, headers = login(accounts["viewer"])
    assert viewer.post(url, headers=headers, json=data).status_code == 403
    analyst, headers = login(accounts["analyst"])
    assert analyst.post(url, json=data).status_code == 403
    assert analyst.post(url, headers={"Origin": ORIGIN}, json=data).status_code == 403
    assert (
        analyst.post(url, headers={**headers, "Origin": "https://evil.invalid"}, json=data).status_code == 403
    )
    assert analyst.post(url, headers={**headers, "X-CSRF-Token": "incorrect"}, json=data).status_code == 403
    assert (
        analyst.post(
            url, headers=[(b"origin", ORIGIN.encode()), (b"x-csrf-token", b"\xff")], json=data
        ).status_code
        == 403
    )
    assert analyst.post(url, headers=headers, json={**data, "actor": "forged"}).status_code == 422
    with Session(security_engine) as db:
        assert db.get(Alert, incident).revision == 1
        assert (
            db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.alert_id == incident))
            == 1
        )


def test_authenticated_lifecycle_assignments_history_and_conflicts(security_engine, accounts, incident):
    client, headers = login(accounts["analyst"])
    url = f"/api/dataops/monitoring/alerts/{incident}/actions"
    for revision, status in enumerate(["acknowledged", "investigating", "resolved", "open"], 1):
        response = client.post(
            url,
            headers=headers,
            json={
                "expected_revision": revision,
                "status": status,
                "assigned_to": accounts["analyst"]["id"],
                "note": f"Evidence decision {revision}",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["revision"] == revision + 1
    assert (
        client.post(url, headers=headers, json={"expected_revision": 1, "note": "Stale"}).status_code == 409
    )
    assert (
        client.post(
            url,
            headers=headers,
            json={"expected_revision": 5, "status": "resolved", "note": "Invalid transition"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            headers=headers,
            json={
                "expected_revision": 5,
                "assigned_to": accounts["viewer"]["id"],
                "note": "Invalid assignment",
            },
        ).status_code
        == 422
    )
    result = client.post(
        url, headers=headers, json={"expected_revision": 5, "assigned_to": "", "note": "Release ownership"}
    )
    assert result.status_code == 200, result.text
    events = client.get(f"/api/dataops/monitoring/alerts/{incident}/events").json()["items"]
    assert len(events) == 6
    assert {e["actor_user_id"] for e in events if e["revision"] > 1} == {accounts["analyst"]["id"]}
    assert events[0]["previous_assigned_user_id"] == accounts["analyst"]["id"]
    assert events[0]["assigned_user_id"] is None
    assert all(PASSWORD not in json.dumps(e) for e in events)
    with Session(security_engine) as db:
        alert = db.get(Alert, incident)
        assert alert.status == "open" and alert.resolution is None and alert.assigned_user_id is None


def test_concurrent_authenticated_decisions_have_one_winner(security_engine, accounts, incident):
    client, headers = login(accounts["analyst"])
    token = client.cookies.get("carerank_session")

    def decide(_):
        with TestClient(app) as separate:
            separate.cookies.set("carerank_session", token)
            return separate.post(
                f"/api/dataops/monitoring/alerts/{incident}/actions",
                headers=headers,
                json={"expected_revision": 1, "status": "acknowledged", "note": "Concurrent review"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(decide, range(2))) == [200, 409]
    with Session(security_engine) as db:
        assert db.get(Alert, incident).revision == 2
        assert (
            db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.alert_id == incident))
            == 2
        )


@pytest.mark.parametrize("change, expected", [("revoked", 401), ("disabled", 401), ("demoted", 403)])
def test_write_rechecks_identity_after_authorization_dependency(
    security_engine, accounts, incident, monkeypatch, change, expected
):
    """A dependency-approved request must not use identity cached before a revocation."""
    from app.monitoring import api

    client, headers = login(accounts["analyst"])
    original = api.investigate_authenticated

    def intervene(db, alert_id, identity, action):
        with Session(security_engine) as other, other.begin():
            if change == "revoked":
                other.execute(delete(AuthSession).where(AuthSession.user_id == identity.user.id))
            else:
                user = other.get(User, identity.user.id)
                if change == "disabled":
                    user.active = False
                else:
                    user.role = "viewer"
        return original(db, alert_id, identity, action)

    monkeypatch.setattr(api, "investigate_authenticated", intervene)
    response = client.post(
        f"/api/dataops/monitoring/alerts/{incident}/actions",
        headers=headers,
        json={"expected_revision": 1, "status": "acknowledged", "note": "Stale authorization"},
    )
    assert response.status_code == expected
    with Session(security_engine) as db:
        assert db.get(Alert, incident).revision == 1
        assert (
            db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.alert_id == incident))
            == 1
        )


def test_admin_changes_revoke_sessions_and_append_audit(security_engine, accounts):
    analyst, _ = login(accounts["analyst"])
    admin, headers = login(accounts["administrator"])
    response = admin.patch(
        f"/api/auth/users/{accounts['analyst']['id']}",
        headers=headers,
        json={"expected_revision": 1, "role": "viewer"},
    )
    assert response.status_code == 200, response.text
    assert analyst.get("/api/providers").status_code == 401
    events = admin.get("/api/auth/admin/events").json()
    changed = next(e for e in events if e["action"] == "account_updated")
    assert changed["actor_user_id"] == accounts["administrator"]["id"]
    assert changed["details"] == {
        "before": {"role": "analyst", "active": True, "revision": 1},
        "after": {"role": "viewer", "active": True, "revision": 2},
    }
    assert (
        admin.patch(
            f"/api/auth/users/{accounts['analyst']['id']}",
            headers=headers,
            json={"expected_revision": 2, "active": False},
        ).status_code
        == 200
    )
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/auth/login",
                headers={"Origin": ORIGIN},
                json={"username": accounts["analyst"]["username"], "password": PASSWORD},
            ).status_code
            == 401
        )
    for operation in ("UPDATE auth_events SET action='tampered'", "DELETE FROM auth_events"):
        with pytest.raises(DBAPIError), security_engine.begin() as db:
            db.execute(text(operation))


def test_last_administrator_cannot_be_disabled(security_engine, accounts):
    admin, headers = login(accounts["administrator"])
    with Session(security_engine) as db, db.begin():
        previous = list(
            db.scalars(
                select(User).where(
                    User.role == "administrator",
                    User.id != accounts["administrator"]["id"],
                    User.active.is_(True),
                )
            )
        )
        ids = [u.id for u in previous]
        for user in previous:
            user.active = False
    try:
        response = admin.patch(
            f"/api/auth/users/{accounts['administrator']['id']}",
            headers=headers,
            json={"expected_revision": 1, "active": False},
        )
        assert response.status_code == 409
        assert admin.get("/api/auth/me").status_code == 200
    finally:
        with Session(security_engine) as db, db.begin():
            for user_id in ids:
                db.get(User, user_id).active = True


def second_administrator(engine):
    with Session(engine) as db, db.begin():
        user = create_user(
            db, f"second-{uuid.uuid4().hex[:10]}", "Second administrator", "administrator", PASSWORD
        )
        return {"id": user.id, "username": user.username}


@pytest.mark.parametrize(
    "first_change, stale_change, final_role, final_active",
    [
        ({"role": "viewer"}, {"role": "analyst", "active": False}, "viewer", True),
        ({"active": False}, {"role": "viewer", "active": True}, "analyst", False),
    ],
)
def test_two_administrators_cannot_restore_stale_access(
    security_engine, accounts, first_change, stale_change, final_role, final_active
):
    first, first_headers = login(accounts["administrator"])
    second, second_headers = login(second_administrator(security_engine))
    target = accounts["analyst"]["id"]
    cached = next(u for u in second.get("/api/auth/admin/users").json() if u["id"] == target)
    assert cached["revision"] == 1
    changed = first.patch(
        f"/api/auth/users/{target}",
        headers=first_headers,
        json={"expected_revision": 1, **first_change},
    )
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    stale = second.patch(
        f"/api/auth/users/{target}",
        headers=second_headers,
        json={"expected_revision": cached["revision"], **stale_change},
    )
    assert stale.status_code == 409
    with Session(security_engine) as db:
        user = db.get(User, target)
        assert (user.role, user.active, user.revision) == (final_role, final_active, 2)
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.subject_user_id == target, SecurityEvent.action == "account_updated")
            )
            == 1
        )


@pytest.mark.parametrize("change", [{"role": "viewer"}, {"active": False}])
def test_administrator_revoked_during_inflight_update(security_engine, accounts, monkeypatch, change):
    """Pause a real request after dependencies, revoke it using another authenticated admin."""
    from app.auth import api

    first, first_headers = login(accounts["administrator"])
    second, second_headers = login(second_administrator(security_engine))
    entered, release, guard = Event(), Event(), Lock()
    original = api.security_lock
    waiting = False

    def pause_first(db):
        nonlocal waiting
        with guard:
            pause = not waiting
            waiting = True
        if pause:
            entered.set()
            assert release.wait(10), "Concurrent revocation did not complete"
        original(db)

    monkeypatch.setattr(api, "security_lock", pause_first)
    target = accounts["analyst"]["id"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            first.patch,
            f"/api/auth/users/{target}",
            headers=first_headers,
            json={"expected_revision": 1, "role": "viewer"},
        )
        try:
            assert entered.wait(10), "Pending administrator never reached transaction boundary"
            revoked = second.patch(
                f"/api/auth/users/{accounts['administrator']['id']}",
                headers=second_headers,
                json={"expected_revision": 1, **change},
            )
            assert revoked.status_code == 200, revoked.text
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 401
    with Session(security_engine) as db:
        assert db.get(User, target).role == "analyst"
        assert db.get(User, target).revision == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.subject_user_id == target, SecurityEvent.action == "account_updated")
            )
            == 0
        )


def test_concurrent_last_administrators_cannot_both_demote(security_engine, accounts, monkeypatch):
    from app.auth import api

    second = second_administrator(security_engine)
    administrators = [accounts["administrator"], second]
    clients = [login(account) for account in administrators]
    keep = [account["id"] for account in administrators]
    with Session(security_engine) as db, db.begin():
        previous = list(
            db.scalars(
                select(User).where(User.role == "administrator", User.active.is_(True), User.id.not_in(keep))
            )
        )
        ids = [user.id for user in previous]
        for user in previous:
            user.active = False
    barrier = Barrier(2)
    original = api.security_lock

    def meet(db):
        barrier.wait(timeout=10)
        original(db)

    monkeypatch.setattr(api, "security_lock", meet)

    def demote(index):
        client, headers = clients[index]
        return client.patch(
            f"/api/auth/users/{administrators[index]['id']}",
            headers=headers,
            json={"expected_revision": 1, "role": "viewer"},
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(demote, range(2))) == [200, 409]
        with Session(security_engine) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == "administrator", User.active.is_(True))
                )
                == 1
            )
    finally:
        with Session(security_engine) as db, db.begin():
            for user_id in ids:
                db.get(User, user_id).active = True


def test_account_change_and_session_revocation_roll_back_when_audit_insert_fails(
    security_engine, accounts, monkeypatch
):
    from app.auth import api

    analyst, _ = login(accounts["analyst"])
    admin, headers = login(accounts["administrator"])
    original = api.record_event

    def invalid_audit(db, action, **fields):
        # The real PostgreSQL foreign key rejects this audit INSERT at commit.
        original(db, action, **{**fields, "actor": str(uuid.uuid4())})

    monkeypatch.setattr(api, "record_event", invalid_audit)
    target = accounts["analyst"]["id"]
    response = admin.patch(
        f"/api/auth/users/{target}",
        headers=headers,
        json={"expected_revision": 1, "role": "viewer", "active": False},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable. Check connection and migrations."}
    assert PASSWORD not in response.text and "INSERT" not in response.text
    with Session(security_engine) as db:
        user = db.get(User, target)
        assert (user.role, user.active, user.revision) == ("analyst", True, 1)
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.subject_user_id == target, SecurityEvent.action == "account_updated")
            )
            == 0
        )
    assert analyst.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "viewer"},
        {"expected_revision": 0, "role": "viewer"},
        {"expected_revision": 1},
        {"expected_revision": 1, "role": None},
        {"expected_revision": 1, "active": None},
        {"expected_revision": 1, "role": "viewer", "revision": 99},
    ],
)
def test_account_update_requires_valid_revision_and_intent(security_engine, accounts, payload):
    admin, headers = login(accounts["administrator"])
    target = accounts["analyst"]["id"]
    assert admin.patch(f"/api/auth/users/{target}", headers=headers, json=payload).status_code == 422
    with Session(security_engine) as db:
        assert db.get(User, target).revision == 1
        assert db.get(User, target).role == "analyst"


def test_account_update_rejects_anonymous_and_invalid_csrf(security_engine, accounts):
    target = accounts["analyst"]["id"]
    url = f"/api/auth/users/{target}"
    body = {"expected_revision": 1, "role": "administrator"}
    with TestClient(app) as client:
        assert (
            client.patch(url, headers={"Origin": ORIGIN, "X-Role": "administrator"}, json=body).status_code
            == 401
        )
    admin, headers = login(accounts["administrator"])
    for denied in (
        {},
        {"Origin": ORIGIN},
        {**headers, "Origin": "https://evil.invalid"},
        {**headers, "X-CSRF-Token": "invalid"},
    ):
        assert admin.patch(url, headers=denied, json=body).status_code == 403
    with Session(security_engine) as db:
        assert db.get(User, target).role == "analyst"
        assert db.get(User, target).revision == 1


def request_from(address, **headers):
    return Request(
        {
            "type": "http",
            "client": (address, 1234),
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        }
    )


def test_forwarding_identity_only_from_explicit_trusted_proxy(monkeypatch):
    from app.auth.throttle import source_address

    monkeypatch.setenv("AUTH_TRUSTED_PROXIES", "192.0.2.1/32")
    assert (
        source_address(
            request_from(
                "192.0.2.2", **{"X-CareRank-Client-IP": "198.51.100.1", "X-Forwarded-For": "198.51.100.2"}
            )
        )
        == "192.0.2.2"
    )
    assert (
        source_address(
            request_from(
                "192.0.2.1", **{"X-CareRank-Client-IP": "198.51.100.1", "X-Forwarded-For": "198.51.100.2"}
            )
        )
        == "198.51.100.1"
    )
    assert source_address(request_from("::ffff:203.0.113.9")) == "203.0.113.9"
    assert (
        source_address(request_from("192.0.2.1", **{"X-CareRank-Client-IP": "::ffff:203.0.113.9"}))
        == "203.0.113.9"
    )
    for value in ("", "invalid", "198.51.100.1, 198.51.100.2", "fe80::1%eth0"):
        with pytest.raises(HTTPException) as error:
            source_address(request_from("192.0.2.1", **{"X-CareRank-Client-IP": value}))
        assert error.value.status_code == 400


def test_blocked_source_allocates_no_username_rows_or_cleanup_work(security_engine, accounts):
    from app.auth.throttle import throttle

    request = request_from("192.0.2.30")
    for index in range(30):
        with Session(security_engine) as db:
            throttle(db, request, f"initial-{index}")
    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(security_engine, "before_cursor_execute", observe)
    try:
        for index in range(100):
            with Session(security_engine) as db, pytest.raises(HTTPException) as error:
                throttle(db, request, f"arbitrary-new-name-{index}")
            assert error.value.status_code == 429
    finally:
        event.remove(security_engine, "before_cursor_execute", observe)
    limit_queries = [sql for sql in statements if "auth_login_limits" in sql]
    assert len(limit_queries) == 100
    assert all(sql.lstrip().startswith("select") and "count(" not in sql for sql in limit_queries)
    with Session(security_engine) as db:
        assert db.scalar(select(func.count()).select_from(LoginLimit)) == 31


def test_login_bucket_capacity_is_atomic_across_connections(security_engine, accounts, monkeypatch):
    from app.auth import throttle as limits

    monkeypatch.setattr(limits, "MAX_BUCKETS", 12)
    barrier = Barrier(8)

    def attempt(index):
        barrier.wait(timeout=10)
        with Session(security_engine) as db:
            try:
                limits.throttle(db, request_from(f"192.0.2.{index + 1}"), f"unique-{index}")
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sorted(results) == [200] * 6 + [429] * 2
    with Session(security_engine) as db:
        assert db.scalar(select(func.count()).select_from(LoginLimit)) == 12
        assert set(db.scalars(select(LoginLimit.attempts))) == {1}


def test_concurrent_source_limit_has_exact_budget_and_bounded_rows(security_engine, accounts):
    from app.auth.throttle import throttle

    barrier = Barrier(8)

    def attempt(index):
        barrier.wait(timeout=10)
        with Session(security_engine) as db:
            try:
                throttle(db, request_from("192.0.2.50"), f"parallel-name-{index}")
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(40)))
    assert sorted(results) == [200] * 30 + [429] * 10
    with Session(security_engine) as db:
        assert db.get(LoginLimit, token_hash("ip:192.0.2.50")).attempts == 30
        assert db.scalar(select(func.count()).select_from(LoginLimit)) == 31


def test_expiry_cleanup_is_indexed_bounded_and_preserves_live_limits(security_engine, accounts):
    from app.auth.throttle import CLEANUP_BATCH, WINDOW, throttle

    with Session(security_engine) as db, db.begin():
        db.add_all(
            [
                LoginLimit(key=token_hash(f"expired-{i}"), window_start=now() - WINDOW * 2, attempts=10)
                for i in range(CLEANUP_BATCH + 7)
            ]
        )
        db.add(LoginLimit(key=token_hash("live"), window_start=now(), attempts=10))
    with Session(security_engine) as db:
        throttle(db, request_from("192.0.2.40"), "fresh-user")
    with Session(security_engine) as db:
        assert db.scalar(select(func.count()).select_from(LoginLimit)) == 10
        assert db.get(LoginLimit, token_hash("live")).attempts == 10
        assert (
            db.scalar(
                select(func.count()).select_from(LoginLimit).where(LoginLimit.window_start <= now() - WINDOW)
            )
            == 7
        )
    indexes = inspect(security_engine).get_indexes("auth_login_limits")
    assert any(index["column_names"] == ["window_start", "key"] for index in indexes)


def test_account_limit_spans_sources_without_blocking_unrelated_account(security_engine, accounts):
    from app.auth.throttle import throttle

    for index in range(10):
        with Session(security_engine) as db:
            throttle(db, request_from(f"192.0.2.{index + 1}"), "target-account")
    with Session(security_engine) as db, pytest.raises(HTTPException) as error:
        throttle(db, request_from("198.51.100.1"), "target-account")
    assert error.value.status_code == 429
    with Session(security_engine) as db:
        throttle(db, request_from("198.51.100.2"), "unrelated-account")
        assert db.get(LoginLimit, token_hash("user:unrelated-account")).attempts == 1


def test_migration_004_to_005_preserves_existing_accounts_sessions_and_history(security_engine, accounts):
    """Downgrade only the explicitly guarded disposable test database to exercise the upgrade."""
    client, _ = login(accounts["administrator"])
    command.downgrade(Config("alembic.ini"), "004")
    with security_engine.connect() as db:
        tables = [name for name in inspect(db).get_table_names() if name != "alembic_version"]
        columns = {table: [column["name"] for column in inspect(db).get_columns(table)] for table in tables}
        before = {
            table: list(
                db.execute(
                    text(
                        "SELECT "
                        + ",".join(f'"{column}"' for column in names)
                        + f' FROM "{table}" ORDER BY 1'
                    )
                ).mappings()
            )
            for table, names in columns.items()
        }
    command.upgrade(Config("alembic.ini"), "005")
    with security_engine.connect() as db:
        for table, names in columns.items():
            assert before[table] == list(
                db.execute(
                    text(
                        "SELECT "
                        + ",".join(f'"{column}"' for column in names)
                        + f' FROM "{table}" ORDER BY 1'
                    )
                ).mappings()
            ), f"Migration changed existing rows in {table}"
        assert db.scalar(text("SELECT count(*) FROM auth_users WHERE revision <> 1")) == 0
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("url", ["postgresql+psycopg://localhost/carerank", "sqlite:////tmp/carerank"])
def test_security_migration_refuses_retained_database_downgrade(monkeypatch, url):
    import importlib
    from types import SimpleNamespace

    migration = importlib.import_module("migrations.versions.005_security_review")
    monkeypatch.setattr(
        migration.op, "get_bind", lambda: SimpleNamespace(engine=SimpleNamespace(url=make_url(url)))
    )
    with pytest.raises(RuntimeError, match="forward-only"):
        migration.downgrade()
