"""Validate a non-secret production release manifest; never print credential contents."""

import argparse
import hashlib
import ipaddress
import re
import ssl
import stat
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

IMAGE = re.compile(
    r"[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/[a-z0-9._/-]+@sha256:[a-f0-9]{64}"
)
KEYS = {
    "BACKEND_IMAGE",
    "WEB_IMAGE",
    "PUBLIC_ORIGIN",
    "WEB_BIND_ADDRESS",
    "AWS_REGION",
    "AWS_LOG_GROUP",
    "RELEASE_ID",
    "WORKER_INSTANCE_ID",
    "SECRET_DIR",
    "RDS_CA_FILE",
    "RDS_CA_SHA256",
}


def manifest(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if (
            not separator
            or key not in KEYS
            or key in values
            or re.search(r"[\s$`'\"\\;]", value)
        ):
            raise ValueError(
                "Release manifest has an unknown, duplicate or nonliteral setting"
            )
        values[key] = value
    if set(values) != KEYS:
        raise ValueError("Release manifest is incomplete")
    for key in ("BACKEND_IMAGE", "WEB_IMAGE"):
        if not IMAGE.fullmatch(values[key]):
            raise ValueError(
                "Both images must use a private ECR URI with an immutable sha256 digest"
            )
    if not re.fullmatch(r"[a-f0-9]{40}", values["RELEASE_ID"]):
        raise ValueError("RELEASE_ID must identify the reviewed Git commit")
    origin = urlsplit(values["PUBLIC_ORIGIN"])
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.port not in (None, 443)
        or origin.path
        or origin.query
        or origin.fragment
    ):
        raise ValueError("PUBLIC_ORIGIN must be one exact HTTPS origin")
    if not re.fullmatch(r"[a-z0-9-]+", values["AWS_REGION"]):
        raise ValueError("Invalid AWS region")
    address = ipaddress.ip_address(values["WEB_BIND_ADDRESS"])
    if address.version != 4 or address not in ipaddress.ip_network("10.64.0.0/24"):
        raise ValueError(
            "Bind only the application host private IPv4 from the reference subnet"
        )
    for key in ("SECRET_DIR", "RDS_CA_FILE"):
        if not values[key].startswith("/") or not re.fullmatch(
            r"/[A-Za-z0-9_./-]+", values[key]
        ):
            raise ValueError("Secret and CA locations must be absolute local paths")
    if not re.fullmatch(r"[a-f0-9]{64}", values["RDS_CA_SHA256"]):
        raise ValueError("Record the approved RDS CA bundle checksum")
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", values["AWS_LOG_GROUP"]):
        raise ValueError("Invalid log group")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", values["WORKER_INSTANCE_ID"]):
        raise ValueError("Invalid worker instance identifier")
    return values


def secrets(values):
    directory = Path(values["SECRET_DIR"])
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError(
            "Secret directory must be a real root-owned directory with mode 0700"
        )
    connections = []
    for role in ("owner", "api", "worker"):
        path = directory / f"{role}-database-url"
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 1000
            or stat.S_IMODE(info.st_mode) != 0o400
        ):
            raise ValueError(
                "Secret files must be regular files owned by UID 1000 with mode 0400"
            )
        value = path.read_text().strip()
        url = urlsplit(value)
        query = parse_qs(url.query)
        if (
            url.scheme != "postgresql+psycopg"
            or url.username != f"carerank_{role}"
            or not url.password
            or len(url.password) < (24 if role == "owner" else 32)
            or url.port != 5432
            or url.path != "/carerank"
            or not url.hostname
            or not url.hostname.endswith(
                (".rds.amazonaws.com", ".rds.amazonaws.com.cn")
            )
            or query
            != {"sslmode": ["verify-full"], "sslrootcert": ["/run/secrets/rds-ca.pem"]}
        ):
            raise ValueError(
                "Database secrets require distinct roles, the private RDS target and verify-full TLS"
            )
        connections.append(url)
    if (
        len({u.password for u in connections}) != 3
        or len({u.hostname for u in connections}) != 1
    ):
        raise ValueError(
            "Database secrets must target one host with three different credentials"
        )
    ca = Path(values["RDS_CA_FILE"])
    if hashlib.sha256(ca.read_bytes()).hexdigest() != values["RDS_CA_SHA256"]:
        raise ValueError("RDS CA bundle does not match the approved checksum")
    ssl.create_default_context(cafile=str(ca))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument(
        "--static",
        action="store_true",
        help="Validate manifest without opening runtime secrets",
    )
    args = parser.parse_args()
    values = manifest(args.manifest)
    if not args.static:
        secrets(values)
    print("Production release configuration validated; no credentials displayed")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, ssl.SSLError):
        raise SystemExit(
            "Production release validation failed; check manifest, file permissions and TLS configuration"
        ) from None
