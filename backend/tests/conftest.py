"""Explicit authenticated identities for existing read-only domain/API tests.

Real cookie, CSRF and authorization boundaries are tested without these overrides
in test_security.py. This fixture is intentionally not autouse.
"""

from types import SimpleNamespace
import pytest
from app.main import app


@pytest.fixture
def authenticated_reader():
    from app.auth.dependencies import require_user

    user = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        username="domain-test-viewer",
        display_name="Domain test viewer",
        role="viewer",
        active=True,
    )
    identity = SimpleNamespace(user=user, session=SimpleNamespace(csrf_token="test-only-csrf"))
    app.dependency_overrides[require_user] = lambda: identity
    yield user
    app.dependency_overrides.pop(require_user, None)
