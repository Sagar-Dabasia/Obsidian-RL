"""Tests for websocket kline stream parsing and validation."""

import json

from obsidian_rl.live.stream import KlineEvent, parse_kline_event


def test_parse_kline_event_valid() -> None:
    payload = {
        "e": "kline",
        "E": 1700000900000,
        "s": "BTCUSDT",
        "k": {
            "t": 1700000000000,
            "T": 1700000899999,
            "s": "BTCUSDT",
            "i": "15m",
            "f": 100,
            "L": 200,
            "o": "40000.0",
            "c": "40100.0",
            "h": "40200.0",
            "l": "39900.0",
            "v": "10.5",
            "n": 101,
            "x": True,
            "q": "420500.0",
            "V": "5.0",
            "Q": "200000.0",
            "B": "0",
        },
    }
    event = parse_kline_event(json.dumps(payload))
    assert event is not None
    assert isinstance(event, KlineEvent)
    assert event.event_time_ms == 1700000900000
    assert event.open_time == 1700000000000
    assert event.close_time == 1700000899999
    assert event.is_closed is True
    assert event.open == 40000.0
    assert event.close == 40100.0
    assert event.volume == 10.5
    assert event.to_candle()["open"] == 40000.0


def test_parse_kline_event_non_kline_type() -> None:
    payload = {
        "e": "aggTrade",
        "E": 1700000900000,
        "s": "BTCUSDT",
        "k": {"t": 1700000000000, "T": 1700000899999, "i": "15m", "x": True},
    }
    assert parse_kline_event(json.dumps(payload)) is None


def test_parse_kline_event_malformed_or_invalid() -> None:
    # Missing E or k
    assert parse_kline_event(json.dumps({"e": "kline", "s": "BTCUSDT"})) is None
    # close_time < open_time
    payload_bad_time = {
        "e": "kline",
        "E": 1700000900000,
        "s": "BTCUSDT",
        "k": {
            "t": 1700000899999,
            "T": 1700000000000,
            "i": "15m",
            "o": "40000",
            "c": "40100",
            "h": "40200",
            "l": "39900",
            "v": "10",
            "q": "400000",
            "n": 10,
            "V": "5",
            "Q": "200000",
            "x": True,
        },
    }
    assert parse_kline_event(json.dumps(payload_bad_time)) is None

    # Negative volume
    payload_neg_vol = {
        "e": "kline",
        "E": 1700000900000,
        "s": "BTCUSDT",
        "k": {
            "t": 1700000000000,
            "T": 1700000899999,
            "i": "15m",
            "o": "40000",
            "c": "40100",
            "h": "40200",
            "l": "39900",
            "v": "-10",
            "q": "400000",
            "n": 10,
            "V": "5",
            "Q": "200000",
            "x": True,
        },
    }
    assert parse_kline_event(json.dumps(payload_neg_vol)) is None

    # Non-finite price
    payload_nan_price = {
        "e": "kline",
        "E": 1700000900000,
        "s": "BTCUSDT",
        "k": {
            "t": 1700000000000,
            "T": 1700000899999,
            "i": "15m",
            "o": "nan",
            "c": "40100",
            "h": "40200",
            "l": "39900",
            "v": "10",
            "q": "400000",
            "n": 10,
            "V": "5",
            "Q": "200000",
            "x": True,
        },
    }
    assert parse_kline_event(json.dumps(payload_nan_price)) is None
