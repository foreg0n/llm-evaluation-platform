import os

import pytest

# Tests must never export telemetry, even when a developer enables tracing in .env.
os.environ["TRACING_ENABLED"] = "false"
os.environ["SENTRY_ENABLED"] = "false"
os.environ["REQUIRE_EMAIL_VERIFICATION"] = "false"
os.environ["EMAIL_BACKEND"] = "console"

from backend.services.auth_rate_limit import get_auth_rate_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_auth_rate_limiter():
    get_auth_rate_limiter.cache_clear()
    yield
    get_auth_rate_limiter.cache_clear()
