"""Reproducible local demo with explicit project/volume reset guards; never uses .env."""

import argparse
import json
import os
import secrets
import stat
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


def docker_environment():
    # No inherited daemon, context, TLS or Compose interpolation overrides.
    return {
        key: value
        for key, value in os.environ.items()
        if key == "DOCKER_CONFIG"
        or not key.startswith(("DOCKER_", "COMPOSE_", "DEMO_"))
    }


def approved_endpoint(host):
    home = Path.home()
    allowed = {
        Path("/var/run/docker.sock"),
        Path("/run/docker.sock"),
        Path("/run/codex-docker/docker.sock"),
        home / ".docker/run/docker.sock",
        home / ".docker/desktop/docker.sock",
        home / "Library/Containers/com.docker.docker/Data/docker.sock",
        Path(f"/run/user/{os.getuid()}/docker.sock"),
    }
    if not isinstance(host, str) or not host.startswith("unix:///"):
        raise ValueError("Demo commands require an approved local Unix Docker socket")
    path = Path(host[len("unix://") :])
    if path not in allowed:
        raise ValueError("Docker context does not use an approved local demo socket")
    resolved = path.resolve(strict=True)
    # Allow the normal /var/run and Docker Desktop symlinks, not arbitrary sockets.
    targets = {candidate.parent.resolve() / candidate.name for candidate in allowed}
    info = resolved.stat()
    permitted_owners = {0, os.getuid()}
    if resolved == Path("/run/codex-docker/docker.sock"):
        permitted_owners.add(65534)  # Managed cloud socket's namespace-mapped owner.
    if (
        resolved not in targets
        or not stat.S_ISSOCK(info.st_mode)
        or info.st_uid not in permitted_owners
    ):
        raise ValueError(
            "Docker endpoint must be an approved locally owned Unix socket"
        )
    return f"unix://{resolved}"


class LocalDocker:
    def __init__(self):
        if os.environ.get("DOCKER_HOST"):
            raise ValueError(
                "Unset DOCKER_HOST and select a local Docker context before demo commands"
            )
        self.environment = docker_environment()
        context = os.environ.get("DOCKER_CONTEXT")
        if not context:
            context = subprocess.run(
                ["docker", "context", "show"],
                check=True,
                capture_output=True,
                text=True,
                env=self.environment,
            ).stdout.strip()
        if not context or context.startswith("-") or any(c.isspace() for c in context):
            raise ValueError("Invalid Docker context")
        data = json.loads(
            subprocess.run(
                ["docker", "context", "inspect", context],
                check=True,
                capture_output=True,
                text=True,
                env=self.environment,
            ).stdout
        )
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError("Expected exactly one Docker context")
        host = data[0].get("Endpoints", {}).get("docker", {}).get("Host")
        self.endpoint = approved_endpoint(host)
        self.run("info", capture_output=True)

    def run(self, *args, **kwargs):
        return subprocess.run(
            ["docker", "--host", self.endpoint, *args],
            env=self.environment,
            check=True,
            **kwargs,
        )

    def volume_exists(self):
        # A daemon/permission failure must not be mistaken for an absent volume.
        names = self.run(
            "volume",
            "ls",
            "--filter",
            f"name={VOLUME}",
            "--format",
            "{{.Name}}",
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        return VOLUME in names


def configure(docker):
    STATE.mkdir(mode=0o700, exist_ok=True)
    STATE.chmod(0o700)
    env = STATE / "compose.env"
    accounts = STATE / "accounts.json"
    exists = docker.volume_exists()
    if exists and (not env.is_file() or not accounts.is_file()):
        raise ValueError(
            "Existing demo volume requires its original .demo/compose.env and "
            ".demo/accounts.json; restore the matching private files from backup. "
            "No replacement credentials were generated and existing data was preserved."
        )
    if not env.exists():
        private_write(
            env,
            "".join(f"{key}={secrets.token_hex(32)}\n" for key in ENV_KEYS)
            + f"DEMO_UID={os.getuid()}\nDEMO_GID={os.getgid()}\n",
        )
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


def compose(docker, *args):
    return docker.run(
        "compose",
        "--env-file",
        str(STATE / "compose.env"),
        "--project-name",
        PROJECT,
        "-f",
        str(ROOT / "compose.demo.yaml"),
        *args,
        cwd=ROOT,
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
    docker = LocalDocker()
    if args.command == "reset":
        if args.confirm_reset != PROJECT:
            parser.error(
                "Reset requires --confirm-reset carerank-demo-v6; it deletes only demo history"
            )
        if not (STATE / "compose.env").is_file():
            parser.error("Matching private demo configuration is required")
        data = json.loads(
            docker.run(
                "volume", "inspect", VOLUME, capture_output=True, text=True
            ).stdout
        )
        validate_reset_volume(data)
        compose(docker, "down")
        docker.run("volume", "rm", VOLUME)
        print(
            "Dedicated demo volume removed; private accounts/configuration retained. Run start to reseed."
        )
    elif args.command == "start":
        configure(docker)
        compose(docker, "config", "--quiet")
        compose(
            docker,
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
        compose(docker, "down")
    else:
        compose(docker, "ps", "-a")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except (
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(
            f"Demo command failed ({type(exc).__name__}); no secret values are logged."
        ) from None
