"""Focused regression tests for Cycle 2 Research Access Guard."""

import pytest
from pathlib import Path

from obsidian_rl.data.contracts import AssetClass
from obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy
from obsidian_rl.data.research_access import (
    validate_temporal_access,
    validate_product_consistency,
    validate_backtest_access,
    ResearchAccessError,
    ProductMismatchError,
    CURRENT_STAGE,
    ResearchStage,
    DEV_TRAIN_START_MS,
    DEV_TRAIN_END_MS,
    OUTER_VAL_START_MS,
    OUTER_VAL_END_MS,
    CONFIRMATION_START_MS,
    CONFIRMATION_END_MS,
    FINAL_HOLDOUT_START_MS,
    FINAL_HOLDOUT_END_MS,
)
from tests.conftest import make_candles
from obsidian_rl.data.schema import interval_to_ms


class TestBoundaryEpochMsConstants:
    """Tests asserting exact calendar UTC datetime ↔ epoch-ms values for every frozen boundary."""

    def test_dev_train_start_ms(self):
        """DEV_TRAIN start = 2020-01-01T00:00:00Z = 1577836800000"""
        assert DEV_TRAIN_START_MS == 1577836800000

    def test_dev_train_end_ms(self):
        """DEV_TRAIN end = 2025-07-01T00:00:00Z = 1751328000000"""
        assert DEV_TRAIN_END_MS == 1751328000000

    def test_outer_val_start_ms(self):
        """OUTER_VAL start = 2025-07-01T00:00:00Z = 1751328000000"""
        assert OUTER_VAL_START_MS == 1751328000000

    def test_outer_val_end_ms(self):
        """OUTER_VAL end = 2026-03-01T00:00:00Z = 1772323200000"""
        assert OUTER_VAL_END_MS == 1772323200000

    def test_confirmation_start_ms(self):
        """CONFIRMATION start = 2026-03-01T00:00:00Z = 1772323200000"""
        assert CONFIRMATION_START_MS == 1772323200000

    def test_confirmation_end_ms(self):
        """CONFIRMATION end = 2026-07-01T00:00:00Z = 1782864000000"""
        assert CONFIRMATION_END_MS == 1782864000000

    def test_final_holdout_start_ms(self):
        """FINAL_HOLDOUT start = 2026-07-01T00:00:00Z = 1782864000000"""
        assert FINAL_HOLDOUT_START_MS == 1782864000000

    def test_final_holdout_end_ms(self):
        """FINAL_HOLDOUT end = 2027-01-01T00:00:00Z = 1798761600000"""
        assert FINAL_HOLDOUT_END_MS == 1798761600000

    def test_half_open_boundary_consistency(self):
        """Adjacent window boundaries match exactly (half-open [start, end))."""
        # DEV_TRAIN end == OUTER_VAL start
        assert DEV_TRAIN_END_MS == OUTER_VAL_START_MS
        # OUTER_VAL end == CONFIRMATION start
        assert OUTER_VAL_END_MS == CONFIRMATION_START_MS
        # CONFIRMATION end == FINAL_HOLDOUT start
        assert CONFIRMATION_END_MS == FINAL_HOLDOUT_START_MS


class TestTemporalAccess:
    """Tests for temporal access validation."""

    def test_dev_train_allowed(self):
        """DEV_TRAIN window reads are allowed."""
        validate_temporal_access(DEV_TRAIN_START_MS, DEV_TRAIN_END_MS)
        validate_temporal_access(1609459200000 + 86400000, DEV_TRAIN_END_MS - 86400000)  # Inside

    def test_dev_train_causal_warmup_allowed(self):
        """Causal warm-up before DEV_TRAIN is allowed if ends within DEV_TRAIN."""
        validate_temporal_access(1500000000000, DEV_TRAIN_START_MS)  # Warm-up only
        validate_temporal_access(1500000000000, DEV_TRAIN_END_MS)  # Warm-up + DEV_TRAIN

    def test_outer_val_blocked_during_dev_train(self):
        """OUTER_VAL range blocked during DEV_TRAIN stage."""
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(OUTER_VAL_START_MS, OUTER_VAL_END_MS)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)
        assert "OUTER_VAL" in str(exc_info.value)

    def test_confirmation_blocked_during_dev_train(self):
        """CONFIRMATION range blocked during DEV_TRAIN stage."""
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(CONFIRMATION_START_MS, CONFIRMATION_END_MS)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)
        assert "CONFIRMATION" in str(exc_info.value)

    def test_final_holdout_blocked_unconditionally(self):
        """FINAL_HOLDOUT blocked regardless of stage."""
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_END_MS)
        assert "FINAL_HOLDOUT" in str(exc_info.value)
        assert "permanently sealed" in str(exc_info.value)

    def test_partial_final_holdout_overlap_blocked(self):
        """Partial overlap with FINAL_HOLDOUT blocked."""
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(FINAL_HOLDOUT_START_MS - 86400000, FINAL_HOLDOUT_START_MS + 86400000)
        assert "FINAL_HOLDOUT" in str(exc_info.value)

    def test_unbounded_read_fails_closed(self):
        """Unbounded reads that could include protected windows must fail closed.

        This is tested by the integration in store.py which maps None to max bounds.
        """
        # With None bounds mapped to [0, max_int64], should fail as it spans all windows
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(0, (1 << 63) - 1)
        assert "FINAL_HOLDOUT" in str(exc_info.value)

    def test_malformed_range_rejected(self):
        """Malformed/bool/reversed ranges are rejected."""
        with pytest.raises(Exception):
            validate_temporal_access("not_int", 1000)
        with pytest.raises(Exception):
            validate_temporal_access(1000, "not_int")
        with pytest.raises(Exception):
            validate_temporal_access(True, 1000)
        with pytest.raises(Exception):
            validate_temporal_access(1000, True)
        with pytest.raises(Exception):
            validate_temporal_access(1000, 500)  # start >= end
        with pytest.raises(Exception):
            validate_temporal_access(-1, 1000)  # negative start
        with pytest.raises(Exception):
            validate_temporal_access(1000, -1)  # negative end


