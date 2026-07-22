"""Canonical hashing and immutability utilities for Cycle 02 data contracts.

Provides canonical JSON (`allow_nan=False`, sorted keys, compact separators)
and deterministic SHA-256 fingerprinting (`MarketBar`, `EventNewsItem`)
while ensuring hash calculation excludes self-hash fields (`row_hash`, `record_hash`).
"""

import dataclasses
import hashlib
import json
from collections.abc import Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from obsidian_rl.data.contracts import EventNewsItem, MarketBar


def _normalize_for_json(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize dictionary values for canonical JSON (converting Enums to string values)."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, Enum):
            out[k] = v.value
        elif isinstance(v, (tuple, list, set)):
            out[k] = [item.value if isinstance(item, Enum) else item for item in v]
        else:
            out[k] = v
    return out


def _canonical_json(data: dict[str, Any]) -> bytes:
    """Serialize a dictionary as canonical sorted-keys compact JSON with allow_nan=False."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_json(data: Any) -> bytes:
    """Convert a contract instance or dictionary into canonical compact JSON bytes.

    If `data` is a dataclass instance, converts via `dataclasses.asdict()`.
    Normalizes Enums to stable string `.value` representations.
    Rejects NaN and Infinity values (`allow_nan=False`).
    """
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        payload = dataclasses.asdict(data)
    elif isinstance(data, dict):
        payload = dict(data)
    else:
        raise TypeError(f"Expected dict or dataclass instance, got {type(data).__name__}")
    normalized = _normalize_for_json(payload)
    return _canonical_json(normalized)


def compute_canonical_sha256(
    data: Any,
    exclude_keys: Sequence[str] = ("row_hash", "record_hash"),
) -> str:
    """Compute the deterministic 64-character lowercase SHA-256 hex digest of a data object.

    Excludes the specified keys (`row_hash` or `record_hash`) before canonical JSON serialization.
    """
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        payload = dataclasses.asdict(data)
    elif isinstance(data, dict):
        payload = dict(data)
    else:
        raise TypeError(f"Expected dict or dataclass instance, got {type(data).__name__}")

    for key in exclude_keys:
        payload.pop(key, None)

    normalized = _normalize_for_json(payload)
    return hashlib.sha256(_canonical_json(normalized)).hexdigest()


def compute_market_bar_hash(bar: "MarketBar | dict[str, Any] | Any") -> str:
    """Compute the deterministic SHA-256 hash of a MarketBar excluding `row_hash`."""
    return compute_canonical_sha256(bar, exclude_keys=("row_hash",))


def compute_event_news_hash(item: "EventNewsItem | dict[str, Any] | Any") -> str:
    """Compute the deterministic SHA-256 hash of an EventNewsItem excluding `record_hash`.

    Note: `raw_content_hash` is retained in the dictionary during canonical serialization.
    """
    return compute_canonical_sha256(item, exclude_keys=("record_hash",))


def verify_contract_hash(contract: Any) -> bool:
    """Verify that a data contract's stored hash exactly matches its canonical computed hash.

    Returns True if valid, or raises RuntimeError if mismatched.
    """
    if not dataclasses.is_dataclass(contract) or isinstance(contract, type):
        raise TypeError(f"Expected dataclass instance, got {type(contract).__name__}")

    if hasattr(contract, "row_hash"):
        stored = contract.row_hash
        computed = compute_market_bar_hash(contract)
        if stored != computed:
            raise RuntimeError(
                f"MarketBar hash mismatch: stored {stored!r} != computed {computed!r}"
            )
        return True
    elif hasattr(contract, "record_hash"):
        stored = contract.record_hash
        computed = compute_event_news_hash(contract)
        if stored != computed:
            raise RuntimeError(
                f"EventNewsItem hash mismatch: stored {stored!r} != computed {computed!r}"
            )
        return True
    else:
        raise ValueError(
            f"Contract {type(contract).__name__} has neither 'row_hash' nor 'record_hash'"
        )
