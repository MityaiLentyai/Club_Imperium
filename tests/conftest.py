import httpx
import pytest


@pytest.fixture(autouse=True)
def block_external_http(monkeypatch):
    """Tests must explicitly mock any outbound geocoding call."""
    async def blocked(*args, **kwargs):
        raise AssertionError("External HTTP is forbidden in tests")

    monkeypatch.setattr(httpx.AsyncClient, "get", blocked)

    def blocked_sync(*args, **kwargs):
        raise AssertionError("External HTTP is forbidden in tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked_sync)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
