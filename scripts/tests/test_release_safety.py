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