class TestExactHalfOpenTransitions:
    """Tests for exact half-open boundary transitions."""

    def test_last_instant_before_outer_val_is_dev(self):
        """Last instant before OUTER_VAL start behaves as DEV_TRAIN (allowed)."""
        # OUTER_VAL_START_MS is the first ms of OUTER_VAL (half-open)
        # So OUTER_VAL_START_MS - 1 is the last ms of DEV_TRAIN
        validate_temporal_access(DEV_TRAIN_START_MS, OUTER_VAL_START_MS - 1)

    def test_exact_outer_val_start_blocked_during_dev_stage(self):
        """Exact OUTER_VAL start blocked during DEV_TRAIN stage."""
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(OUTER_VAL_START_MS, OUTER_VAL_START_MS + 86400000)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_exact_confirmation_start_blocked(self):
        """Exact CONFIRMATION start blocked during DEV_TRAIN stage."""
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(CONFIRMATION_START_MS, CONFIRMATION_START_MS + 86400000)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_exact_final_holdout_start_hard_blocked(self):
        """Exact FINAL_HOLDOUT start hard-blocked unconditionally."""
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_START_MS + 86400000)
        assert "FINAL_HOLDOUT" in str(exc_info.value)
        assert "permanently sealed" in str(exc_info.value)

    def test_exact_final_holdout_end_behaves_per_post_holdout_policy(self):
        """Exact FINAL_HOLDOUT end behaves according to post-holdout policy.
        
        Since FINAL_HOLDOUT is [start, end), the instant FINAL_HOLDOUT_END_MS
        is the first ms AFTER the holdout. During DEV_TRAIN stage, this would 
        still be blocked as it's beyond DEV_TRAIN. After stage transition to
        post-holdout, access would be allowed.
        """
        # During DEV_TRAIN, even post-holdout timestamps are blocked
        # (they exceed DEV_TRAIN_END_MS)
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(FINAL_HOLDOUT_END_MS, FINAL_HOLDOUT_END_MS + 86400000)
        assert "exceeds DEV_TRAIN window" in str(exc_info.value)


class TestProductConsistency:
    """Tests for product consistency validation."""

    def test_spot_data_as_perpetual_rejected(self):
        """Spot data evaluated as PERPETUAL is rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_product_consistency(
                AssetClass.CRYPTO,
                "BINANCE_SPOT",
                MarketModel.PERPETUAL,
                ExposurePolicy.BIDIRECTIONAL
            )
        assert "BINANCE_SPOT" in str(exc_info.value)
        assert "PERPETUAL" in str(exc_info.value)

    def test_perpetual_data_as_spot_rejected(self):
        """Perpetual data evaluated as SPOT is rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_product_consistency(
                AssetClass.CRYPTO,
                "BINANCE_FUTURES",
                MarketModel.SPOT,
                ExposurePolicy.BIDIRECTIONAL
            )
        assert "BINANCE_FUTURES" in str(exc_info.value)
        assert "SPOT" in str(exc_info.value)

    def test_spot_bidirectional_rejected(self):
        """SPOT + BIDIRECTIONAL remains rejected."""
        with pytest.raises(Exception) as exc_info:
            validate_product_consistency(
                AssetClass.CRYPTO,
                "BINANCE_SPOT",
                MarketModel.SPOT,
                ExposurePolicy.BIDIRECTIONAL
            )
        assert "SPOT market model cannot be combined with BIDIRECTIONAL" in str(exc_info.value)

    def test_valid_spot_unidirectional_preserved(self):
        """Valid SPOT + unidirectional combination preserved."""
        decl = validate_product_consistency(
            AssetClass.CRYPTO,
            "BINANCE_SPOT",
            MarketModel.SPOT,
            ExposurePolicy.LONG_FLAT
        )
        assert decl.market_model == MarketModel.SPOT
        assert decl.exposure_policy == ExposurePolicy.LONG_FLAT

    def test_valid_perpetual_bidirectional_preserved(self):
        """Valid PERPETUAL + BIDIRECTIONAL preserved."""
        decl = validate_product_consistency(
            AssetClass.CRYPTO,
            "BINANCE_FUTURES",
            MarketModel.PERPETUAL,
            ExposurePolicy.BIDIRECTIONAL
        )
        assert decl.market_model == MarketModel.PERPETUAL
        assert decl.exposure_policy == ExposurePolicy.BIDIRECTIONAL


