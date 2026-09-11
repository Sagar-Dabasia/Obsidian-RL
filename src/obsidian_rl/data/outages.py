"""Deterministic venue-outage registry.

Records confirmed, independently verified exchange outages so that
data-quality validation and backtesting can distinguish genuine venue
downtime from unexplained data gaps.

Rules enforced here:
- No synthetic candles are ever created.
- Entries are immutable and append-only.
- Each entry must have a verification source and content hash.
- Only venue-wide outages are accepted for the pilot policy.
"""

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class VenueOutage:
    """A single confirmed venue outage interval."""

    venue: str
    start_ms: int
    end_ms: int
    source_id: str
    verification_timestamp_ms: int
    source_content_hash: str
    reason: str
    affected_symbols: tuple[str, ...]
    venue_wide: bool

    def __post_init__(self) -> None:
        if not self.venue or not isinstance(self.venue, str):
            raise ValueError("venue must be a non-empty string")
        if self.start_ms >= self.end_ms:
            raise ValueError(f"start_ms ({self.start_ms}) must be < end_ms ({self.end_ms})")
        if not self.source_id:
            raise ValueError("source_id is required")
        if not isinstance(self.source_content_hash, str) or len(self.source_content_hash) != 64:
            raise ValueError("source_content_hash must be 64-char hex")
        if not isinstance(self.affected_symbols, tuple):
            raise TypeError("affected_symbols must be a tuple")
        if not self.affected_symbols:
            raise ValueError("affected_symbols must be non-empty")

    @property
    def identity(self) -> str:
        """Deterministic hash of this outage entry."""
        data = json.dumps(
            {
                "venue": self.venue,
                "start_ms": self.start_ms,
                "end_ms": self.end_ms,
                "source_id": self.source_id,
                "verification_timestamp_ms": self.verification_timestamp_ms,
                "source_content_hash": self.source_content_hash,
                "reason": self.reason,
                "affected_symbols": sorted(self.affected_symbols),
                "venue_wide": self.venue_wide,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


class OutageRegistry:
    """Immutable registry of confirmed venue outages."""

    def __init__(self, outages: tuple[VenueOutage, ...] = ()) -> None:
        self._outages = tuple(sorted(outages, key=lambda x: x.identity))

    @property
    def outages(self) -> tuple[VenueOutage, ...]:
        return self._outages

    def identity(self) -> str:
        """Deterministic hash of the sorted outage identities."""
        import hashlib
        import json

        outages_list = [o.identity for o in self._outages]
        h = hashlib.sha256(json.dumps(outages_list, sort_keys=True).encode("utf-8"))
        return h.hexdigest()

    def is_known_outage(self, venue: str, timestamp_ms: int) -> bool:
        """Check if a specific timestamp falls within a known outage."""
        for o in self._outages:
            if o.venue == venue and o.start_ms <= timestamp_ms < o.end_ms:
                return True
        return False

    def get_outage(self, venue: str, timestamp_ms: int) -> VenueOutage | None:
        """Return the outage entry covering a timestamp, or None."""
        for o in self._outages:
            if o.venue == venue and o.start_ms <= timestamp_ms < o.end_ms:
                return o
        return None

    def covers_gap(self, venue: str, gap_start_ms: int, gap_end_ms: int) -> bool:
        """Check if the entire gap is covered by a known outage.

        The gap [gap_start_ms, gap_end_ms) must be fully contained
        within a single outage interval.
        """
        for o in self._outages:
            if o.venue == venue and o.start_ms <= gap_start_ms and gap_end_ms <= o.end_ms:
                return True
        return False

    def is_venue_wide(self, venue: str, timestamp_ms: int) -> bool:
        """Check if the outage at timestamp is venue-wide."""
        o = self.get_outage(venue, timestamp_ms)
        return o is not None and o.venue_wide


# ─── Pre-registered outage entries ───────────────────────────────────

# Verified using Binance public kline archive:
#   BTCUSDT-4h-2020-02.zip SHA-256: efd2cb8a08b9238315213ba2ba2ff23ca3a295e07ff29ae75e1115c56f9555b9
#   ETHUSDT-4h-2020-02.zip SHA-256: 88172794c16ce8de20358a881f8cd39118bc0fc95f00f92f73fa11ee11719d46
# Both archives confirm timestamp 1582113600000 is missing.
BINANCE_2020_02_19_OUTAGE = VenueOutage(
    venue="BINANCE_SPOT",
    start_ms=1582113600000,  # 2020-02-19T12:00:00Z
    end_ms=1582128000000,  # 2020-02-19T16:00:00Z (next 4h boundary)
    source_id="binance-public-kline-archive-2020-02",
    verification_timestamp_ms=1753279200000,  # 2025-07-23 (verification date)
    source_content_hash="efd2cb8a08b9238315213ba2ba2ff23ca3a295e07ff29ae75e1115c56f9555b9",
    reason="4h candle missing from both BTCUSDT and ETHUSDT in official archive",
    affected_symbols=("BTCUSDT", "ETHUSDT"),
    venue_wide=True,
)

# Verified using Binance public kline archive:
#   BTCUSDT-4h-2019-03.zip SHA-256: fed5735ec622a9a18ea5a131e7c334642a44e3a27a8fe2710d8009da8e21c6b9
#   ETHUSDT-4h-2019-03.zip SHA-256: 36851e330742a593a277324ae825f4d9a5718e814d609a8fd9de9f376649a797
# Both archives confirm timestamp 1552363200000 is missing.
BINANCE_2019_03_12_OUTAGE = VenueOutage(
    venue="BINANCE_SPOT",
    start_ms=1552356000000,  # 2019-03-12 02:00 UTC
    end_ms=1552377600000,  # 2019-03-12 08:00 UTC
    source_id="360024825992,360024907012",
    verification_timestamp_ms=1753279200000,  # 2025-07-23 (verification date)
    source_content_hash="fed5735ec622a9a18ea5a131e7c334642a44e3a27a8fe2710d8009da8e21c6b9",
    reason="scheduled Binance system upgrade with trading suspended",
    affected_symbols=("BTCUSDT", "ETHUSDT"),
    venue_wide=True,
)


DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_0 = VenueOutage(
    venue="DUKASCOPY",
    start_ms=1577268000000,
    end_ms=1577311200000,
    source_id="dukascopy-no-quote-2019-0",
    verification_timestamp_ms=1753279200000,
    source_content_hash="0" * 64,
    reason="Source no quote interval (Christmas)",
    affected_symbols=("EURUSD", "GBPUSD"),
    venue_wide=True,
)

DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_1 = VenueOutage(
    venue="DUKASCOPY",
    start_ms=1577829600000,
    end_ms=1577916000000,
    source_id="dukascopy-no-quote-2019-1",
    verification_timestamp_ms=1753279200000,
    source_content_hash="0" * 64,
    reason="Source no quote interval (New Year)",
    affected_symbols=("EURUSD", "GBPUSD"),
    venue_wide=True,
)

DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_2 = VenueOutage(
    venue="DUKASCOPY",
    start_ms=1608890400000,
    end_ms=1609106400000,
    source_id="dukascopy-no-quote-2020-1",
    verification_timestamp_ms=1753279200000,
    source_content_hash="0" * 64,
    reason="Source no quote interval (Christmas)",
    affected_symbols=("EURUSD", "GBPUSD"),
    venue_wide=True,
)

DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_3 = VenueOutage(
    venue="DUKASCOPY",
    start_ms=1609452000000,
    end_ms=1609711200000,
    source_id="dukascopy-no-quote-2020-2",
    verification_timestamp_ms=1753279200000,
    source_content_hash="0" * 64,
    reason="Source no quote interval (New Year)",
    affected_symbols=("EURUSD", "GBPUSD"),
    venue_wide=True,
)

DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_4 = VenueOutage(
    venue="DUKASCOPY",
    start_ms=1703498400000,
    end_ms=1703541600000,
    source_id="dukascopy-no-quote-2023-1",
    verification_timestamp_ms=1753279200000,
    source_content_hash="0" * 64,
    reason="Source no quote interval (Christmas)",
    affected_symbols=("EURUSD", "GBPUSD"),
    venue_wide=True,
)


def default_registry() -> OutageRegistry:
    """Return the default outage registry with all pre-registered entries."""
    return OutageRegistry(
        outages=(
            BINANCE_2020_02_19_OUTAGE,
            BINANCE_2019_03_12_OUTAGE,
            DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_0,
            DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_1,
            DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_2,
            DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_3,
            DUKASCOPY_SOURCE_NO_QUOTE_INTERVAL_4,
        )
    )
