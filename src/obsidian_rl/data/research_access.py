"""Fail-closed Cycle 2 Research Data Access Guard.

This module enforces the frozen experimental windows for Cycle 02 research
at the data access layer. All reads/ingestion/fetches/backtests must pass
through this gate before accessing market data.

Windows (half-open UTC, immutable):
- DEV_TRAIN:       [2020-01-01T00:00:00Z, 2025-07-01T00:00:00Z)
- OUTER_VAL:       [2025-07-01T00:00:00Z, 2026-03-01T00:00:00Z)
- CONFIRMATION:    [2026-03-01T00:00:00Z, 2026-07-01T00:00:00Z)
- FINAL_HOLDOUT:   [2026-07-01T00:00:00Z, 2027-01-01T00:00:00Z)

Current allowed stage: DEV_TRAIN only (enforced by STAGE constant).

Product model (from CYCLE_02_EXPERIMENTAL_WINDOWS.md §4):
- Binance Spot -> MarketModel.SPOT
- Binance USD-M Perpetual -> MarketModel.PERPETUAL

SPOT + BIDIRECTIONAL remains rejected (per existing trend_backtest.py logic).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from obsidian_rl.data.contracts import AssetClass
from obsidian_rl.portfolio.engine import MarketModel, ExposurePolicy


# Frozen window boundaries (milliseconds since Unix epoch, UTC)
# Half-open intervals: [start, end)
# Explicit literal values derived from frozen UTC datetimes to avoid any runtime derivation errors
DEV_TRAIN_START_MS = 1577836800000      # 2020-01-01T00:00:00Z
DEV_TRAIN_END_MS = 1751328000000        # 2025-07-01T00:00:00Z
OUTER_VAL_START_MS = 1751328000000      # 2025-07-01T00:00:00Z
OUTER_VAL_END_MS = 1772323200000        # 2026-03-01T00:00:00Z
CONFIRMATION_START_MS = 1772323200000   # 2026-03-01T00:00:00Z
CONFIRMATION_END_MS = 1782864000000     # 2026-07-01T00:00:00Z
FINAL_HOLDOUT_START_MS = 1782864000000  # 2026-07-01T00:00:00Z
FINAL_HOLDOUT_END_MS = 1798761600000    # 2027-01-01T00:00:00Z


class ResearchStage(Enum):
    """Current allowed research stage (changes require governance/code change)."""
    DEV_TRAIN = "DEV_TRAIN"
    OUTER_VAL = "OUTER_VAL"
    CONFIRMATION = "CONFIRMATION"


# Current stage is hardcoded; changing it requires a committed governance/code change.
CURRENT_STAGE = ResearchStage.DEV_TRAIN


class ResearchAccessError(RuntimeError):
    """Base error for research access violations."""
    pass


class ProductMismatchError(ResearchAccessError):
    """Raised when venue/product doesn't match requested market model."""
    pass


@dataclass(frozen=True)
class ProductDeclaration:
    """Validated product declaration for an experiment."""
    asset_class: AssetClass
    venue: str
    market_model: MarketModel
    exposure_policy: ExposurePolicy


# AssetClass -> expected venue mapping (from historical_dataset.py _get_venue)
ASSET_CLASS_TO_VENUE = {
    AssetClass.CRYPTO: ["BINANCE_SPOT", "BINANCE_FUTURES"],
    AssetClass.FOREX: ["OANDA_PRACTICE"],
}

# Venue -> MarketModel mapping
VENUE_TO_MARKET_MODEL = {
    "BINANCE_SPOT": MarketModel.SPOT,
    "BINANCE_FUTURES": MarketModel.PERPETUAL,
    "OANDA_PRACTICE": MarketModel.FOREX_MARGIN,
}


