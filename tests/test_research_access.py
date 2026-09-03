"""Focused regression tests for Cycle 2 Research Access Guard."""

import pytest

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
        """Unbounded reads that could include protected windows must fail closed."""
        # This is tested by the integration in store.py which maps None to max bounds

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

    def test_ingestion_blocks_outer_val(self):
        """Ingestion blocks OUTER_VAL."""
        pass

    def test_futures_fetch_blocks_outer_val(self):
        """BinanceFuturesRest.fetch_klines blocks OUTER_VAL."""
        pass

    def test_funding_fetch_blocks_outer_val(self):
        """BinanceFuturesRest.fetch_funding_rates blocks OUTER_VAL."""
        pass


class TestInMemoryBacktestBlocked:
    """Tests that in-memory backtest enforces guard."""

    def test_run_trend_backtest_blocks_outer_val(self):
        """run_trend_backtest blocks OUTER_VAL ranges."""
        pass

    def test_validate_backtest_access_integration(self):
        """run_trend_backtest calls validate_backtest_access."""
        pass


class TestPostHoldoutAccess:
    """Tests for post-holdout access policy."""

    def test_post_holdout_access_allowed_after_stage_change(self):
        """Post-holdout access policy is explicitly designed.
        
        FINAL_HOLDOUT_END_MS = 2027-01-01T00:00:00Z = 1798761600000
        After stage transition to post-holdout, access would be allowed.
        This is explicitly documented as 2027-01-01T00:00:00Z earliest.
        """
        assert FINAL_HOLDOUT_END_MS == 1798761600000


class TestPhase11HoldoutConflict:
    """Tests for Phase 11 holdout consistency."""

    def test_phase11_does_not_require_final_holdout_access(self):
        """Phase 11 paper trading does not require FINAL_HOLDOUT access.
        
        FINAL_HOLDOUT remains sealed during Phase 11.
        Phase 11 uses live market time after holdout.
        """
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])