"""Historical and cross-asset market-data layer: schemas, contracts, validation, clients, store."""

from obsidian_rl.data.contracts import (
    DEFAULT_MAX_SKEW_MS,
    SCHEMA_VERSION_V2,
    EventNewsItem,
    MarketBar,
)
from obsidian_rl.data.fingerprint import (
    canonical_json,
    compute_canonical_sha256,
    compute_event_news_hash,
    compute_market_bar_hash,
    verify_contract_hash,
)

__all__ = [
    "DEFAULT_MAX_SKEW_MS",
    "SCHEMA_VERSION_V2",
    "EventNewsItem",
    "MarketBar",
    "canonical_json",
    "compute_canonical_sha256",
    "compute_event_news_hash",
    "compute_market_bar_hash",
    "verify_contract_hash",
]
