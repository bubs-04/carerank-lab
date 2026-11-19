"""No cloud calls: enforce release digest, TLS and isolated-demo reset boundaries."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load("release", "infra/check_release.py")
demo = load("demo_launcher", "scripts/demo.py")


def valid_manifest():
    return (
        (ROOT / "infra/release.env.example")
        .read_text()
        .replace("REPLACE_WITH_64_HEX_DIGEST", "a" * 64)
        .replace("REPLACE_WITH_GIT_COMMIT_SHA", "b" * 40)
        .replace("REPLACE_WITH_APPROVED_64_HEX_CHECKSUM", "c" * 64)
        .replace("REPLACE_WITH_STACK_NAME", "test")
    )


@pytest.mark.parametrize(
    "old,new",
    [
        ("https://carerank.example.org", "http://carerank.example.org"),
        ("@sha256:" + "a" * 64, ":latest"),
        ("WEB_BIND_ADDRESS=10.64.0.10", "WEB_BIND_ADDRESS=0.0.0.0"),
        ("WORKER_INSTANCE_ID=production-worker-1", "WORKER_INSTANCE_ID=$(id)"),
    ],
)
def test_release_rejects_unsafe_manifest(tmp_path, old, new):
    path = tmp_path / "release.env"
    path.write_text(valid_manifest().replace(old, new))
    with pytest.raises(ValueError):
        release.manifest(path)


def test_exact_release_and_demo_volume_identity(tmp_path):
    path = tmp_path / "release.env"
    path.write_text(valid_manifest())
    assert release.manifest(path)["RELEASE_ID"] == "b" * 40
    data = [
        {
            "Name": demo.VOLUME,
            "Labels": {
                "com.docker.compose.project": demo.PROJECT,
                "carerank.demo": "v6",
            },
        }
    ]
    demo.validate_reset_volume(data)
    data[0]["Name"] = "carerank_pgdata"
    with pytest.raises(ValueError):
        demo.validate_reset_volume(data)


# All Docker, HTTP and deployment subprocess calls below are mocked.
import io
import json
import os
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {"check_release": release}):
    deploy = load("deploy_helper", "infra/deploy.py")


def mock_socket(monkeypatch, tmp_path, relative=".docker/run/docker.sock"):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("mock socket; no Docker daemon")
    original_stat = Path.stat

    def socket_stat(candidate, *args, **kwargs):
        if candidate == path:
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.getuid())
        return original_stat(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", socket_stat)
    return f"unix://{path}"


def mock_docker(monkeypatch, host, names="", valid_labels=True):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert not any(
            key != "DOCKER_CONFIG" and key.startswith(("DOCKER_", "COMPOSE_", "DEMO_"))
            for key in kwargs["env"]
        )
        if command[1:] == ["context", "show"]:
            output = "selected-context\n"
        elif command[1:3] == ["context", "inspect"]:
            output = json.dumps([{"Endpoints": {"docker": {"Host": host}}}])
        elif command[3:5] == ["volume", "ls"]:
            output = names
        elif command[3:5] == ["volume", "inspect"]:
            output = json.dumps(
                [
                    {
                        "Name": demo.VOLUME,
                        "Labels": {
                            "com.docker.compose.project": demo.PROJECT,
                            "carerank.demo": "v6" if valid_labels else "unrelated",
                        },
                    }
                ]
            )
        else:
            output = ""
        return SimpleNamespace(stdout=output, returncode=0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    return calls


@pytest.mark.parametrize("selected_by_env", [False, True])
@pytest.mark.parametrize(
    "host", ["tcp://remote:2375", "ssh://remote", "unix:///tmp/forwarded-docker.sock"]
)
def test_demo_rejects_remote_or_unapproved_context_before_daemon_calls(
    monkeypatch, selected_by_env, host
):
    calls = mock_docker(monkeypatch, host)
    if selected_by_env:
        monkeypatch.setenv("DOCKER_CONTEXT", "remote")
    with pytest.raises(ValueError, match="local"):
        demo.LocalDocker()
    assert all(command[1] == "context" for command, _ in calls)


@pytest.mark.parametrize("host", ["tcp://remote:2375", "unix:///var/run/docker.sock"])
def test_demo_rejects_docker_host_override_before_any_cli_call(monkeypatch, host):
    run = Mock(side_effect=AssertionError("Docker must not be invoked"))
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("DOCKER_HOST", host)
    with pytest.raises(ValueError, match="Unset DOCKER_HOST"):
        demo.LocalDocker()
    run.assert_not_called()


def test_custom_docker_config_is_used_to_detect_its_remote_context(monkeypatch):
    calls = mock_docker(monkeypatch, "ssh://remote-selected-by-config")
    monkeypatch.setenv("DOCKER_CONFIG", "/private/custom-docker-config")
    with pytest.raises(ValueError, match="local"):
        demo.LocalDocker()
    assert calls and all(command[1] == "context" for command, _ in calls)
    assert all(
        options["env"]["DOCKER_CONFIG"] == "/private/custom-docker-config"
        for _, options in calls
    )


@pytest.mark.parametrize(
    "relative",
    [
        ".docker/run/docker.sock",
        ".docker/desktop/docker.sock",
        "Library/Containers/com.docker.docker/Data/docker.sock",
    ],
)
def test_approved_docker_desktop_socket_paths(monkeypatch, tmp_path, relative):
    endpoint = mock_socket(monkeypatch, tmp_path, relative)
    assert demo.approved_endpoint(endpoint) == endpoint


def test_demo_rejects_non_socket_and_socket_symlink_outside_allowed_paths(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    path = tmp_path / ".docker/run/docker.sock"
    path.parent.mkdir(parents=True)
    path.write_text("not a socket")
    with pytest.raises(ValueError, match="Unix socket"):
        demo.approved_endpoint(f"unix://{path}")
    path.unlink()
    target = tmp_path / "unapproved.sock"
    target.write_text("not an approved socket")
    path.symlink_to(target)
    with pytest.raises(ValueError, match="Unix socket"):
        demo.approved_endpoint(f"unix://{path}")
    assert target.read_text() == "not an approved socket"


@pytest.mark.parametrize("valid_labels", [True, False])
def test_reset_pins_every_daemon_command_and_preserves_labels(
    monkeypatch, tmp_path, valid_labels
):
    endpoint = mock_socket(monkeypatch, tmp_path)
    calls = mock_docker(monkeypatch, endpoint, valid_labels=valid_labels)
    for key in (
        "DOCKER_TLS_VERIFY",
        "DOCKER_CONFIG",
        "COMPOSE_FILE",
        "DEMO_OWNER_PASSWORD",
    ):
        monkeypatch.setenv(key, "inherited-untrusted-value")
    state = tmp_path / ".demo"
    state.mkdir()
    (state / "compose.env").write_text("matching configuration")
    monkeypatch.setattr(demo, "STATE", state)
    monkeypatch.setattr(
        sys, "argv", ["demo.py", "reset", "--confirm-reset", demo.PROJECT]
    )
    if valid_labels:
        demo.main()
    else:
        with pytest.raises(ValueError, match="dedicated"):
            demo.main()
    daemon_calls = [command for command, _ in calls if command[1] != "context"]
    assert all(
        command[:3] == ["docker", "--host", endpoint] for command in daemon_calls
    )
    assert any(command[3:5] == ["volume", "inspect"] for command in daemon_calls)
    assert (
        any(command[3:5] == ["volume", "rm"] for command in daemon_calls)
        == valid_labels
    )
    assert any(command[3] == "compose" for command in daemon_calls) == valid_labels
    assert (state / "compose.env").read_text() == "matching configuration"


def test_reset_requires_explicit_confirmation(monkeypatch):
    docker = Mock()
    monkeypatch.setattr(demo, "LocalDocker", lambda: docker)
    monkeypatch.setattr(sys, "argv", ["demo.py", "reset"])
    with pytest.raises(SystemExit):
        demo.main()
    docker.run.assert_not_called()


@pytest.mark.parametrize("missing", ["accounts.json", "compose.env"])
def test_existing_demo_volume_never_regenerates_missing_credentials(
    monkeypatch, tmp_path, missing
):
    monkeypatch.setattr(demo, "STATE", tmp_path)
    kept = "compose.env" if missing == "accounts.json" else "accounts.json"
    (tmp_path / kept).write_text("existing private credentials")
    docker = SimpleNamespace(volume_exists=lambda: True)
    with pytest.raises(ValueError, match="restore the matching private files"):
        demo.configure(docker)
    assert not (tmp_path / missing).exists()
    assert (tmp_path / kept).read_text() == "existing private credentials"


def test_new_demo_credentials_are_private_and_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "STATE", tmp_path)
    demo.configure(SimpleNamespace(volume_exists=lambda: False))
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    demo.configure(SimpleNamespace(volume_exists=lambda: True))
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in tmp_path.iterdir()
    )
    assert len(json.loads((tmp_path / "accounts.json").read_text())) == 3


def test_volume_lookup_failure_does_not_generate_credentials(monkeypatch, tmp_path):
    endpoint = mock_socket(monkeypatch, tmp_path)
    mock_docker(monkeypatch, endpoint)
    docker = demo.LocalDocker()
    docker.run = Mock(side_effect=subprocess.CalledProcessError(1, "mock docker"))
    state = tmp_path / ".demo"
    monkeypatch.setattr(demo, "STATE", state)
    with pytest.raises(subprocess.CalledProcessError):
        demo.configure(docker)
    assert not (state / "compose.env").exists()
    assert not (state / "accounts.json").exists()


@pytest.fixture
def deployment(monkeypatch, tmp_path):
    directory = tmp_path / "secrets"
    directory.mkdir(mode=0o700)
    owner = directory / "owner-database-url"
    owner.write_text("private owner URL sentinel")
    api = directory / "api-database-url"
    api.write_text("preserved runtime URL sentinel")
    path = tmp_path / "release.env"
    path.write_text(valid_manifest().replace("/run/carerank-secrets", str(directory)))
    values = release.manifest(path)
    metadata = tmp_path / "receipt.json"
    metadata.write_text(
        json.dumps(
            {key: values[key] for key in ("RELEASE_ID", "BACKEND_IMAGE", "WEB_IMAGE")}
        )
    )
    history = tmp_path / "history"
    monkeypatch.setattr(deploy, "HISTORY", history)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    original_fstat = os.fstat

    def root_directory(descriptor):
        info = original_fstat(descriptor)
        if stat.S_ISDIR(info.st_mode):
            fields = list(info)
            fields[4] = 0
            return os.stat_result(fields)
        return info

    monkeypatch.setattr(os, "fstat", root_directory)
    monkeypatch.setattr(deploy, "secrets", Mock())
    monkeypatch.setattr(deploy, "wait_ready", Mock())
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["deploy.py", str(path), str(metadata), "--approved-change", "CHANGE-123"],
    )
    return SimpleNamespace(
        values=values,
        owner=owner,
        api=api,
        path=path,
        metadata=metadata,
        history=history,
        run=run,
    )


@pytest.mark.parametrize(
    "phase",
    [
        "approval",
        "approval_missing",
        "manifest",
        "receipt_json",
        "receipt_missing",
        "receipt_mismatch",
        "secrets",
        "history",
        "config",
        "pull",
        "previous_manifest",
        "stop",
        "migrate",
        "provision",
        "up",
        "readiness",
        "save_manifest",
    ],
)
def test_every_deployment_failure_after_safe_directory_validation_cleans_owner(
    deployment, monkeypatch, phase
):
    if phase == "approval":
        monkeypatch.setattr(os, "geteuid", lambda: 1000)
    elif phase == "approval_missing":
        monkeypatch.setattr(
            sys, "argv", ["deploy.py", str(deployment.path), str(deployment.metadata)]
        )
    elif phase == "manifest":
        deployment.path.write_text(
            deployment.path.read_text().replace("@sha256:" + "a" * 64, ":latest")
        )
    elif phase == "receipt_json":
        deployment.metadata.write_text("{invalid json")
    elif phase == "receipt_missing":
        deployment.metadata.unlink()
    elif phase == "receipt_mismatch":
        deployment.metadata.write_text("{}")
    elif phase in ("secrets", "history", "readiness"):
        function = {
            "secrets": "secrets",
            "history": "record_operator_approval",
            "readiness": "wait_ready",
        }[phase]
        monkeypatch.setattr(
            deploy, function, Mock(side_effect=ValueError("mock failure"))
        )
    elif phase == "previous_manifest":
        deployment.history.mkdir()
        (deployment.history / "current.env").write_text("previous approved release")
        monkeypatch.setattr(
            deploy.shutil, "copy2", Mock(side_effect=OSError("mock failure"))
        )
    elif phase == "save_manifest":
        monkeypatch.setattr(
            deploy.shutil, "copyfile", Mock(side_effect=OSError("mock failure"))
        )
    else:

        def fail_phase(command, **kwargs):
            if phase in command:
                raise subprocess.CalledProcessError(1, "mock docker")

        deployment.run.side_effect = fail_phase
    with pytest.raises((ValueError, OSError, subprocess.SubprocessError)):
        deploy.main()
    assert not deployment.owner.exists()
    assert deployment.api.read_text() == "preserved runtime URL sentinel"


def test_release_receipt_is_advisory_and_operator_approval_is_recorded(
    deployment, capsys
):
    deploy.main()
    records = list(deployment.history.glob("operator-approval-*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["local_receipt_is_authoritative"] is False
    assert record["approved_change"] == "CHANGE-123"
    assert record["RELEASE_ID"] == deployment.values["RELEASE_ID"]
    assert stat.S_IMODE(records[0].stat().st_mode) == 0o600
    assert "not a GitHub approval gate" in capsys.readouterr().out
    assert not deployment.owner.exists()


def test_symlink_secret_directory_never_deletes_target(deployment, tmp_path):
    alias = tmp_path / "secret-alias"
    alias.symlink_to(deployment.owner.parent, target_is_directory=True)
    deployment.path.write_text(
        deployment.path.read_text().replace(str(deployment.owner.parent), str(alias))
    )
    deployment.metadata.unlink()
    with pytest.raises(ValueError, match="symlinks"):
        deploy.main()
    assert deployment.owner.read_text() == "private owner URL sentinel"
    deployment.run.assert_not_called()


def test_cleanup_keeps_validated_directory_identity(deployment):
    original = deployment.owner.parent
    replacement = original.with_name("moved-secrets")
    with (
        pytest.raises(ValueError, match="synthetic early failure"),
        deploy.owner_cleanup(deployment.values),
    ):
        original.rename(replacement)
        original.mkdir(mode=0o700)
        (original / "owner-database-url").write_text("unrelated replacement")
        raise ValueError("synthetic early failure")
    assert not (replacement / "owner-database-url").exists()
    assert (original / "owner-database-url").read_text() == "unrelated replacement"


@pytest.mark.parametrize("failure", ["claim", "timeout", "http", "json"])
def test_readiness_retries_transient_startup_failures(monkeypatch, failure):
    calls = 0

    def open_response(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1 and failure == "http":
            raise OSError("starting API")
        if calls == 1 and failure == "json":
            return io.StringIO("starting")
        return io.StringIO('{"status": "ok"}')

    http = SimpleNamespace(open=open_response)
    monkeypatch.setattr(deploy, "build_opener", lambda *args: http)
    sleep = Mock()
    monkeypatch.setattr(deploy.time, "sleep", sleep)
    run = Mock()
    if failure in ("claim", "timeout"):
        error = (
            subprocess.CalledProcessError(1, "mock health")
            if failure == "claim"
            else subprocess.TimeoutExpired("mock health", 5)
        )
        run.side_effect = [error, None]
    deploy.wait_ready({"WEB_BIND_ADDRESS": "10.64.0.10"}, run)
    assert calls == 2
    sleep.assert_called_once_with(2)
    assert all(call.kwargs == {"timeout": 5} for call in run.call_args_list)


def test_worker_readiness_exhaustion_is_bounded(monkeypatch):
    http = SimpleNamespace(open=lambda *args, **kwargs: io.StringIO('{"status": "ok"}'))
    monkeypatch.setattr(deploy, "build_opener", lambda *args: http)
    sleep = Mock()
    monkeypatch.setattr(deploy.time, "sleep", sleep)
    run = Mock(side_effect=subprocess.CalledProcessError(1, "mock health"))
    with pytest.raises(ValueError, match="30 attempts"):
        deploy.wait_ready({"WEB_BIND_ADDRESS": "10.64.0.10"}, run)
    assert run.call_count == 30
    assert sleep.call_count == 29
