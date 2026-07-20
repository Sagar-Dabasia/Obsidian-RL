"""Candle validation: duplicates, gaps, malformed OHLCV, interval spacing, finality.

Validation never repairs or fabricates data. Callers decide (explicitly) how to react
to a failing report; nothing here substitutes synthetic values.
"""

from dataclasses import dataclass, field

import pandas as pd

from obsidian_rl.data.schema import CANDLE_COLUMNS, coerce_candle_frame, interval_to_ms


@dataclass
class ValidationReport:
    n_rows: int = 0
    start_ms: int | None = None
    end_ms: int | None = None
    n_duplicates: int = 0
    gaps: list[tuple[int, int]] = field(default_factory=list)  # (last_ok_open, next_open)
    n_missing_candles: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        status = "OK" if self.ok else "FAILED"
        return (
            f"{status}: rows={self.n_rows} span=[{self.start_ms},{self.end_ms}] "
            f"dups={self.n_duplicates} gaps={len(self.gaps)} "
            f"missing={self.n_missing_candles} errors={self.errors[:5]}"
        )


class CandleValidationError(ValueError):
    def __init__(self, report: ValidationReport) -> None:
        super().__init__(report.summary())
        self.report = report


def validate_candles(
    df: pd.DataFrame,
    interval: str,
    *,
    now_ms: int | None = None,
    gaps_are_errors: bool = False,
) -> ValidationReport:
    """Validate a canonical candle frame. Returns a report; never mutates or repairs."""
    rep = ValidationReport()
    ms = interval_to_ms(interval)

    missing_cols = [c for c in CANDLE_COLUMNS if c not in df.columns]
    if missing_cols:
        rep.errors.append(f"missing columns {missing_cols}")
        return rep

    rep.n_rows = len(df)
    if rep.n_rows == 0:
        return rep

    if df[CANDLE_COLUMNS].isna().any().any():
        rep.errors.append("NaN values present")

    ot = df["open_time"]
    rep.start_ms = int(ot.iloc[0])
    rep.end_ms = int(ot.iloc[-1])

    if not ot.is_monotonic_increasing:
        rep.errors.append("open_time not sorted ascending")
    dup_mask = ot.duplicated()
    rep.n_duplicates = int(dup_mask.sum())
    if rep.n_duplicates:
        rep.errors.append(f"{rep.n_duplicates} duplicate open_time values")

    if (ot % ms != 0).any():
        rep.errors.append(f"open_time values not aligned to {interval} boundaries")
    bad_close = df["close_time"] != df["open_time"] + ms - 1
    if bad_close.any():
        rep.errors.append(f"{int(bad_close.sum())} rows with close_time != open_time+{ms}-1")

    # Gaps (only meaningful when sorted and deduplicated). Use positional access so a
    # filtered/holey caller index cannot corrupt gap boundaries or missing counts.
    if ot.is_monotonic_increasing and not rep.n_duplicates and rep.n_rows > 1:
        ot_pos = ot.reset_index(drop=True)
        deltas = ot_pos.diff()
        for pos in range(1, len(ot_pos)):
            if deltas.iloc[pos] != ms:
                prev_open = int(ot_pos.iloc[pos - 1])
                next_open = int(ot_pos.iloc[pos])
                rep.gaps.append((prev_open, next_open))
                rep.n_missing_candles += max(0, int((next_open - prev_open) // ms) - 1)
        if rep.gaps and gaps_are_errors:
            rep.errors.append(f"{len(rep.gaps)} gaps ({rep.n_missing_candles} missing candles)")

    prices = df[["open", "high", "low", "close"]]
    if (prices <= 0).any().any():
        rep.errors.append("non-positive prices present")
    if (df["volume"] < 0).any() or (df["quote_volume"] < 0).any():
        rep.errors.append("negative volume present")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        rep.errors.append("high below open/close/low on some rows")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        rep.errors.append("low above open/close/high on some rows")

    if now_ms is not None and int(df["close_time"].iloc[-1]) >= now_ms:
        rep.errors.append("final candle is not finalized (close_time >= now)")

    return rep


def drop_unfinalized(df: pd.DataFrame, now_ms: int) -> pd.DataFrame:
    """Return only candles whose close_time is strictly in the past (finalized)."""
    out = df[df["close_time"] < now_ms]
    return coerce_candle_frame(out)


def require_valid(
    df: pd.DataFrame,
    interval: str,
    *,
    now_ms: int | None = None,
    gaps_are_errors: bool = False,
) -> ValidationReport:
    rep = validate_candles(df, interval, now_ms=now_ms, gaps_are_errors=gaps_are_errors)
    if not rep.ok:
        raise CandleValidationError(rep)
    return rep
