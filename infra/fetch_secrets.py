"""Explicit operator step: retrieve three approved Secrets Manager values to private files.

Never invoked by application startup, CloudFormation UserData or pull-request CI.
"""

import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, urlencode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--database-host", required=True)
    parser.add_argument("--directory", default="/run/carerank-secrets")
    for role in ("owner", "api", "worker"):
        parser.add_argument(f"--{role}-secret-arn", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError("Run through the approved root operator session")
    if not re.fullmatch(
        r"[a-z0-9.-]+\.rds\.amazonaws\.com(?:\.cn)?", args.database_host
    ):
        raise ValueError("A private RDS endpoint is required")
    directory = Path(args.directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("Use a root-owned directory with mode 0700")
    values = {}
    for role in ("owner", "api", "worker"):
        result = subprocess.run(
            [
                "aws",
                "secretsmanager",
                "get-secret-value",
                "--region",
                args.region,
                "--secret-id",
                getattr(args, f"{role}_secret_arn"),
                "--query",
                "SecretString",
                "--output",
                "text",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        if data.get("username") != f"carerank_{role}" or len(
            data.get("password", "")
        ) < (24 if role == "owner" else 32):
            raise ValueError("Unexpected database identity")
        values[role] = data
    if len({v["password"] for v in values.values()}) != 3:
        raise ValueError("Use distinct credentials")
    for role, data in values.items():
        url = (
            f"postgresql+psycopg://{data['username']}:{quote(data['password'], safe='')}"
            f"@{args.database_host}:5432/carerank?"
            + urlencode(
                {"sslmode": "verify-full", "sslrootcert": "/run/secrets/rds-ca.pem"}
            )
        )
        fd, temporary = tempfile.mkstemp(prefix=".secret-", dir=directory)
        try:
            with os.fdopen(fd, "w") as handle:
                os.fchmod(handle.fileno(), 0o400)
                os.fchown(handle.fileno(), 1000, 1000)
                handle.write(url + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary).replace(directory / f"{role}-database-url")
        finally:
            Path(temporary).unlink(missing_ok=True)
    print("Retrieved private runtime files; values were not logged")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        raise SystemExit(
            "Secret retrieval failed; check approved identity, target and file permissions"
        ) from None
