from dataclasses import dataclass
from typing import Annotated
import hmac
from fastapi import Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from ..db import get_engine
from .config import AuthSettings
from .models import User, AuthSession
from .security import now, utc, token_hash

COOKIE = "carerank_session"


def settings():
    try:
        return AuthSettings()
    except ValidationError:
        raise HTTPException(503, "Authentication configuration invalid") from None


def get_auth_session():
    # READ COMMITTED is deliberate: authorization writes recheck state under locks.
    with Session(get_engine()) as db:
        yield db


AuthDB = Annotated[Session, Depends(get_auth_session)]


@dataclass
class Identity:
    user: User
    session: AuthSession


def require_user(request: Request, db: AuthDB) -> Identity:
    raw = request.cookies.get(COOKIE, "")
    session = db.get(AuthSession, token_hash(raw)) if 20 <= len(raw) <= 200 else None
    user = db.get(User, session.user_id) if session else None
    if not session or utc(session.expires_at) <= now() or not user or not user.active:
        raise HTTPException(401, "Sign in to continue")
    return Identity(user, session)


CurrentUser = Annotated[Identity, Depends(require_user)]


def require_origin(request: Request):
    origin = request.headers.get("origin", "")
    if origin not in settings().origins or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Request origin is not allowed")


def require_csrf(request: Request, identity: CurrentUser):
    require_origin(request)
    provided = request.headers.get("x-csrf-token", "")
    if not provided or not hmac.compare_digest(provided.encode(), identity.session.csrf_token.encode()):
        raise HTTPException(403, "CSRF verification failed")
    return identity


Writer = Annotated[Identity, Depends(require_csrf)]


def require_analyst(identity: Writer):
    if identity.user.role not in {"analyst", "administrator"}:
        raise HTTPException(403, "Analyst or administrator role required")
    return identity


Analyst = Annotated[Identity, Depends(require_analyst)]


def require_administrator(identity: Writer):
    if identity.user.role != "administrator":
        raise HTTPException(403, "Administrator role required")
    return identity


Administrator = Annotated[Identity, Depends(require_administrator)]
