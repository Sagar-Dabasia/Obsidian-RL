"""Cross-asset market-data provider adapters (`BinanceSpotProvider`, `OandaPracticeProvider`)."""

from obsidian_rl.data.providers.base import BaseRestProvider, MarketDataProvider
from obsidian_rl.data.providers.binance import BinanceSpotProvider
from obsidian_rl.data.providers.errors import (
    AuthenticationError,
    MalformedResponseError,
    ProviderError,
    RateLimitError,
    TransportError,
    UnsupportedSymbolTimeframeError,
    scrub_secrets,
)
from obsidian_rl.data.providers.oanda import OandaPracticeProvider

__all__ = [
    "AuthenticationError",
    "BaseRestProvider",
    "BinanceSpotProvider",
    "MalformedResponseError",
    "MarketDataProvider",
    "OandaPracticeProvider",
    "ProviderError",
    "RateLimitError",
    "TransportError",
    "UnsupportedSymbolTimeframeError",
    "scrub_secrets",
]
