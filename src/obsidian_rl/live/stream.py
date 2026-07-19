"""Websocket kline stream client (public market data only; ADR-003).

Consumes {symbol}@kline_{interval} events. Event fields verified against official docs:
k.t open time, k.T close time, k.i interval, k.o/h/l/c prices, k.v volume, k.n trades,
k.x "Is this kline closed?", k.q quote volume, k.V/k.Q taker buy volumes.
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KlineEvent:
    open_time: int
    close_time: int
    is_closed: bool
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int
    taker_buy_volume: float
    taker_buy_quote_volume: float

    def to_candle(self) -> dict[str, float | int]:
        return {
            "open_time": self.open_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "close_time": self.close_time,
            "quote_volume": self.quote_volume,
            "trades": self.trades,
            "taker_buy_volume": self.taker_buy_volume,
            "taker_buy_quote_volume": self.taker_buy_quote_volume,
        }


def parse_kline_event(raw: str | bytes) -> KlineEvent | None:
    """Parse one websocket message; None for non-kline payloads."""
    msg = json.loads(raw)
    k = msg.get("k") if isinstance(msg, dict) else None
    if not isinstance(k, dict):
        return None
    return KlineEvent(
        open_time=int(k["t"]),
        close_time=int(k["T"]),
        is_closed=bool(k["x"]),
        open=float(k["o"]),
        high=float(k["h"]),
        low=float(k["l"]),
        close=float(k["c"]),
        volume=float(k["v"]),
        quote_volume=float(k["q"]),
        trades=int(k["n"]),
        taker_buy_volume=float(k["V"]),
        taker_buy_quote_volume=float(k["Q"]),
    )


async def kline_events(
    ws_base_url: str, symbol: str, interval: str, *, max_reconnects: int = 1_000_000
) -> AsyncIterator[KlineEvent]:
    """Yield kline events with automatic reconnection (caller backfills after gaps)."""
    import asyncio

    import websockets

    url = f"{ws_base_url.rstrip('/')}/{symbol.lower()}@kline_{interval}"
    attempts = 0
    while attempts < max_reconnects:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                logger.info("connected to %s", url)
                attempts = 0
                async for raw in ws:
                    event = parse_kline_event(raw)
                    if event is not None:
                        yield event
        except Exception as exc:
            attempts += 1
            wait = min(2.0**attempts, 60.0)
            logger.warning("stream error (%s); reconnecting in %.0fs", exc, wait)
            await asyncio.sleep(wait)
    raise RuntimeError("websocket reconnect budget exhausted")
