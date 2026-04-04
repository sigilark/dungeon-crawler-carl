"""Global test configuration."""

import pytest


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """Disable slowapi rate limiting during tests."""
    from server import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True
