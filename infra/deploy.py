"""Deploy by recorded operator approval; local release metadata is not GitHub approval."""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from check_release import manifest, secrets

HISTORY = Path("/var/lib/carerank/releases")


def cleanup_location(path):
    # Find only a literal, unambiguous location before validating the rest of the
    # release. An invalid image/receipt/approval must still remove the owner URL.
    locations = [
        line.partition("=")[2]
        for line in Path(path).read_text().splitlines()
        if line.startswith("SECRET_DIR=")
    ]
    if len(locations) != 1 or not re.fullmatch(r"/[A-Za-z0-9_./-]+", locations[0]):
        raise ValueError("Cannot safely identify the owner-secret cleanup directory")
    return {"SECRET_DIR": locations[0]}


@contextmanager
def owner_cleanup(values):
    directory = Path(values["SECRET_DIR"])
    if directory.resolve(strict=True) != directory:
        raise ValueError("Secret directory must not use symlinks or traversal")
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Secret directory must be root-owned with mode 0700")
        try:
            yield
        finally:
            # Hold directory identity through every failure, including failed preflight.
            try:
                os.unlink("owner-database-url", dir_fd=descriptor)
            except FileNotFoundError:
                pass
    finally:
        os.close(descriptor)


def release_metadata(path, values):
    """Check consistency only: a local JSON file has no trusted CI provenance."""
    receipt = json.loads(Path(path).read_text())
    if not isinstance(receipt, dict) or any(
        receipt.get(key) != values[key]
        for key in ("RELEASE_ID", "BACKEND_IMAGE", "WEB_IMAGE")
    ):
        raise ValueError("Unverified release metadata does not match the manifest")
    return receipt


def record_operator_approval(values, change):
    HISTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
    record = {
        "approved_change": change,
        "operator_uid": os.geteuid(),
        "recorded_at_unix": time.time(),
        "authorization_basis": "operator approval; independently verify the change record",
        "local_receipt_is_authoritative": False,
        **{key: values[key] for key in ("RELEASE_ID", "BACKEND_IMAGE", "WEB_IMAGE")},
    }
    path = HISTORY / f"operator-approval-{time.time_ns()}.json"
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as file:
        json.dump(record, file, indent=2)
        file.write("\n")


def wait_ready(values, run):
    http = build_opener(ProxyHandler({}))
    for attempt in range(30):
        try:
            with http.open(
                f"http://{values['WEB_BIND_ADDRESS']}:8080/api/ready", timeout=3
            ) as response:
                if json.load(response) == {"status": "ok"}:
                    run(
                        "exec",
                        "-T",
                        "worker",
                        "python",
                        "-m",
                        "app.operations",
                        "health",
                        timeout=5,
                    )
                    return
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            # A starting/recovering worker can fail its first health checks.
            pass
        if attempt < 29:
            time.sleep(2)
    raise ValueError("Application and worker readiness did not pass within 30 attempts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument(
        "receipt",
        help="Unverified release metadata JSON; never proof of GitHub or human approval",
    )
    parser.add_argument(
        "--approved-change",
        help="Independently approved operator change reference, recorded before deployment",
    )
    args = parser.parse_args()
    # A verified directory descriptor binds cleanup even if other manifest fields
    # or the operator approval are missing/invalid. An unknown location fails closed.
    with owner_cleanup(cleanup_location(args.manifest)):
        values = manifest(args.manifest)
        if (
            os.geteuid() != 0
            or not args.approved_change
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._/-]{3,100}", args.approved_change
            )
        ):
            raise ValueError(
                "An approved root operator session and change reference are required"
            )
        release_metadata(args.receipt, values)
        secrets(values)
        record_operator_approval(values, args.approved_change)
        print(
            "Local release metadata is unverified and is not a GitHub approval gate; "
            "deployment relies on the recorded operator approval"
        )
        base = Path(__file__).resolve().parent
        command = [
            "docker",
            "compose",
            "--env-file",
            str(Path(args.manifest).resolve()),
            "-f",
            str(base / "compose.production.yaml"),
        ]
        # Shell/Compose interpolation must not override the validated manifest.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in values and not key.startswith(("COMPOSE_", "DOCKER_"))
        }

        def run(*arguments, **kwargs):
            subprocess.run(
                command + list(arguments), check=True, env=environment, **kwargs
            )

        run("config", "--quiet")
        run("--profile", "operator", "pull")
        previous = HISTORY / "current.env"
        if previous.exists():
            shutil.copy2(previous, HISTORY / f"previous-{time.time_ns()}.env")
        run("stop", "worker")
        run("run", "--rm", "--no-deps", "migrate")
        run("run", "--rm", "--no-deps", "provision")
        # Recreate the proxy too so Nginx resolves the replacement API container.
        run("up", "-d", "--no-deps", "--force-recreate", "api", "worker", "web")
        wait_ready(values, run)
        shutil.copyfile(args.manifest, previous)
        previous.chmod(0o600)
        print(
            "Application and worker readiness verified; confirm ALB HTTPS and audit before closing change"
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        raise SystemExit(
            "Deployment did not complete. Preserve logs, inspect worker state and use the reviewed rollback runbook; no database downgrade was attempted"
        ) from None