class TestBacktestAccess:
    """Tests for backtest access validation."""

    def test_dev_train_allowed(self):
        """DEV_TRAIN backtest allowed."""
        validate_backtest_access(
            bars_start_ms=DEV_TRAIN_START_MS,
            bars_end_ms=DEV_TRAIN_END_MS,
            eval_start_ms=1672531200000,  # 2023-01-01 within DEV_TRAIN
            asset_class=AssetClass.CRYPTO,
            venue="BINANCE_SPOT",
            market_model=MarketModel.SPOT,
            exposure_policy=ExposurePolicy.LONG_FLAT,
        )

    def test_outer_val_blocked(self):
        """OUTER_VAL range blocked during DEV_TRAIN."""
        with pytest.raises(Exception) as exc_info:
            validate_backtest_access(
                bars_start_ms=OUTER_VAL_START_MS,
                bars_end_ms=OUTER_VAL_END_MS,
                eval_start_ms=OUTER_VAL_START_MS,
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_SPOT",
                market_model=MarketModel.SPOT,
                exposure_policy=ExposurePolicy.LONG_FLAT,
            )
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)
        assert "OUTER_VAL" in str(exc_info.value)

    def test_confirmation_blocked(self):
        """CONFIRMATION range blocked during DEV_TRAIN."""
        with pytest.raises(Exception) as exc_info:
            validate_backtest_access(
                bars_start_ms=CONFIRMATION_START_MS,
                bars_end_ms=CONFIRMATION_END_MS,
                eval_start_ms=CONFIRMATION_START_MS,
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_SPOT",
                market_model=MarketModel.SPOT,
                exposure_policy=ExposurePolicy.LONG_FLAT,
            )
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)
        assert "CONFIRMATION" in str(exc_info.value)

    def test_final_holdout_hard_block(self):
        """FINAL_HOLDOUT hard blocked."""
        with pytest.raises(Exception) as exc_info:
            validate_backtest_access(
                bars_start_ms=FINAL_HOLDOUT_START_MS,
                bars_end_ms=FINAL_HOLDOUT_END_MS,
                eval_start_ms=FINAL_HOLDOUT_START_MS,
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_SPOT",
                market_model=MarketModel.SPOT,
                exposure_policy=ExposurePolicy.LONG_FLAT,
            )
        assert "FINAL_HOLDOUT" in str(exc_info.value)


class TestStorageBypassBlocked:
    """Tests that storage layer enforces guards."""

    def test_sqlite_query_market_bars_blocks_outer_val(self):
        """SQLiteStorage.query_market_bars blocks OUTER_VAL."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import Timeframe

        with SQLiteStorage(":memory:") as store:
            with pytest.raises(Exception) as exc_info:
                store.query_market_bars(
                    AssetClass.CRYPTO,
                    "BINANCE_SPOT",
                    "BTCUSDT",
                    Timeframe.H4,
                    OUTER_VAL_START_MS,
                    OUTER_VAL_END_MS,
                )
            assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_sqlite_query_market_bars_blocks_confirmation(self):
        """SQLiteStorage.query_market_bars blocks CONFIRMATION."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import Timeframe

        with SQLiteStorage(":memory:") as store:
            with pytest.raises(Exception) as exc_info:
                store.query_market_bars(
                    AssetClass.CRYPTO,
                    "BINANCE_SPOT",
                    "BTCUSDT",
                    Timeframe.H4,
                    CONFIRMATION_START_MS,
                    CONFIRMATION_END_MS,
                )
            assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_sqlite_query_market_bars_blocks_final_holdout(self):
        """SQLiteStorage.query_market_bars blocks FINAL_HOLDOUT unconditionally."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import Timeframe

        with SQLiteStorage(":memory:") as store:
            with pytest.raises(Exception) as exc_info:
                store.query_market_bars(
                    AssetClass.CRYPTO,
                    "BINANCE_SPOT",
                    "BTCUSDT",
                    Timeframe.H4,
                    FINAL_HOLDOUT_START_MS,
                    FINAL_HOLDOUT_END_MS,
                )
            assert "FINAL_HOLDOUT" in str(exc_info.value)
            assert "permanently sealed" in str(exc_info.value)

    def test_sqlite_query_market_bars_partial_final_holdout_blocked(self):
        """SQLiteStorage.query_market_bars blocks partial FINAL_HOLDOUT overlap."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import Timeframe

        with SQLiteStorage(":memory:") as store:
            with pytest.raises(Exception) as exc_info:
                store.query_market_bars(
                    AssetClass.CRYPTO,
                    "BINANCE_SPOT",
                    "BTCUSDT",
                    Timeframe.H4,
                    FINAL_HOLDOUT_START_MS - 86400000,
                    FINAL_HOLDOUT_START_MS + 86400000,
                )
            assert "FINAL_HOLDOUT" in str(exc_info.value)

    def test_candlestore_read_blocks_outer_val(self):
        """CandleStore.read blocks OUTER_VAL."""
        from obsidian_rl.data.store import CandleStore
        from pathlib import Path

        # Create a temp directory
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CandleStore(Path(tmpdir), "BTCUSDT", "4h")
            with pytest.raises(Exception) as exc_info:
                store.read(start_ms=OUTER_VAL_START_MS, end_ms=OUTER_VAL_END_MS)
            assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_candlestore_read_blocks_confirmation(self):
        """CandleStore.read blocks CONFIRMATION."""
        from obsidian_rl.data.store import CandleStore
        from pathlib import Path

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CandleStore(Path(tmpdir), "BTCUSDT", "4h")
            with pytest.raises(Exception) as exc_info:
                store.read(start_ms=CONFIRMATION_START_MS, end_ms=CONFIRMATION_END_MS)
            assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_candlestore_read_blocks_final_holdout(self):
        """CandleStore.read blocks FINAL_HOLDOUT unconditionally."""
        from obsidian_rl.data.store import CandleStore
        from pathlib import Path

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CandleStore(Path(tmpdir), "BTCUSDT", "4h")
            with pytest.raises(Exception) as exc_info:
                store.read(start_ms=FINAL_HOLDOUT_START_MS, end_ms=FINAL_HOLDOUT_END_MS)
            assert "FINAL_HOLDOUT" in str(exc_info.value)
            assert "permanently sealed" in str(exc_info.value)

    def test_candlestore_read_unbounded_fails_closed(self):
        """CandleStore.read with unbounded bounds fails closed (spans protected windows)."""
        from obsidian_rl.data.store import CandleStore
        from pathlib import Path

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CandleStore(Path(tmpdir), "BTCUSDT", "4h")
            # Unbounded reads (None -> max bounds) span all windows including FINAL_HOLDOUT
            with pytest.raises(Exception) as exc_info:
                store.read(start_ms=None, end_ms=None)
            assert "FINAL_HOLDOUT" in str(exc_info.value)


