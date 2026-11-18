"""Reproducible local demo with explicit project/volume reset guards; never uses .env."""

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".demo"
PROJECT = "carerank-demo-v6"
VOLUME = "carerank-demo-v6-pgdata"
ENV_KEYS = ("DEMO_OWNER_PASSWORD", "DEMO_API_PASSWORD", "DEMO_WORKER_PASSWORD")


def private_write(path, content):
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as file:
        file.write(content)


def configure():
    STATE.mkdir(mode=0o700, exist_ok=True)
    STATE.chmod(0o700)
    env = STATE / "compose.env"
    if not env.exists():
        # Refuse silently rotating an existing database's password.
        exists = (
            subprocess.run(
                ["docker", "volume", "inspect", VOLUME],
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
        if exists:
            raise ValueError(
                "Existing demo volume has no matching private configuration; restore .demo"
            )
        private_write(
            env,
            "".join(f"{key}={secrets.token_hex(32)}\n" for key in ENV_KEYS)
            + f"DEMO_UID={os.getuid()}\nDEMO_GID={os.getgid()}\n",
        )
    accounts = STATE / "accounts.json"
    if not accounts.exists():
        private_write(
            accounts,
            json.dumps(
                [
                    {
                        "username": "demo-" + role,
                        "display_name": "Demo " + role.title(),
                        "role": role,
                        "password": secrets.token_urlsafe(32),
                    }
                    for role in ("administrator", "analyst", "viewer")
                ],
                indent=2,
            )
            + "\n",
        )
    env.chmod(0o600)
    accounts.chmod(0o600)


def compose(*args):
    # Ignore caller COMPOSE_FILE/PROJECT/production variables; only fixed demo config.
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "DEMO_"))
    }
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(STATE / "compose.env"),
            "--project-name",
            PROJECT,
            "-f",
            str(ROOT / "compose.demo.yaml"),
            *args,
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )


def validate_reset_volume(data):
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError("Expected exactly one dedicated demo volume")
    volume = data[0]
    labels = volume.get("Labels") or {}
    if (
        volume.get("Name") != VOLUME
        or labels.get("com.docker.compose.project") != PROJECT
        or labels.get("carerank.demo") != "v6"
    ):
        raise ValueError("Refusing reset: volume is not the dedicated CareRank v6 demo")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "status", "reset"])
    parser.add_argument("--confirm-reset", choices=[PROJECT])
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Start from existing images without build network access",
    )
    args = parser.parse_args()
    if args.command == "reset":
        if args.confirm_reset != PROJECT:
            parser.error(
                "Reset requires --confirm-reset carerank-demo-v6; it deletes only demo history"
            )
        if not (STATE / "compose.env").is_file():
            parser.error("Matching private demo configuration is required")
        data = json.loads(
            subprocess.check_output(["docker", "volume", "inspect", VOLUME])
        )
        validate_reset_volume(data)
        compose("down")
        subprocess.run(["docker", "volume", "rm", VOLUME], check=True)
        print(
            "Dedicated demo volume removed; private accounts/configuration retained. Run start to reseed."
        )
    elif args.command == "start":
        configure()
        compose("config", "--quiet")
        compose(
            "up",
            "--no-build" if args.no_build else "--build",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
        )
        print(
            "Demo: http://127.0.0.1:8086 — credentials are in .demo/accounts.json (keep private)"
        )
        if not (ROOT / "demo/cms-archive.json").exists():
            print(
                "CMS ARCHIVE MISSING: only explicitly labeled artificial fixtures are available."
            )
    elif args.command == "stop":
        compose("down")
    else:
        compose("ps", "-a")


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(
            f"Demo command failed ({type(exc).__name__}); no secret values are logged."
        ) from None
