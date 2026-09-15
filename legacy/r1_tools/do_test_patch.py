import os
import re

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix all run_trend_backtest missing eval_start_ms, market_model, exposure_policy
content = re.sub(
    r'run_trend_backtest\((bars, config, cost.*?)\)',
    lambda m: 'run_trend_backtest(' + m.group(1) + (', eval_start_ms=0, market_model=MarketModel.PERPETUAL, exposure_policy=ExposurePolicy.BIDIRECTIONAL' if 'market_model' not in m.group(1) else '') + ')',
    content
)

# And if eval_start_ms is missing but market_model is there:
content = re.sub(
    r'run_trend_backtest\((.*?)market_model=(.*?)\)',
    lambda m: 'run_trend_backtest(' + m.group(1) + 'eval_start_ms=0, market_model=' + m.group(2) + ')' if 'eval_start_ms' not in m.group(1) else m.group(0),
    content
)

# Fix double eval_start_ms
content = content.replace("eval_start_ms=0, eval_start_ms=0", "eval_start_ms=0")

manifest_tests = """    def _write_manifest(manifest_dict, path):
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest_dict, f)

    def test_manifest_duplicate_exact_match_rejected(tmp_path) -> None:
        from obsidian_rl.data.manifest import load_and_validate_manifest
        manifest = {
            "components": [
                {
                    "asset_class": "CRYPTO",
                    "venue": "BINANCE_SPOT",
                    "symbol": "BTCUSDT",
                    "timeframe": "4h",
                    "start_timestamp_utc": 1000,
                    "end_timestamp_utc": 2000,
                    "row_count": 10,
                    "digest": "0" * 64
                },
                {
                    "asset_class": "CRYPTO",
                    "venue": "BINANCE_SPOT",
                    "symbol": "BTCUSDT",
                    "timeframe": "4h",
                    "start_timestamp_utc": 1000,
                    "end_timestamp_utc": 2000,
                    "row_count": 10,
                    "digest": "0" * 64
                }
            ]
        }
        p = tmp_path / "man.json"
        _write_manifest(manifest, p)
        import pytest
        with pytest.raises(ValueError, match="Manifest component missing or ambiguous"):
            load_and_validate_manifest(str(p), "CRYPTO", "BINANCE_SPOT", "BTCUSDT", "4h", 1000, 2000, 10, "0"*64)

    def test_manifest_wrong_identity_rejected(tmp_path) -> None:
        from obsidian_rl.data.manifest import load_and_validate_manifest
        manifest = {
            "components": [
                {
                    "asset_class": "CRYPTO",
                    "venue": "BINANCE_SPOT",
                    "symbol": "ETHUSDT",
                    "timeframe": "4h",
                    "start_timestamp_utc": 1000,
                    "end_timestamp_utc": 2000,
                    "row_count": 10,
                    "digest": "0" * 64
                }
            ]
        }
        p = tmp_path / "man.json"
        _write_manifest(manifest, p)
        import pytest
        with pytest.raises(ValueError, match="Manifest component missing or ambiguous"):
            load_and_validate_manifest(str(p), "CRYPTO", "BINANCE_SPOT", "BTCUSDT", "4h", 1000, 2000, 10, "0"*64)

    def test_manifest_malformed_values_rejected(tmp_path) -> None:
        from obsidian_rl.data.manifest import load_and_validate_manifest
        manifest = {
            "components": [
                {
                    "asset_class": "CRYPTO",
                    "venue": "BINANCE_SPOT",
                    "symbol": "BTCUSDT",
                    "timeframe": "4h",
                    "start_timestamp_utc": "1000",
                    "end_timestamp_utc": 2000,
                    "row_count": 10,
                    "digest": "0" * 64
                }
            ]
        }
        p = tmp_path / "man.json"
        _write_manifest(manifest, p)
        import pytest
        with pytest.raises(ValueError, match="Manifest component boundaries must be integers"):
            load_and_validate_manifest(str(p), "CRYPTO", "BINANCE_SPOT", "BTCUSDT", "4h", 1000, 2000, 10, "0"*64)

    def test_runtime_bounds_count_and_digest_rejected(tmp_path) -> None:
        from obsidian_rl.data.manifest import load_and_validate_manifest
        manifest = {
            "components": [
                {
                    "asset_class": "CRYPTO",
                    "venue": "BINANCE_SPOT",
                    "symbol": "BTCUSDT",
                    "timeframe": "4h",
                    "start_timestamp_utc": 2000,
                    "end_timestamp_utc": 1000,
                    "row_count": 10,
                    "digest": "0" * 64
                }
            ]
        }
        p = tmp_path / "man.json"
        _write_manifest(manifest, p)
        import pytest
        with pytest.raises(ValueError, match="start >= end"):
            load_and_validate_manifest(str(p), "CRYPTO", "BINANCE_SPOT", "BTCUSDT", "4h", 2000, 1000, 10, "0"*64)
"""
content = re.sub(r'    def test_manifest_duplicate_exact_match_rejected.*?$', manifest_tests, content, flags=re.DOTALL|re.MULTILINE)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