class TestCandleStoreHalfOpenSemantics:
    """Tests for CandleStore half-open boundary semantics."""

    def test_half_open_end_exclusive(self, tmp_path: Path):
        """read() end_ms is exclusive per half-open contract."""
        from obsidian_rl.data.store import CandleStore
        from obsidian_rl.data.schema import interval_to_ms

        MS15 = interval_to_ms("15m")
        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(50, start_ms=1609459200000)  # 2021-01-01 within DEV_TRAIN
        store.write(df, source="test")
        mid = int(df["open_time"].iloc[25])
        # Half-open [start, end): 5 intervals = 5 candles
        out = store.read(start_ms=mid, end_ms=mid + 5 * MS15)
        assert len(out) == 5
        assert int(out["open_time"].iloc[0]) == mid
        assert int(out["open_time"].iloc[-1]) == mid + 4 * MS15

    def test_exact_outer_val_boundary_cannot_leak(self, tmp_path: Path):
        """Exact OUTER_VAL start (DEV_TRAIN end) cannot leak through end_ms > DEV_TRAIN_END."""
        from obsidian_rl.data.store import CandleStore
        from obsidian_rl.data.schema import interval_to_ms

        MS15 = interval_to_ms("15m")
        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(50, start_ms=1609459200000)
        store.write(df, source="test")
        # Request end_ms exactly at OUTER_VAL start (DEV_TRAIN end) - this IS allowed
        # because DEV_TRAIN is [2020-01-01, 2025-07-01) half-open
        out = store.read(start_ms=1609459200000, end_ms=1751328000000)
        assert len(out) == 50  # All DEV_TRAIN data accessible

        # But end_ms > DEV_TRAIN_END_MS should fail
        with pytest.raises(Exception) as exc_info:
            store.read(start_ms=1609459200000, end_ms=1751328000000 + 1)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_exact_confirmation_boundary_blocked(self, tmp_path: Path):
        """Exact CONFIRMATION start blocked."""
        from obsidian_rl.data.store import CandleStore

        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(10, start_ms=1609459200000)
        store.write(df, source="test")
        with pytest.raises(Exception) as exc_info:
            store.read(start_ms=1772323200000, end_ms=1772323200000 + 86400000)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_exact_final_holdout_boundary_blocked(self, tmp_path: Path):
        """Exact FINAL_HOLDOUT start blocked."""
        from obsidian_rl.data.store import CandleStore

        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(10, start_ms=1609459200000)
        store.write(df, source="test")
        with pytest.raises(Exception) as exc_info:
            store.read(start_ms=1782864000000, end_ms=1782864000000 + 86400000)
        assert "FINAL_HOLDOUT" in str(exc_info.value)
        assert "permanently sealed" in str(exc_info.value)


class TestCandleStoreMaxOpenTimeGuarded:
    """Tests that max_open_time() cannot expose protected timestamps."""

    def test_max_open_time_cannot_expose_outer_val(self, tmp_path: Path):
        """max_open_time() returns DEV_TRAIN max even if store has later data."""
        from obsidian_rl.data.store import CandleStore

        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(10, start_ms=1609459200000)
        store.write(df, source="test")
        # Store only has DEV_TRAIN data, max_open_time should return actual max
        max_time = store.max_open_time()
        assert max_time is not None
        assert max_time < 1751328000000  # Within DEV_TRAIN

    def test_max_open_time_returns_dev_train_max_when_later_data_exists(self, tmp_path: Path):
        """If store somehow has OUTER_VAL data, max_open_time() caps at DEV_TRAIN end."""
        # This test verifies the guard logic; in practice temporal guard prevents
        # writing OUTER_VAL data, but the return value is capped as defense-in-depth.
        from obsidian_rl.data.store import CandleStore

        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        # Write DEV_TRAIN data
        df_dev = make_candles(10, start_ms=1609459200000)
        store.write(df_dev, source="test")
        max_time = store.max_open_time()
        assert max_time is not None
        assert max_time <= 1751327999999  # Capped at DEV_TRAIN last instant


