"""Standard-library scrypt password hashing; random 256-bit bearer session tokens."""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError("Password must contain 12 to 256 characters")
    salt = secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=67108864)
    return f"scrypt$32768$8$3${salt}${result.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (32768, 8, 3):
            return False
        result = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=67108864
        )
        return hmac.compare_digest(result.hex(), expected)
    except (ValueError, TypeError):
        return False


# Equal-cost verification for unknown accounts prevents trivial account enumeration.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
