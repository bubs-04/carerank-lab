"""Pure guard tests; these do not connect to Docker or PostgreSQL."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "reliability", Path(__file__).parents[1] / "verify_reliability.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_destructive_container_guard_requires_name_ownership_and_no_mounts():
    name, token = "carerank-verification-123456abcdef", "x" * 48
    valid = {
        "Name": "/" + name,
        "Config": {"Labels": {module.LABEL: token}},
        "Mounts": [],
    }
    module.validate_disposable(name, token, valid)
    for unsafe in [
        {**valid, "Name": "/carerank-cloud-db"},
        {**valid, "Config": {"Labels": {module.LABEL: "another-invocation"}}},
        {**valid, "Mounts": [{"Type": "bind", "Source": "/retained"}]},
    ]:
        with pytest.raises(ValueError):
            module.validate_disposable(name, token, unsafe)
    with pytest.raises(ValueError):
        module.validate_disposable("carerank-cloud-db", token, valid)


@pytest.mark.parametrize(
    "url,port,database",
    [
        (
            "postgresql+psycopg://u:p@127.0.0.1:5432/carerank_test",
            5432,
            "carerank_test",
        ),
        ("postgresql+psycopg://u:p@127.0.0.1:5546/carerank", 5546, "carerank"),
        ("postgresql+psycopg://u:p@remote:5546/carerank_test", 5546, "carerank_test"),
        (
            "postgresql+psycopg://u:p@127.0.0.1:5547/carerank_test",
            5546,
            "carerank_test",
        ),
    ],
)
def test_destructive_database_guard_rejects_retained_or_mismatched_targets(
    url, port, database
):
    with pytest.raises(ValueError):
        module.validate_target(url, port, database)


def test_own_ephemeral_target_is_accepted():
    module.validate_target(
        "postgresql+psycopg://u:p@127.0.0.1:5546/carerank_restore_test",
        5546,
        "carerank_restore_test",
    )