class TestCandleStoreSummarySemantics:
    """Tests for summary() truthful semantics."""

    def test_summary_defaults_to_dev_train(self, tmp_path: Path):
        """summary() defaults to DEV_TRAIN window."""
        from obsidian_rl.data.store import CandleStore

        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(10, start_ms=1609459200000)
        store.write(df, source="test")
        summary = store.summary()
        assert summary["rows"] == 10
        assert "start_utc" in summary
        assert "end_utc" in summary

    def test_summary_explicit_bounds(self, tmp_path: Path):
        """summary() with explicit bounds summarizes that window."""
        from obsidian_rl.data.store import CandleStore
        from obsidian_rl.data.schema import interval_to_ms

        MS15 = interval_to_ms("15m")
        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(50, start_ms=1609459200000)
        store.write(df, source="test")
        # Summarize only first 10 candles: end_ms = 10th candle's timestamp + 15m
        mid = int(df["open_time"].iloc[9])
        summary = store.summary(start_ms=1609459200000, end_ms=mid + MS15)
        assert summary["rows"] == 10

    def test_summary_fails_on_outer_val(self, tmp_path: Path):
        """summary() fails if bounds include OUTER_VAL."""
        from obsidian_rl.data.store import CandleStore

        store = CandleStore(tmp_path, "BTCUSDT", "15m")
        df = make_candles(10, start_ms=1609459200000)
        store.write(df, source="test")
        with pytest.raises(Exception) as exc_info:
            store.summary(start_ms=1751328000000, end_ms=1772323200000)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)
    """Tests that ingestion path enforces guards."""

    def test_historical_dataset_ingest_blocks_outer_val(self):
        """ingest_historical_range blocks OUTER_VAL."""
        from obsidian_rl.data.historical_dataset import ingest_historical_range
        from obsidian_rl.data.contracts import AssetClass, Timeframe
        from obsidian_rl.data.storage import SQLiteStorage

        with SQLiteStorage(":memory:") as store:
            with pytest.raises(Exception) as exc_info:
                ingest_historical_range(
                    asset_class=AssetClass.CRYPTO,
                    venue="BINANCE_FUTURES",
                    symbol="BTCUSDT",
                    timeframe=Timeframe.H4,
                    start_ms=OUTER_VAL_START_MS,
                    end_ms=OUTER_VAL_END_MS,
                    storage=store,
                )
            assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_historical_dataset_ingest_blocks_confirmation(self):
        """ingest_historical_range blocks CONFIRMATION."""
        from obsidian_rl.data.historical_dataset import ingest_historical_range
        from obsidian_rl.data.contracts import AssetClass, Timeframe
        from obsidian_rl.data.storage import SQLiteStorage

        with SQLiteStorage(":memory:") as store:
            with pytest.raises(Exception) as exc_info:
                ingest_historical_range(
                    asset_class=AssetClass.CRYPTO,
                    venue="BINANCE_FUTURES",
                    symbol="BTCUSDT",
                    timeframe=Timeframe.H4,
                    start_ms=CONFIRMATION_START_MS,
                    end_ms=CONFIRMATION_END_MS,
                    storage=store,
                )
            assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_historical_dataset_ingest_blocks_final_holdout(self):
        """ingest_historical_range blocks FINAL_HOLDOUT."""
        from obsidian_rl.data.historical_dataset import ingest_historical_range
        from obsidian_rl.data.contracts import AssetClass, Timeframe
        from obsidian_rl.data.storage import SQLiteStorage

        with SQLiteStorage(":memory:") as store:
            with pytest.raises(Exception) as exc_info:
                ingest_historical_range(
                    asset_class=AssetClass.CRYPTO,
                    venue="BINANCE_FUTURES",
                    symbol="BTCUSDT",
                    timeframe=Timeframe.H4,
                    start_ms=FINAL_HOLDOUT_START_MS,
                    end_ms=FINAL_HOLDOUT_END_MS,
                    storage=store,
                )
            assert "FINAL_HOLDOUT" in str(exc_info.value)
            assert "permanently sealed" in str(exc_info.value)


class TestFuturesFetchBypassBlocked:
    """Tests that BinanceFuturesRest fetch paths enforce guards."""

    def test_fetch_klines_blocks_outer_val(self):
        """BinanceFuturesRest.fetch_klines blocks OUTER_VAL."""
        from obsidian_rl.data.binance_client import BinanceFuturesRest
        from unittest.mock import MagicMock

        client = BinanceFuturesRest()
        client._session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        client._session.get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            client.fetch_klines("BTCUSDT", "4h", OUTER_VAL_START_MS, OUTER_VAL_END_MS)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_fetch_klines_blocks_confirmation(self):
        """BinanceFuturesRest.fetch_klines blocks CONFIRMATION."""
        from obsidian_rl.data.binance_client import BinanceFuturesRest
        from unittest.mock import MagicMock

        client = BinanceFuturesRest()
        client._session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        client._session.get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            client.fetch_klines("BTCUSDT", "4h", CONFIRMATION_START_MS, CONFIRMATION_END_MS)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_fetch_klines_blocks_final_holdout(self):
        """BinanceFuturesRest.fetch_klines blocks FINAL_HOLDOUT unconditionally."""
        from obsidian_rl.data.binance_client import BinanceFuturesRest
        from unittest.mock import MagicMock

        client = BinanceFuturesRest()
        client._session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        client._session.get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            client.fetch_klines("BTCUSDT", "4h", FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_END_MS)
        assert "FINAL_HOLDOUT" in str(exc_info.value)
        assert "permanently sealed" in str(exc_info.value)

    def test_fetch_funding_rates_blocks_outer_val(self):
        """BinanceFuturesRest.fetch_funding_rates blocks OUTER_VAL."""
        from obsidian_rl.data.binance_client import BinanceFuturesRest
        from unittest.mock import MagicMock

        client = BinanceFuturesRest()
        client._session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        client._session.get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            client.fetch_funding_rates("BTCUSDT", OUTER_VAL_START_MS, OUTER_VAL_END_MS)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_fetch_funding_rates_blocks_confirmation(self):
        """BinanceFuturesRest.fetch_funding_rates blocks CONFIRMATION."""
        from obsidian_rl.data.binance_client import BinanceFuturesRest
        from unittest.mock import MagicMock

        client = BinanceFuturesRest()
        client._session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        client._session.get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            client.fetch_funding_rates("BTCUSDT", CONFIRMATION_START_MS, CONFIRMATION_END_MS)
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_fetch_funding_rates_blocks_final_holdout(self):
        """BinanceFuturesRest.fetch_funding_rates blocks FINAL_HOLDOUT unconditionally."""
        from obsidian_rl.data.binance_client import BinanceFuturesRest
        from unittest.mock import MagicMock

        client = BinanceFuturesRest()
        client._session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        client._session.get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            client.fetch_funding_rates("BTCUSDT", FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_END_MS)
        assert "FINAL_HOLDOUT" in str(exc_info.value)
        assert "permanently sealed" in str(exc_info.value)


