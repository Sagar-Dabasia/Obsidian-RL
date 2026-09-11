"""Cross-Market Trend Engine V1."""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Literal

from obsidian_rl.data.contracts import MarketBar


@dataclass(frozen=True)
class TrendConfig:
    """Configuration for Trend Engine V1."""

    short_horizon_days: int = 20
    medium_horizon_days: int = 60
    long_horizon_days: int = 120

    @property
    def identity(self) -> str:
        """Deterministic identity for this configuration."""
        data = {
            "version": "1",
            "short": self.short_horizon_days,
            "medium": self.medium_horizon_days,
            "long": self.long_horizon_days,
        }
        encoded = json.dumps(data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TrendSignal:
    """Output signal from the trend engine."""

    direction: Literal["LONG", "SHORT", "FLAT"]
    score: float
    volatility_20d: float
    latest_close: float
    signal_timestamp_utc: int
    reason: str
    input_row_hash: str
    config_identity: str


class TrendEngineError(Exception):
    """Base exception for Trend Engine errors."""


class InsufficientHistoryError(TrendEngineError):
    """Raised when the input series lacks sufficient history."""


class DataQualityError(TrendEngineError):
    """Raised when the input series fails data quality checks."""


def calculate_trend_signal(
    bars: tuple[MarketBar, ...],
    observed_before_ms: int,
    config: TrendConfig | None = None,
) -> TrendSignal:
    """Calculate the trend signal from a chronologically ordered series of bars."""
    config = config or TrendConfig()

    if not isinstance(bars, tuple) or not bars:
        raise DataQualityError("Bars must be a non-empty tuple.")

    # 1. Point-in-time and basic data quality filtering
    valid_bars: list[MarketBar] = []
    last_ts = -1
    asset = bars[0].asset_class
    venue = bars[0].venue
    symbol = bars[0].symbol
    timeframe = bars[0].timeframe

    if timeframe.value not in ("4h", "1d"):
        raise DataQualityError(
            f"Unsupported timeframe {timeframe.value}. Only '4h' and '1d' are supported."
        )

    for bar in bars:
        if bar.observed_at_utc > observed_before_ms:
            continue

        if (
            bar.asset_class != asset
            or bar.venue != venue
            or bar.symbol != symbol
            or bar.timeframe != timeframe
        ):
            raise DataQualityError("Mixed asset, venue, symbol, or timeframe detected.")

        if bar.timestamp_utc <= last_ts:
            raise DataQualityError("Bars are out of order or contain duplicates.")
        last_ts = bar.timestamp_utc

        if not bar.row_hash or not isinstance(bar.row_hash, str) or len(bar.row_hash) != 64:
            raise DataQualityError(f"Invalid row hash for bar at {bar.timestamp_utc}.")

        if not (math.isfinite(bar.close) and bar.close > 0):
            raise DataQualityError(f"Invalid close price {bar.close} at {bar.timestamp_utc}.")

        valid_bars.append(bar)

    if not valid_bars:
        raise InsufficientHistoryError("No valid bars available before the cutoff.")

    # 2. Determine required history
    bars_per_day = 6 if timeframe.value == "4h" else 1
    short_bars = config.short_horizon_days * bars_per_day
    med_bars = config.medium_horizon_days * bars_per_day
    long_bars = config.long_horizon_days * bars_per_day

    max_bars_needed = long_bars + 1  # Need long_bars + 1 to compute return over long_bars period
    if len(valid_bars) < max_bars_needed:
        raise InsufficientHistoryError(
            f"Insufficient history. Need {max_bars_needed} bars, got {len(valid_bars)}."
        )

    # We only care about the last `max_bars_needed` bars
    eval_bars = valid_bars[-max_bars_needed:]
    latest_bar = eval_bars[-1]
    latest_close = latest_bar.close

    # 3. Calculate Returns
    # Return = (latest_close - past_close) / past_close
    close_short = eval_bars[-(short_bars + 1)].close
    close_med = eval_bars[-(med_bars + 1)].close
    close_long = eval_bars[-(long_bars + 1)].close

    ret_short = (latest_close - close_short) / close_short
    ret_med = (latest_close - close_med) / close_med
    ret_long = (latest_close - close_long) / close_long

    # 4. Calculate 20d Volatility (std dev of log returns over short_bars)
    # We need the last `short_bars` returns, which means we need the last `short_bars + 1` prices
    short_prices = [b.close for b in eval_bars[-(short_bars + 1) :]]
    log_returns = [
        math.log(short_prices[i] / short_prices[i - 1]) for i in range(1, len(short_prices))
    ]
    mean_log_ret = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_log_ret) ** 2 for r in log_returns) / len(log_returns)
    # We use raw standard deviation of log returns as realized volatility
    # Since position sizing is not implemented yet, raw stdev is sufficient.
    vol_20d = math.sqrt(variance)

    # 5. Logic
    direction: Literal["LONG", "SHORT", "FLAT"] = "FLAT"
    reason = "Mixed or zero returns across horizons."
    score = 0.0

    if ret_short > 0 and ret_med > 0 and ret_long > 0:
        direction = "LONG"
        reason = "All three horizon returns are strictly positive."
        score = 1.0
    elif ret_short < 0 and ret_med < 0 and ret_long < 0:
        direction = "SHORT"
        reason = "All three horizon returns are strictly negative."
        score = -1.0
    else:
        # Score could be an average of signs
        signs = []
        for r in (ret_short, ret_med, ret_long):
            if r > 0:
                signs.append(1)
            elif r < 0:
                signs.append(-1)
            else:
                signs.append(0)
        score = sum(signs) / 3.0

    return TrendSignal(
        direction=direction,
        score=round(score, 4),
        volatility_20d=vol_20d,
        latest_close=latest_close,
        signal_timestamp_utc=latest_bar.observed_at_utc,
        reason=reason,
        input_row_hash=latest_bar.row_hash or "",
        config_identity=config.identity,
    )
