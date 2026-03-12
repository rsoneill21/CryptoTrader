import pytest

from services.kraken import KrakenService


@pytest.mark.asyncio
async def test_request_acquires_limiter_before_http_call(monkeypatch):
    service = KrakenService()
    events = []

    async def fake_acquire(weight, timeout_seconds=10.0):
        events.append(("acquire", weight))

    async def no_sleep_rate_limit():
        events.append(("legacy_rate_limit", None))

    def fake_query_public(method, payload):
        events.append(("request", method, payload))
        return {"error": [], "result": {"ok": True}}

    monkeypatch.setattr("services.kraken.KrakenRateLimiter.acquire", fake_acquire)
    monkeypatch.setattr(service, "_rate_limit", no_sleep_rate_limit)
    monkeypatch.setattr(service._api, "query_public", fake_query_public)

    result = await service._request_once("Ticker", {"pair": "XXBTZUSD"}, private=False)

    assert result == {"ok": True}
    assert events[0][0] == "acquire"
    assert events[1][0] == "legacy_rate_limit"
    assert events[2][0] == "request"


@pytest.mark.asyncio
async def test_request_assigns_endpoint_weights(monkeypatch):
    service = KrakenService()
    captured_weights = []

    async def fake_acquire(weight, timeout_seconds=10.0):
        captured_weights.append(weight)

    async def no_sleep_rate_limit():
        return None

    def fake_query_private(method, payload):
        return {"error": [], "result": {"ok": method}}

    def fake_query_public(method, payload):
        return {"error": [], "result": {"ok": method}}

    monkeypatch.setattr("services.kraken.KrakenRateLimiter.acquire", fake_acquire)
    monkeypatch.setattr(service, "_rate_limit", no_sleep_rate_limit)
    monkeypatch.setattr(service._api, "query_private", fake_query_private)
    monkeypatch.setattr(service._api, "query_public", fake_query_public)

    await service._request_once("AddOrder", {}, private=True)
    await service._request_once("Balance", {}, private=True)
    await service._request_once("Ticker", {}, private=False)

    assert captured_weights == [2.0, 1.5, 1.0]