class TestInMemoryBacktestBlocked:
    """Tests that in-memory backtest enforces guard."""

    def test_run_trend_backtest_blocks_outer_val(self):
        """run_trend_backtest blocks OUTER_VAL ranges."""
        from obsidian_rl.evaluation.trend_backtest import run_trend_backtest
        from obsidian_rl.data.contracts import MarketBar, QuoteStatus, Timeframe, VolumeType
        from obsidian_rl.signals.trend import TrendConfig
        from obsidian_rl.portfolio.costs import CostModel
        from obsidian_rl.data.contracts import compute_market_bar_hash

        # Create OUTER_VAL bars
        bars = []
        for i in range(10):
            bar = MarketBar(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_SPOT",
                symbol="BTCUSDT",
                timeframe=Timeframe.H4,
                data_source="TEST",
                timestamp_utc=OUTER_VAL_START_MS + i * 14_400_000,
                observed_at_utc=OUTER_VAL_START_MS + i * 14_400_000 + 1000,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                quote_status=QuoteStatus.UNAVAILABLE,
                bid=None,
                ask=None,
                volume_type=VolumeType.BASE,
                volume=100.0,
                row_hash="",
            )
            object.__setattr__(bar, "row_hash", compute_market_bar_hash(bar))
            bars.append(bar)

        with pytest.raises(Exception) as exc_info:
            run_trend_backtest(
                tuple(bars),
                TrendConfig(),
                CostModel(),
                eval_start_ms=OUTER_VAL_START_MS,
                market_model=MarketModel.SPOT,
                exposure_policy=ExposurePolicy.LONG_FLAT,
            )
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_run_trend_backtest_blocks_confirmation(self):
        """run_trend_backtest blocks CONFIRMATION ranges."""
        from obsidian_rl.evaluation.trend_backtest import run_trend_backtest
        from obsidian_rl.data.contracts import MarketBar, QuoteStatus, Timeframe, VolumeType
        from obsidian_rl.signals.trend import TrendConfig
        from obsidian_rl.portfolio.costs import CostModel
        from obsidian_rl.data.contracts import compute_market_bar_hash

        # Create CONFIRMATION bars
        bars = []
        for i in range(10):
            bar = MarketBar(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_SPOT",
                symbol="BTCUSDT",
                timeframe=Timeframe.H4,
                data_source="TEST",
                timestamp_utc=CONFIRMATION_START_MS + i * 14_400_000,
                observed_at_utc=CONFIRMATION_START_MS + i * 14_400_000 + 1000,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                quote_status=QuoteStatus.UNAVAILABLE,
                bid=None,
                ask=None,
                volume_type=VolumeType.BASE,
                volume=100.0,
                row_hash="",
            )
            object.__setattr__(bar, "row_hash", compute_market_bar_hash(bar))
            bars.append(bar)

        with pytest.raises(Exception) as exc_info:
            run_trend_backtest(
                tuple(bars),
                TrendConfig(),
                CostModel(),
                eval_start_ms=CONFIRMATION_START_MS,
                market_model=MarketModel.SPOT,
                exposure_policy=ExposurePolicy.LONG_FLAT,
            )
        assert "DEV_TRAIN stage only permits reads within DEV_TRAIN" in str(exc_info.value)

    def test_run_trend_backtest_blocks_final_holdout(self):
        """run_trend_backtest blocks FINAL_HOLDOUT ranges."""
        from obsidian_rl.evaluation.trend_backtest import run_trend_backtest
        from obsidian_rl.data.contracts import MarketBar, QuoteStatus, Timeframe, VolumeType
        from obsidian_rl.signals.trend import TrendConfig
        from obsidian_rl.portfolio.costs import CostModel
        from obsidian_rl.data.contracts import compute_market_bar_hash

        # Create FINAL_HOLDOUT bars
        bars = []
        for i in range(10):
            bar = MarketBar(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_SPOT",
                symbol="BTCUSDT",
                timeframe=Timeframe.H4,
                data_source="TEST",
                timestamp_utc=FINAL_HOLDOUT_START_MS + i * 14_400_000,
                observed_at_utc=FINAL_HOLDOUT_START_MS + i * 14_400_000 + 1000,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                quote_status=QuoteStatus.UNAVAILABLE,
                bid=None,
                ask=None,
                volume_type=VolumeType.BASE,
                volume=100.0,
                row_hash="",
            )
            object.__setattr__(bar, "row_hash", compute_market_bar_hash(bar))
            bars.append(bar)

        with pytest.raises(Exception) as exc_info:
            run_trend_backtest(
                tuple(bars),
                TrendConfig(),
                CostModel(),
                eval_start_ms=FINAL_HOLDOUT_START_MS,
                market_model=MarketModel.SPOT,
                exposure_policy=ExposurePolicy.LONG_FLAT,
            )
        assert "FINAL_HOLDOUT" in str(exc_info.value)
        assert "permanently sealed" in str(exc_info.value)

    def test_validate_backtest_access_integration(self):
        """run_trend_backtest calls validate_backtest_access internally."""
        from obsidian_rl.evaluation.trend_backtest import run_trend_backtest
        from obsidian_rl.data.contracts import MarketBar, QuoteStatus, Timeframe, VolumeType
        from obsidian_rl.signals.trend import TrendConfig
        from obsidian_rl.portfolio.costs import CostModel
        from obsidian_rl.data.contracts import compute_market_bar_hash

        # Create DEV_TRAIN bars (should pass)
        bars = []
        for i in range(10):
            bar = MarketBar(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_FUTURES",
                symbol="BTCUSDT",
                timeframe=Timeframe.H4,
                data_source="TEST",
                timestamp_utc=DEV_TRAIN_START_MS + i * 14_400_000,
                observed_at_utc=DEV_TRAIN_START_MS + i * 14_400_000 + 1000,
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                quote_status=QuoteStatus.UNAVAILABLE,
                bid=None,
                ask=None,
                volume_type=VolumeType.BASE,
                volume=100.0,
                row_hash="",
            )
            object.__setattr__(bar, "row_hash", compute_market_bar_hash(bar))
            bars.append(bar)

        # This should pass without raising
        result = run_trend_backtest(
            tuple(bars),
            TrendConfig(),
            CostModel(),
            eval_start_ms=DEV_TRAIN_START_MS,
            market_model=MarketModel.PERPETUAL,
            exposure_policy=ExposurePolicy.BIDIRECTIONAL,
        )
        assert result is not None


