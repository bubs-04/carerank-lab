import re
import uuid
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .models import User, SecurityEvent, AuthSession
from .security import hash_password, now, utc


def security_lock(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '10s'"))
        db.execute(text("SELECT pg_advisory_xact_lock(721407)"))


def record_event(db, action, actor=None, subject=None, details=None):
    db.add(
        SecurityEvent(
            id=str(uuid.uuid4()),
            action=action,
            actor_user_id=actor,
            subject_user_id=subject,
            details=details or {},
            created_at=now(),
        )
    )


def recheck_identity(db, identity, roles):
    """Recheck authorization after acquiring security_lock, inside the write transaction."""
    from fastapi import HTTPException

    user = db.get(User, identity.user.id, populate_existing=True, with_for_update=True)
    session = db.get(AuthSession, identity.session.token_hash, populate_existing=True)
    if not user or not user.active or not session or utc(session.expires_at) <= now():
        raise HTTPException(401, "Sign in to continue")
    if session.user_id != user.id or user.role not in roles:
        raise HTTPException(403, "Your role does not permit this action")
    return user


def create_user(db: Session, username: str, display_name: str, role: str, password: str) -> User:
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,79}", username):
        raise ValueError("Username must be 3–80 lowercase letters, numbers, dots, underscores or hyphens")
    if not display_name.strip() or len(display_name) > 100:
        raise ValueError("Display name must contain 1 to 100 characters")
    if role not in {"administrator", "analyst", "viewer"}:
        raise ValueError("Invalid account role")
    if db.scalar(select(User).where(User.username == username)):
        raise ValueError("Username already exists")
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        display_name=display_name.strip(),
        role=role,
        password_hash=hash_password(password),
        active=True,
        created_at=now(),
    )
    db.add(user)
    db.flush()
    record_event(
        db, "account_provisioned", subject=user.id, details={"role": role, "method": "development_cli"}
    )
    return user
