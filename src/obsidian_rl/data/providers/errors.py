"""Typed exception hierarchy and secret scrubbing for market-data provider adapters.

All provider exceptions inherit from `ProviderError` and automatically scrub registered
secrets (tokens, authorization headers, credentials) from message strings and string
representations to guarantee credentials never leak to terminal, logs, or reports.
"""

from collections.abc import Iterable


def scrub_secrets(text: str, secrets: Iterable[str | None] = ()) -> str:
    """Replace all non-empty secret strings and Bearer header patterns in text with '[REDACTED]'."""
    if not isinstance(text, str):
        text = str(text)

    # First, scrub any explicit secret strings passed in
    for secret in secrets:
        if secret and isinstance(secret, str) and len(secret.strip()) >= 3:
            text = text.replace(secret, "[REDACTED]")

    # Second, scrub standard Authorization / Bearer header patterns proactively
    import re

    text = re.sub(
        r"(?i)(authorization['\":\s]+bearer\s+)([^\s'\"},]+)",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(bearer\s+)([a-z0-9\-\._~+/]+=*)",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)(oanda_api_token['\":\s=]+)([^\s'\"},]+)",
        r"\1[REDACTED]",
        text,
    )
    return text


class ProviderError(Exception):
    """Base exception for all market-data provider adapter errors."""

    def __init__(self, message: str, secrets: Iterable[str | None] = ()) -> None:
        self._secrets = tuple(s for s in secrets if s and isinstance(s, str))
        scrubbed = scrub_secrets(message, self._secrets)
        super().__init__(scrubbed)

    def __str__(self) -> str:
        return scrub_secrets(super().__str__(), self._secrets)

    def __repr__(self) -> str:
        return scrub_secrets(super().__repr__(), self._secrets)


class AuthenticationError(ProviderError):
    """Raised when authentication or authorization fails (HTTP 401/403 or missing token)."""


class RateLimitError(ProviderError):
    """Raised when provider rate limits are exceeded after exhausting maximum retries (HTTP 429)."""


class MalformedResponseError(ProviderError):
    """Raised when responses are invalid JSON, missing required fields, or violate invariants."""


class UnsupportedSymbolTimeframeError(ProviderError):
    """Raised when requested symbol, interval, or granularity is not supported by the provider."""


class TransportError(ProviderError):
    """Raised on network connection failures, timeouts, or HTTP 5xx server errors after retries."""
