"""Canonical immutable manifest loading and validation."""
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ManifestComponent:
    asset_class: str
    venue: str
    symbol: str
    timeframe: str
    start_timestamp_utc: int
    end_timestamp_utc: int
    row_count: int
    digest: str

def load_and_validate_manifest(
    manifest_path: str,
    asset_class: str,
    venue: str,
    symbol: str,
    timeframe: str,
    runtime_first_ts: int,
    runtime_end_excl_ts: int,
    runtime_row_count: int,
    runtime_digest: str,
    cli_start_ms: int | None = None,
    cli_end_ms: int | None = None,
) -> ManifestComponent:
    with open(manifest_path, encoding="utf-8") as f:
        manifest_data = json.load(f)

    components = manifest_data.get("components")
    if not isinstance(components, list):
        raise ValueError("Manifest component missing or ambiguous")

    matches = [
        c for c in components
        if c.get("asset_class") == asset_class
        and c.get("venue") == venue
        and c.get("symbol") == symbol
        and c.get("timeframe") == timeframe
    ]

    if len(matches) != 1:
        raise ValueError("Manifest component missing or ambiguous")

    c = matches[0]

    start_ts = c.get("start_timestamp_utc")
    end_ts = c.get("end_timestamp_utc")
    row_count = c.get("row_count")
    digest = c.get("digest")

    if type(start_ts) is not int or type(end_ts) is not int or type(row_count) is not int:
        raise ValueError("Manifest component boundaries must be integers")

    if start_ts >= end_ts:
        raise ValueError("start >= end")

    if row_count <= 0:
        raise ValueError("row_count <= 0")

    if not isinstance(digest, str) or not re.match(r"^[0-9a-f]{64}$", digest):
        raise ValueError("Manifest digest is malformed")

    if cli_start_ms is not None and cli_start_ms != start_ts:
        raise ValueError("CLI start boundaries conflict with the manifest")

    if cli_end_ms is not None and cli_end_ms != end_ts:
        raise ValueError("CLI end boundaries conflict with the manifest")

    if runtime_first_ts != start_ts:
        raise ValueError("runtime first timestamp differs from manifest")

    if runtime_end_excl_ts != end_ts:
        raise ValueError("runtime end-exclusive timestamp differs from manifest")

    if runtime_row_count != row_count:
        raise ValueError("Row count differs from manifest")

    if runtime_digest != digest:
        raise ValueError("Computed digest differs from manifest")

    return ManifestComponent(
        asset_class=asset_class,
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        start_timestamp_utc=start_ts,
        end_timestamp_utc=end_ts,
        row_count=row_count,
        digest=digest
    )
