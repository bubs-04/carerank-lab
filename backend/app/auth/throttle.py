"""Bounded shared login limits. Only a trusted immediate proxy may identify a client."""

from datetime import timedelta
from ipaddress import ip_address, ip_network
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from .dependencies import settings
from .models import LoginLimit
from .security import now, token_hash, utc
from .service import security_lock

WINDOW = timedelta(minutes=15)
MAX_BUCKETS = 10000
CLEANUP_BATCH = 100


def canonical_address(value):
    address = ip_address(value)
    if getattr(address, "scope_id", None):
        raise ValueError("Scoped client addresses are not supported")
    return getattr(address, "ipv4_mapped", None) or address


def source_address(request):
    peer = request.client.host if request.client else "unknown"
    try:
        address = canonical_address(peer)
    except ValueError:
        return peer
    trusted = any(
        address in ip_network(c.strip(), strict=False)
        for c in settings().auth_trusted_proxies.split(",")
        if c.strip()
    )
    if trusted:
        # No header chains. Nginx/Vite must OVERWRITE this value at the trust boundary.
        supplied = request.headers.get("x-carerank-client-ip", "")
        try:
            return str(canonical_address(supplied))
        except ValueError:
            raise HTTPException(400, "Trusted proxy must supply a valid client address") from None
    return str(address)


def throttle(db, request, username):
    security_lock(db)
    moment = now()

    def reject():
        db.commit()
        raise HTTPException(
            429, "Too many sign-in attempts. Try again later.", headers={"Retry-After": "900"}
        )

    def bucket(key):
        row = db.get(LoginLimit, token_hash(key), populate_existing=True)
        if row and utc(row.window_start) <= moment - WINDOW:
            row.window_start, row.attempts = moment, 0
        return row

    # A blocked source causes one indexed lookup and no cleanup, counts or username allocation.
    source = source_address(request)
    source_row = bucket("ip:" + source)
    if source_row and source_row.attempts >= 30:
        reject()
    account_row = bucket("user:" + username)
    # Account exhaustion also consumes source budget, preventing unlimited cheap probes.
    rows = [(source_row, "ip:" + source), (account_row, "user:" + username)]
    missing = sum(row is None for row, _ in rows)
    if missing:
        expired = (
            select(LoginLimit.key)
            .where(LoginLimit.window_start <= moment - WINDOW)
            .order_by(LoginLimit.window_start, LoginLimit.key)
            .limit(CLEANUP_BATCH)
        )
        db.execute(delete(LoginLimit).where(LoginLimit.key.in_(expired)))
        # Hard cap, serialized with all insertions across workers. No eviction of live limits.
        if db.scalar(select(func.count()).select_from(LoginLimit)) + missing > MAX_BUCKETS:
            reject()
    if source_row is None:
        source_row = LoginLimit(key=token_hash("ip:" + source), window_start=moment, attempts=0)
        db.add(source_row)
    source_row.attempts += 1
    if account_row and account_row.attempts >= 10:
        reject()
    if account_row is None:
        account_row = LoginLimit(key=token_hash("user:" + username), window_start=moment, attempts=0)
        db.add(account_row)
    account_row.attempts += 1
    db.commit()