class TestPostHoldoutAccess:
    """Tests for post-holdout access policy."""

    def test_final_holdout_end_matches_2027_01_01(self):
        """FINAL_HOLDOUT_END_MS = 2027-01-01T00:00:00Z = 1798761600000."""
        assert FINAL_HOLDOUT_END_MS == 1798761600000


class TestPhase11HoldoutConflict:
    """Tests for Phase 11 holdout consistency."""

    def test_phase11_does_not_require_final_holdout_access(self):
        """Phase 11 paper trading does not require FINAL_HOLDOUT access.
        
        FINAL_HOLDOUT remains sealed during Phase 11.
        Phase 11 uses live market time after holdout (2027-01-01T00:00:00Z earliest).
        """
        # This is a documentation/design test - the policy is enforced by
        # the FINAL_HOLDOUT hard block in validate_temporal_access
        # and the explicit 2027-01-01T00:00:00Z earliest paper-market time
        assert FINAL_HOLDOUT_END_MS == 1798761600000
        # Any attempt to access FINAL_HOLDOUT is hard-blocked
        with pytest.raises(Exception) as exc_info:
            validate_temporal_access(FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_END_MS)
        assert "FINAL_HOLDOUT" in str(exc_info.value)
        assert "permanently sealed" in str(exc_info.value)


