"""Operator-approved image deployment only; does not create infrastructure or downgrade data."""

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from check_release import manifest, secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument(
        "receipt",
        help="reviewed-release.json from the manually approved release workflow",
    )
    parser.add_argument(
        "--approved-change",
        required=True,
        help="Recorded human approval/change reference",
    )
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._/-]{3,100}", args.approved_change
    ):
        raise ValueError(
            "An approved root operator session and change reference are required"
        )
    values = manifest(args.manifest)
    receipt = json.loads(Path(args.receipt).read_text())
    for key in ("RELEASE_ID", "BACKEND_IMAGE", "WEB_IMAGE"):
        if receipt.get(key) != values[key]:
            raise ValueError(
                "Release receipt does not match the exact reviewed commit and image digests"
            )
    if not receipt.get("ci_run_url", "").startswith("https://github.com/"):
        raise ValueError("CI verification receipt is required")
    secrets(values)
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

    def run(*arguments):
        subprocess.run(command + list(arguments), check=True, env=environment)

    run("config", "--quiet")
    run("--profile", "operator", "pull")
    history = Path("/var/lib/carerank/releases")
    history.mkdir(mode=0o700, parents=True, exist_ok=True)
    previous = history / "current.env"
    if previous.exists():
        shutil.copy2(previous, history / f"previous-{time.time_ns()}.env")
    try:
        run("stop", "worker")
        run("run", "--rm", "--no-deps", "migrate")
        run("run", "--rm", "--no-deps", "provision")
        # Recreate the proxy too so Nginx resolves the replacement API container.
        run("up", "-d", "--no-deps", "--force-recreate", "api", "worker", "web")
        http = build_opener(ProxyHandler({}))
        for _ in range(30):
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
                        )
                        shutil.copyfile(args.manifest, previous)
                        previous.chmod(0o600)
                        print(
                            "Application and worker readiness verified; confirm ALB HTTPS and audit before closing change"
                        )
                        return
            except OSError:
                pass
            time.sleep(2)
        raise ValueError("Readiness did not pass")
    finally:
        # Owner credentials are never left mounted in application services.
        (Path(values["SECRET_DIR"]) / "owner-database-url").unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        raise SystemExit(
            "Deployment did not complete. Preserve logs, inspect worker state and use the reviewed rollback runbook; no database downgrade was attempted"
        ) from None