def _validate_bounds(start_ms: int, end_ms: int) -> None:
    """Validate request bounds are well-formed."""
    if isinstance(start_ms, bool) or not isinstance(start_ms, int):
        raise ResearchAccessError(f"start_ms must be integer ms UTC, got {type(start_ms).__name__}")
    if isinstance(end_ms, bool) or not isinstance(end_ms, int):
        raise ResearchAccessError(f"end_ms must be integer ms UTC, got {type(end_ms).__name__}")
    if start_ms < 0:
        raise ResearchAccessError("start_ms cannot be negative")
    if end_ms < 0:
        raise ResearchAccessError("end_ms cannot be negative")
    if start_ms >= end_ms:
        raise ResearchAccessError(f"start_ms ({start_ms}) must be < end_ms ({end_ms})")


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Check if two half-open intervals [a_start, a_end) and [b_start, b_end) overlap."""
    return a_start < b_end and b_start < a_end


def _is_within_dev_train(start_ms: int, end_ms: int) -> bool:
    """Check if range is entirely within DEV_TRAIN window (including causal warm-up before start)."""
    # Allow causal warm-up before DEV_TRAIN start, as long as range ends within DEV_TRAIN
    return end_ms <= DEV_TRAIN_END_MS


def _is_within_outer_val(start_ms: int, end_ms: int) -> bool:
    """Check if range intersects OUTER_VAL window."""
    return _overlaps(start_ms, end_ms, OUTER_VAL_START_MS, OUTER_VAL_END_MS)


def _is_within_confirmation(start_ms: int, end_ms: int) -> bool:
    """Check if range intersects CONFIRMATION window."""
    return _overlaps(start_ms, end_ms, CONFIRMATION_START_MS, CONFIRMATION_END_MS)


def _is_within_final_holdout(start_ms: int, end_ms: int) -> bool:
    """Check if range intersects FINAL_HOLDOUT window."""
    return _overlaps(start_ms, end_ms, FINAL_HOLDOUT_START_MS, FINAL_HOLDOUT_END_MS)


def validate_temporal_access(start_ms: int, end_ms: int) -> None:
    """Fail-closed temporal access validation for Cycle 2 research windows.
    
    During DEV_TRAIN stage:
    - Causal warm-up + DEV_TRAIN reads allowed (end <= DEV_TRAIN_END_MS)
    - Any OUTER_VAL access rejected
    - Any CONFIRMATION access rejected
    - Any FINAL_HOLDOUT overlap rejected unconditionally (all stages)
    
    Args:
        start_ms: Start timestamp in milliseconds (UTC)
        end_ms: End timestamp in milliseconds (UTC)
    
    Raises:
        ResearchAccessError: If access violates temporal firewall
    """
    _validate_bounds(start_ms, end_ms)
    
    # FINAL_HOLDOUT is permanently sealed regardless of stage
    if _is_within_final_holdout(start_ms, end_ms):
        raise ResearchAccessError(
            f"Access range [{start_ms}, {end_ms}) overlaps FINAL_HOLDOUT "
            f"[{FINAL_HOLDOUT_START_MS}, {FINAL_HOLDOUT_END_MS}) — permanently sealed for Cycle 02"
        )
    
    # Current stage enforcement
    if CURRENT_STAGE == ResearchStage.DEV_TRAIN:
        # Allow reads entirely within DEV_TRAIN (including warm-up before DEV_TRAIN_START)
        if _is_within_dev_train(start_ms, end_ms):
            return
        
        # Block OUTER_VAL
        if _is_within_outer_val(start_ms, end_ms):
            raise ResearchAccessError(
                f"Access range [{start_ms}, {end_ms}) overlaps OUTER_VAL "
                f"[{OUTER_VAL_START_MS}, {OUTER_VAL_END_MS}) — DEV_TRAIN stage only permits reads "
                f"within DEV_TRAIN [{DEV_TRAIN_START_MS}, {DEV_TRAIN_END_MS})"
            )
        
        # Block CONFIRMATION
        if _is_within_confirmation(start_ms, end_ms):
            raise ResearchAccessError(
                f"Access range [{start_ms}, {end_ms}) overlaps CONFIRMATION "
                f"[{CONFIRMATION_START_MS}, {CONFIRMATION_END_MS}) — DEV_TRAIN stage only permits reads "
                f"within DEV_TRAIN [{DEV_TRAIN_START_MS}, {DEV_TRAIN_END_MS})"
            )
        
        # Block anything beyond DEV_TRAIN (post-holdout, etc.)
        raise ResearchAccessError(
            f"Access range [{start_ms}, {end_ms}) exceeds DEV_TRAIN window "
            f"[{DEV_TRAIN_START_MS}, {DEV_TRAIN_END_MS}) — current stage: DEV_TRAIN only"
        )
    
    # Other stages not yet implemented (require governance/code change)
    raise ResearchAccessError(f"Stage {CURRENT_STAGE.value} not yet implemented — requires governance/code change")


def validate_product_consistency(
    asset_class: AssetClass,
    venue: str,
    requested_market_model: MarketModel,
    requested_exposure_policy: ExposurePolicy
) -> ProductDeclaration:
    """Validate that the requested market model matches the venue/product.
    
    Args:
        asset_class: The asset class of the dataset
        venue: The data venue (e.g., "BINANCE_SPOT", "BINANCE_FUTURES", "OANDA_PRACTICE")
        requested_market_model: The MarketModel requested for evaluation
        requested_exposure_policy: The ExposurePolicy requested for evaluation
    
    Returns:
        ProductDeclaration with validated venue and market model
    
    Raises:
        ProductMismatchError: If venue/product doesn't match requested model
    """
    # Derive expected venue from asset class
    expected_venues = ASSET_CLASS_TO_VENUE.get(asset_class)
    if expected_venues is None:
        raise ProductMismatchError(f"Unknown asset class: {asset_class}")
    
    if venue not in expected_venues:
        raise ProductMismatchError(
            f"Venue '{venue}' not in expected venues {expected_venues} "
            f"for asset class {asset_class.value}"
        )
    
    # Derive expected market model from venue
    expected_model = VENUE_TO_MARKET_MODEL.get(venue)
    if expected_model is not None and requested_market_model != expected_model:
        raise ProductMismatchError(
            f"Venue '{venue}' is a {expected_model.value} product; "
            f"cannot evaluate as {requested_market_model.value}"
        )
    
    # SPOT + BIDIRECTIONAL is rejected by existing logic; enforce here too
    if requested_market_model == MarketModel.SPOT and requested_exposure_policy == ExposurePolicy.BIDIRECTIONAL:
        raise ProductMismatchError("SPOT market model cannot be combined with BIDIRECTIONAL exposure policy")
    
    return ProductDeclaration(
        asset_class=asset_class,
        venue=venue,
        market_model=requested_market_model,
        exposure_policy=requested_exposure_policy,
    )


def validate_backtest_access(
    bars_start_ms: int,
    bars_end_ms: int,
    eval_start_ms: int,
    asset_class: AssetClass,
    venue: str,
    market_model: MarketModel,
    exposure_policy: ExposurePolicy
) -> None:
    """Validate in-memory backtest access against temporal and product guards.
    
    Args:
        bars_start_ms: Start timestamp of loaded bars
        bars_end_ms: End timestamp of loaded bars
        eval_start_ms: Evaluation start timestamp (scoring boundary)
        asset_class: Asset class of the dataset
        venue: Data venue
        market_model: Requested market model for evaluation
        exposure_policy: Requested exposure policy for evaluation
    
    Raises:
        ResearchAccessError: If temporal access violates firewall
        ProductMismatchError: If product/model mismatch
    """
    # Validate temporal access for the full bars range
    validate_temporal_access(bars_start_ms, bars_end_ms)
    
    # Validate product consistency
    validate_product_consistency(asset_class, venue, market_model, exposure_policy)
    
    # eval_start_ms must be within bars range
    if not (bars_start_ms <= eval_start_ms < bars_end_ms):
        raise ResearchAccessError(
            f"eval_start_ms ({eval_start_ms}) must be within bars range "
            f"[{bars_start_ms}, {bars_end_ms})"
        )


__all__ = [
    "ResearchAccessError",
    "ProductMismatchError",
    "ProductDeclaration",
    "ResearchStage",
    "CURRENT_STAGE",
    "DEV_TRAIN_START_MS",
    "DEV_TRAIN_END_MS",
    "OUTER_VAL_START_MS",
    "OUTER_VAL_END_MS",
    "CONFIRMATION_START_MS",
    "CONFIRMATION_END_MS",
    "FINAL_HOLDOUT_START_MS",
    "FINAL_HOLDOUT_END_MS",
    "validate_temporal_access",
    "validate_product_consistency",
    "validate_backtest_access",
    "ASSET_CLASS_TO_VENUE",
    "VENUE_TO_MARKET_MODEL",
]