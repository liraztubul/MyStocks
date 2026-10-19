import os

# Must run before any app import: Settings requires a JWT secret and is built at import time.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters")
# Tests never use real provider keys, even if the developer's .env (read by Settings) has them:
# no test may reach a real provider.
os.environ["COINGECKO_DEMO_API_KEY"] = ""
os.environ["TIINGO_API_KEY"] = ""

import httpx2  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside the opt-in live tests, any real HTTP request fails the test, whatever .env holds."""
    if request.node.get_closest_marker("live_network"):
        return

    def refuse(_transport: httpx2.HTTPTransport, req: httpx2.Request) -> httpx2.Response:
        raise AssertionError(f"tests must not reach the network (tried {req.url.host})")

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", refuse)
