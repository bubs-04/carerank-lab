"""Generate separate local operator/API credentials without changing existing secrets."""

import fcntl
import os
import secrets
from pathlib import Path


def main():
    target = Path(__file__).resolve().parents[1] / ".env"
    # Append missing keys for upgrades; preserve every existing setting/password.
    with os.fdopen(os.open(target, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600), "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        os.fchmod(f.fileno(), 0o600)
        f.seek(0)
        content = f.read()
        keys = {line.split("=", 1)[0].strip() for line in content.splitlines() if "=" in line}
        missing = [key for key in ("POSTGRES_PASSWORD", "API_DATABASE_PASSWORD") if key not in keys]
        if missing and content and not content.endswith("\n"):
            f.write("\n")
        for key in missing:
            f.write(key + "=" + secrets.token_hex(24) + "\n")
    target.chmod(0o600)
    print("Local credentials ready; existing settings preserved")


if __name__ == "__main__":
    main()
