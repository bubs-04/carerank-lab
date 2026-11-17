import secrets
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, func
from .dependencies import AuthDB, CurrentUser, Writer, Administrator, COOKIE, require_origin, settings
from .models import User, AuthSession, LoginLimit, SecurityEvent
from .security import now, token_hash, verify_password, DUMMY_HASH
from .service import security_lock, record_event, recheck_identity

router = APIRouter(prefix="/api/auth", tags=["Authentication and authorization"])


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    display_name: str
    role: Literal["administrator", "analyst", "viewer"]


class SessionView(BaseModel):
    user: UserView
    csrf_token: str


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


def throttle(db, request, username):
    """Shared bounded windows across API workers; forwarded IP headers are never trusted."""
    security_lock(db)
    moment = now()
    # Expired bucket cleanup bounds storage under repeated arbitrary usernames.
    db.execute(delete(LoginLimit).where(LoginLimit.window_start < moment - timedelta(minutes=15)))
    blocked = False
    for key, maximum in [
        ("ip:" + (request.client.host if request.client else "unknown"), 30),
        ("user:" + username, 10),
    ]:
        key = token_hash(key)
        limit = db.get(LoginLimit, key)
        if limit is None:
            limit = LoginLimit(key=key, window_start=moment, attempts=0)
            db.add(limit)
        if limit.attempts >= maximum:
            blocked = True
        else:
            limit.attempts += 1
    db.commit()
    if blocked:
        raise HTTPException(
            429, "Too many sign-in attempts. Try again later.", headers={"Retry-After": "900"}
        )


@router.post("/login", response_model=SessionView)
def login(body: Login, request: Request, response: Response, db: AuthDB):
    require_origin(request)
    config = settings()
    username = body.username.strip().lower()
    throttle(db, request, username)
    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        record_event(db, "login_failed")
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    # Recheck account state after the expensive password operation and serialize with administration.
    security_lock(db)
    db.refresh(user, with_for_update=True)
    if not user.active:
        raise HTTPException(401, "Invalid username or password")
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    previous = request.cookies.get(COOKIE)
    if previous:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(previous)))
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now()))
    db.add(
        AuthSession(
            token_hash=token_hash(raw),
            user_id=user.id,
            csrf_token=csrf,
            created_at=now(),
            expires_at=now() + timedelta(seconds=config.auth_session_seconds),
        )
    )
    record_event(db, "login", actor=user.id, subject=user.id)
    result = {"user": UserView.model_validate(user), "csrf_token": csrf}
    db.commit()
    response.set_cookie(
        COOKIE,
        raw,
        max_age=config.auth_session_seconds,
        secure=config.auth_cookie_secure,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return result


@router.get("/me", response_model=SessionView)
def me(identity: CurrentUser):
    return {"user": identity.user, "csrf_token": identity.session.csrf_token}


@router.post("/logout", status_code=204)
def logout(identity: Writer, db: AuthDB, response: Response):
    security_lock(db)
    recheck_identity(db, identity, {"administrator", "analyst", "viewer"})
    db.execute(delete(AuthSession).where(AuthSession.token_hash == identity.session.token_hash))
    record_event(db, "logout", actor=identity.user.id, subject=identity.user.id)
    db.commit()
    response.delete_cookie(COOKIE, secure=settings().auth_cookie_secure, httponly=True, samesite="strict")


@router.get("/users", response_model=list[UserView])
def assignable_users(identity: CurrentUser, db: AuthDB):
    return list(
        db.scalars(
            select(User)
            .where(User.active.is_(True), User.role.in_(["analyst", "administrator"]))
            .order_by(User.display_name, User.id)
            .limit(1000)
        )
    )


class ManagedUser(UserView):
    active: bool


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["administrator", "analyst", "viewer"] | None = None
    active: bool | None = None


@router.get("/admin/users", response_model=list[ManagedUser])
def managed_users(identity: CurrentUser, db: AuthDB):
    if identity.user.role != "administrator":
        raise HTTPException(403, "Administrator role required")
    return list(db.scalars(select(User).order_by(User.username).limit(1000)))


@router.patch("/users/{user_id}", response_model=ManagedUser)
def update_user(user_id: str, body: AccountUpdate, identity: Administrator, db: AuthDB):
    if not body.model_fields_set or (body.role is None and body.active is None):
        raise HTTPException(422, "Supply role or active")
    security_lock(db)
    recheck_identity(db, identity, {"administrator"})
    target = db.get(User, user_id, with_for_update=True)
    if not target:
        raise HTTPException(404, "Account not found")
    before = {"role": target.role, "active": target.active}
    demoting = body.role is not None and body.role != "administrator"
    if target.active and target.role == "administrator" and (demoting or body.active is False):
        count = db.scalar(
            select(func.count()).select_from(User).where(User.active.is_(True), User.role == "administrator")
        )
        if count <= 1:
            raise HTTPException(409, "At least one active administrator must remain")
    if body.role is not None:
        target.role = body.role
    if body.active is not None:
        target.active = body.active
    after = {"role": target.role, "active": target.active}
    db.execute(delete(AuthSession).where(AuthSession.user_id == target.id))
    record_event(
        db,
        "account_updated",
        actor=identity.user.id,
        subject=target.id,
        details={"before": before, "after": after},
    )
    result = ManagedUser.model_validate(target)
    db.commit()
    return result


@router.get("/admin/events")
def security_events(identity: CurrentUser, db: AuthDB):
    if identity.user.role != "administrator":
        raise HTTPException(403, "Administrator role required")
    return [
        {
            "id": e.id,
            "actor_user_id": e.actor_user_id,
            "subject_user_id": e.subject_user_id,
            "action": e.action,
            "details": e.details,
            "created_at": e.created_at,
        }
        for e in db.scalars(
            select(SecurityEvent).order_by(SecurityEvent.created_at.desc(), SecurityEvent.id).limit(100)
        )
    ]