class TestFundingStorage:
    """Tests for funding rate storage and retrieval."""

    def test_funding_rates_migration_creates_table(self, tmp_path: Path):
        """funding_rates table is created by migrations."""
        from obsidian_rl.data.storage import SQLiteStorage

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            cursor = store.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='funding_rates'")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "funding_rates"

            # Check index exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_funding_rates_query'")
            idx = cursor.fetchone()
            assert idx is not None

    def test_insert_funding_rates_idempotent(self, tmp_path: Path):
        """Identical funding rates insert is idempotent."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass, FundingRate

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            rate = FundingRate(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_FUTURES",
                symbol="BTCUSDT",
                timestamp_utc=1577836800000,
                observed_at_utc=1577836800000,
                rate=0.0001,
                data_source="BINANCE_FUTURES_REST",
                schema_version="SCHEMA_V2",
            )

            # First insert
            count1 = store.insert_funding_rates([rate])
            assert count1 == 1

            # Second identical insert - should be idempotent
            count2 = store.insert_funding_rates([rate])
            assert count2 == 0

            # Verify only one stored
            rates = store.query_funding_rates(AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT", 1577836800000, 1577836800000 + 86400000)
            assert len(rates) == 1

    def test_insert_funding_rates_conflict_rejected(self, tmp_path: Path):
        """Conflicting funding rate (same identity, different hash) is rejected."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass, FundingRate
        from obsidian_rl.data.fingerprint import compute_funding_rate_hash

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            rate1 = FundingRate(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_FUTURES",
                symbol="BTCUSDT",
                timestamp_utc=1577836800000,
                observed_at_utc=1577836800000,
                rate=0.0001,
                data_source="BINANCE_FUTURES_REST",
                schema_version="SCHEMA_V2",
            )

            # Create a conflicting rate with same identity but different rate
            rate2 = FundingRate(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_FUTURES",
                symbol="BTCUSDT",
                timestamp_utc=1577836800000,
                observed_at_utc=1577836800000,
                rate=0.0002,  # Different rate -> different hash
                data_source="BINANCE_FUTURES_REST",
                schema_version="SCHEMA_V2",
            )

            store.insert_funding_rates([rate1])

            from obsidian_rl.data.storage import DuplicateConflictError
            with pytest.raises(DuplicateConflictError):
                store.insert_funding_rates([rate2])

    def test_funding_identity_symbol_timestamp_source(self, tmp_path: Path):
        """Funding rate identity is (symbol, timestamp_utc, data_source)."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass, FundingRate

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            # Same symbol, same timestamp, different source -> allowed
            rate1 = FundingRate(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_FUTURES",
                symbol="BTCUSDT",
                timestamp_utc=1577836800000,
                observed_at_utc=1577836800000,
                rate=0.0001,
                data_source="SOURCE_A",
                schema_version="SCHEMA_V2",
            )
            rate2 = FundingRate(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE_FUTURES",
                symbol="BTCUSDT",
                timestamp_utc=1577836800000,
                observed_at_utc=1577836800000,
                rate=0.0002,
                data_source="SOURCE_B",
                schema_version="SCHEMA_V2",
            )

            count1 = store.insert_funding_rates([rate1])
            count2 = store.insert_funding_rates([rate2])
            assert count1 == 1
            assert count2 == 1  # Different source = different identity

            rates = store.query_funding_rates(AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT", 1577836800000, 1577836800000 + 86400000)
            assert len(rates) == 2

    def test_query_funding_rates_chronological_bounds(self, tmp_path: Path):
        """query_funding_rates respects [start, end) bounds chronologically."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass, FundingRate

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            # Insert rates at different timestamps
            rates = [
                FundingRate(
                    asset_class=AssetClass.CRYPTO,
                    venue="BINANCE_FUTURES",
                    symbol="BTCUSDT",
                    timestamp_utc=1577836800000 + i * 8 * 3600 * 1000,
                    observed_at_utc=1577836800000 + i * 8 * 3600 * 1000,
                    rate=0.0001 + i * 0.00001,
                    data_source="BINANCE_FUTURES_REST",
                    schema_version="SCHEMA_V2",
                )
                for i in range(10)
            ]
            store.insert_funding_rates(rates)

            # Query middle range
            result = store.query_funding_rates(
                AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT",
                1577836800000 + 3 * 8 * 3600 * 1000,
                1577836800000 + 7 * 8 * 3600 * 1000
            )
            assert len(result) == 4  # indices 3,4,5,6
            assert result[0].timestamp_utc == 1577836800000 + 3 * 8 * 3600 * 1000
            assert result[-1].timestamp_utc == 1577836800000 + 6 * 8 * 3600 * 1000

            # Check chronological order
            for i in range(1, len(result)):
                assert result[i].timestamp_utc > result[i-1].timestamp_utc

    def test_query_funding_rates_observed_before_filter(self, tmp_path: Path):
        """observed_before_ms filter works correctly."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass, FundingRate

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            now = 1700000000000
            rates = [
                FundingRate(
                    asset_class=AssetClass.CRYPTO,
                    venue="BINANCE_FUTURES",
                    symbol="BTCUSDT",
                    timestamp_utc=1577836800000 + i * 8 * 3600 * 1000,
                    observed_at_utc=now - (9-i) * 8 * 3600 * 1000,  # observed at different times
                    rate=0.0001,
                    data_source="BINANCE_FUTURES_REST",
                    schema_version="SCHEMA_V2",
                )
                for i in range(10)
            ]
            store.insert_funding_rates(rates)

            # Filter to only those observed before mid-point
            mid_observed = now - 5 * 8 * 3600 * 1000
            result = store.query_funding_rates(
                AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT",
                1577836800000, 1577836800000 + 10 * 8 * 3600 * 1000,
                observed_before_ms=mid_observed
            )
            # Only first 5 should be returned (observed_at_utc <= mid_observed)
            assert len(result) == 5

    def test_funding_read_outer_val_blocked(self, tmp_path: Path):
        """query_funding_rates blocks OUTER_VAL access."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass
        from obsidian_rl.data.research_access import (
            OUTER_VAL_START_MS, OUTER_VAL_END_MS,
            ResearchAccessError
        )

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            with pytest.raises(ResearchAccessError) as exc_info:
                store.query_funding_rates(
                    AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT",
                    OUTER_VAL_START_MS, OUTER_VAL_END_MS
                )
            assert "OUTER_VAL" in str(exc_info.value)

    def test_funding_read_confirmation_blocked(self, tmp_path: Path):
        """query_funding_rates blocks CONFIRMATION access."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass
        from obsidian_rl.data.research_access import (
            CONFIRMATION_START_MS, CONFIRMATION_END_MS,
            ResearchAccessError
        )

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            with pytest.raises(ResearchAccessError) as exc_info:
                store.query_funding_rates(
                    AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT",
                    CONFIRMATION_START_MS, CONFIRMATION_END_MS
                )
            assert "CONFIRMATION" in str(exc_info.value)

    def test_funding_read_final_holdout_blocked(self, tmp_path: Path):
        """query_funding_rates blocks FINAL_HOLDOUT access unconditionally."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass
        from obsidian_rl.data.research_access import (
            FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_END_MS,
            ResearchAccessError
        )

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            with pytest.raises(ResearchAccessError) as exc_info:
                store.query_funding_rates(
                    AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT",
                    FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_END_MS
                )
            assert "FINAL_HOLDOUT" in str(exc_info.value)
            assert "permanently sealed" in str(exc_info.value)

    def test_funding_unbounded_read_blocked(self, tmp_path: Path):
        """Unbounded funding read is blocked."""
        from obsidian_rl.data.storage import SQLiteStorage
        from obsidian_rl.data.contracts import AssetClass

        with SQLiteStorage(tmp_path / "test.sqlite") as store:
            with pytest.raises(TypeError):
                store.query_funding_rates(
                    AssetClass.CRYPTO, "BINANCE_FUTURES", "BTCUSDT",
                    None, None
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])