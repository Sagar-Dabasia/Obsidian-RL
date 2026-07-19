"""REST client tests with a fully mocked HTTP session. No network access."""

from typing import Any

import pytest

from obsidian_rl.data.binance_client import MAX_LIMIT, BinanceFuturesRest, DataFetchError
from obsidian_rl.data.schema import interval_to_ms

MS15 = interval_to_ms("15m")


def make_raw_klines(start_ms: int, n: int) -> list[list[Any]]:
    rows = []
    for i in range(n):
        ot = start_ms + i * MS15
        rows.append(
            [ot, "100", "101", "99", "100.5", "10", ot + MS15 - 1, "1005", 5, "5", "502", "0"]
        )
    return rows


class FakeResponse:
    def __init__(
        self, status_code: int, payload: Any = None, headers: dict[str, str] | None = None
    ):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = str(payload)[:100]

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """Returns queued responses; records request params."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: float) -> FakeResponse:
        self.calls.append(dict(params))
        return self._responses.pop(0)


def make_client(session: FakeSession, retries: int = 3) -> BinanceFuturesRest:
    return BinanceFuturesRest(
        "https://example.invalid", session=session, max_retries=retries, sleep=lambda s: None
    )


def test_single_page_fetch() -> None:
    raw = make_raw_klines(0, 100)
    session = FakeSession([FakeResponse(200, raw)])
    df = make_client(session).fetch_klines("BTCUSDT", "15m", 0, 100 * MS15)
    assert len(df) == 100
    assert session.calls[0]["symbol"] == "BTCUSDT"


def test_pagination_advances_cursor() -> None:
    page1 = make_raw_klines(0, MAX_LIMIT)
    page2 = make_raw_klines(MAX_LIMIT * MS15, 10)
    session = FakeSession([FakeResponse(200, page1), FakeResponse(200, page2)])
    df = make_client(session).fetch_klines("BTCUSDT", "15m", 0)
    assert len(df) == MAX_LIMIT + 10
    assert session.calls[1]["startTime"] == MAX_LIMIT * MS15


def test_rate_limit_retries_then_succeeds() -> None:
    raw = make_raw_klines(0, 5)
    session = FakeSession([FakeResponse(429, None, {"Retry-After": "0"}), FakeResponse(200, raw)])
    df = make_client(session).fetch_klines("BTCUSDT", "15m", 0, 5 * MS15)
    assert len(df) == 5


def test_server_errors_exhaust_retries() -> None:
    session = FakeSession([FakeResponse(500), FakeResponse(502), FakeResponse(503)])
    with pytest.raises(DataFetchError, match="after 3 retries"):
        make_client(session, retries=3).fetch_klines("BTCUSDT", "15m", 0, MS15)


def test_client_error_fails_immediately_no_fallback() -> None:
    session = FakeSession([FakeResponse(400, {"code": -1121, "msg": "Invalid symbol."})])
    with pytest.raises(DataFetchError, match="HTTP 400"):
        make_client(session).fetch_klines("NOPE", "15m", 0, MS15)
    assert len(session.calls) == 1  # no retry, no synthetic substitute


def test_empty_result_returns_empty_frame() -> None:
    session = FakeSession([FakeResponse(200, [])])
    df = make_client(session).fetch_klines("BTCUSDT", "15m", 0, MS15)
    assert df.empty
