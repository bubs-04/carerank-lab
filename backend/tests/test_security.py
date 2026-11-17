"""Real PostgreSQL authentication and authorization boundaries, without identity mocks.

Every schema reset is guarded by the exact disposable database name. Existing
domain tests use a viewer override; this module exercises real passwords/cookies.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import json
import os
import subprocess
import sys
import uuid

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, delete, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.main import app
from app.db import get_engine
from app.auth.models import AuthSession, LoginLimit, User
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
    keys = ("DATABASE_URL", "APP_ENV", "AUTH_COOKIE_SECURE", "AUTH_ALLOWED_ORIGINS", "DQ_ENABLED")
    original = {k: os.environ.get(k) for k in keys}
    os.environ.update(
        DATABASE_URL=url,
        APP_ENV="development",
        AUTH_COOKIE_SECURE="false",
        AUTH_ALLOWED_ORIGINS=ORIGIN,
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
            f"/api/auth/users/{accounts[role]['id']}", headers=headers, json={"role": "administrator"}
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
        f"/api/auth/users/{accounts['analyst']['id']}", headers=headers, json={"role": "viewer"}
    )
    assert response.status_code == 200, response.text
    assert analyst.get("/api/providers").status_code == 401
    events = admin.get("/api/auth/admin/events").json()
    changed = next(e for e in events if e["action"] == "account_updated")
    assert changed["actor_user_id"] == accounts["administrator"]["id"]
    assert changed["details"] == {
        "before": {"role": "analyst", "active": True},
        "after": {"role": "viewer", "active": True},
    }
    assert (
        admin.patch(
            f"/api/auth/users/{accounts['analyst']['id']}", headers=headers, json={"active": False}
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
            f"/api/auth/users/{accounts['administrator']['id']}", headers=headers, json={"active": False}
        )
        assert response.status_code == 409
        assert admin.get("/api/auth/me").status_code == 200
    finally:
        with Session(security_engine) as db, db.begin():
            for user_id in ids:
                db.get(User, user_id).active = True
