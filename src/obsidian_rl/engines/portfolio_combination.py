"""Portfolio Combination Engine.

Combines per-asset, per-engine proposals into target exposures with deterministic
weight normalization, conflict resolution, and exposure bounds.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Final

from obsidian_rl.data.contracts import AssetClass


class EngineType(Enum):
    """Supported engine types in the combination pipeline."""

    TREND = "TREND"
    CARRY = "CARRY"
    MACRO = "MACRO"
    NEWS = "NEWS"
    POSITIONING = "POSITIONING"


@dataclass(frozen=True, slots=True)
class EngineProposal:
    """A single engine's proposal for one asset.

    Attributes:
        engine: The engine that produced this proposal.
        asset_class: Asset class of the target instrument.
        venue: Trading venue identifier.
        symbol: Instrument symbol (e.g., "BTCUSDT", "EUR_USD").
        target_exposure: Desired exposure in [-1.0, +1.0].
        confidence: Confidence weight in [0.0, 1.0].
        timestamp_utc: Proposal generation timestamp (ms since epoch).
        metadata: Optional opaque metadata (not used in combination).
    """

    engine: EngineType
    asset_class: AssetClass
    venue: str
    symbol: str
    target_exposure: float
    confidence: float
    timestamp_utc: int
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.engine, EngineType):
            raise ValueError(f"engine must be EngineType, got {type(self.engine).__name__}")
        if not isinstance(self.asset_class, AssetClass):
            raise ValueError(
                f"asset_class must be AssetClass, got {type(self.asset_class).__name__}"
            )
        if not isinstance(self.venue, str) or not self.venue:
            raise ValueError("venue must be a non-empty string")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if not math.isfinite(self.target_exposure):
            raise ValueError(f"target_exposure must be finite, got {self.target_exposure!r}")
        if not -1.0 <= self.target_exposure <= 1.0:
            raise ValueError(f"target_exposure must be in [-1.0, 1.0], got {self.target_exposure}")
        if not math.isfinite(self.confidence):
            raise ValueError(f"confidence must be finite, got {self.confidence!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if not isinstance(self.timestamp_utc, int) or self.timestamp_utc <= 0:
            raise ValueError(f"timestamp_utc must be a positive int, got {self.timestamp_utc!r}")


@dataclass(frozen=True, slots=True)
class CombinationConfig:
    """Configuration for the PortfolioCombinationEngine.

    Attributes:
        engine_weights: Mapping from EngineType to weight (non-negative, finite).
            Weights are normalized to sum to 1.0 internally.
        max_gross_exposure: Maximum gross exposure across all assets (>= 0).
        max_net_exposure: Maximum net exposure across all assets (>= 0).
        per_asset_exposure_cap: Per-asset absolute exposure cap in (0, 1.0].
    """

    engine_weights: Mapping[EngineType, float]
    max_gross_exposure: float = 1.0
    max_net_exposure: float = 1.0
    per_asset_exposure_cap: float = 1.0

    def __post_init__(self) -> None:
        if not self.engine_weights:
            raise ValueError("engine_weights must not be empty")
        total = 0.0
        for engine, weight in self.engine_weights.items():
            if not isinstance(engine, EngineType):
                raise ValueError(
                    f"engine_weights key must be EngineType, got {type(engine).__name__}"
                )
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise ValueError(
                    f"weight for {engine} must be int or float, got {type(weight).__name__}"
                )
            if not math.isfinite(weight):
                raise ValueError(f"weight for {engine} must be finite, got {weight!r}")
            if weight < 0.0:
                raise ValueError(f"weight for {engine} must be non-negative, got {weight}")
            total += weight
        if total <= 0.0:
            raise ValueError("sum of engine_weights must be positive")
        if not math.isfinite(self.max_gross_exposure) or self.max_gross_exposure < 0.0:
            raise ValueError(
                f"max_gross_exposure must be finite and >= 0, got {self.max_gross_exposure!r}"
            )
        if not math.isfinite(self.max_net_exposure) or self.max_net_exposure < 0.0:
            raise ValueError(
                f"max_net_exposure must be finite and >= 0, got {self.max_net_exposure!r}"
            )
        if not math.isfinite(self.per_asset_exposure_cap) or not (
            0.0 < self.per_asset_exposure_cap <= 1.0
        ):
            raise ValueError(
                f"per_asset_exposure_cap must be finite and in "
                f"(0, 1.0], got {self.per_asset_exposure_cap!r}"
            )

    @property
    def normalized_weights(self) -> dict[EngineType, float]:
        """Return deterministic normalized weights summing to 1.0."""
        total = sum(self.engine_weights.values())
        return {engine: weight / total for engine, weight in self.engine_weights.items()}


@dataclass(frozen=True, slots=True)
class CombinedTarget:
    """Result of combining proposals for a single asset."""

    asset_class: AssetClass
    venue: str
    symbol: str
    target_exposure: float  # in [-1.0, 1.0] after combination and caps
    contributing_engines: tuple[EngineType, ...]
    gross_exposure_contribution: float  # absolute exposure this asset adds
    net_exposure_contribution: float  # signed exposure this asset adds

    def __post_init__(self) -> None:
        import math

        if not math.isfinite(self.target_exposure):
            raise ValueError(f"target_exposure must be finite, got {self.target_exposure!r}")
        if not math.isfinite(self.gross_exposure_contribution):
            raise ValueError(
                f"gross_exposure_contribution must be finite, "
                f"got {self.gross_exposure_contribution!r}"
            )
        if not math.isfinite(self.net_exposure_contribution):
            raise ValueError(
                f"net_exposure_contribution must be finite, got {self.net_exposure_contribution!r}"
            )


@dataclass(frozen=True, slots=True)
class CombinationResult:
    """Full combination result across all assets."""

    targets: tuple[CombinedTarget, ...]
    portfolio_gross_exposure: float
    portfolio_net_exposure: float
    timestamp_utc: int
    config_fingerprint: str

    def get_target(self, symbol: str) -> CombinedTarget | None:
        """Retrieve target for a symbol if present."""
        for t in self.targets:
            if t.symbol == symbol:
                return t
        return None


class PortfolioCombinationEngine:
    """Deterministic multi-engine portfolio combination.

    Pipeline:
    1. Group proposals by (asset_class, venue, symbol).
    2. For each asset, compute weighted average of target_exposure using
       normalized engine weights * proposal confidence.
    3. Clamp per-asset result to [-per_asset_exposure_cap, +per_asset_exposure_cap].
    4. Compute portfolio gross and net exposure.
    5. If portfolio caps exceeded, scale all targets proportionally (preserving signs).
    6. Return deterministic CombinationResult.

    All computations are pure functions of inputs; no internal state is mutated.
    """

    def __init__(self, config: CombinationConfig) -> None:
        self.config = config
        self._norm_weights: Final[dict[EngineType, float]] = config.normalized_weights

    def _fingerprint(self) -> str:
        """Deterministic fingerprint of the combination configuration."""
        import hashlib
        import json

        data = {
            "engine_weights": {e.value: w for e, w in self.config.engine_weights.items()},
            "max_gross_exposure": self.config.max_gross_exposure,
            "max_net_exposure": self.config.max_net_exposure,
            "per_asset_exposure_cap": self.config.per_asset_exposure_cap,
        }
        encoded = json.dumps(data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def combine(self, proposals: Sequence[EngineProposal]) -> CombinationResult:
        """Combine proposals into portfolio targets.

        Args:
            proposals: Sequence of EngineProposal objects. Must not be empty.
                All proposals must have the same timestamp_utc (point-in-time snapshot).

        Returns:
            CombinationResult with per-asset targets and portfolio exposures.

        Raises:
            ValueError: If proposals is empty, timestamps differ, or validation fails.
        """
        if not proposals:
            raise ValueError("proposals must not be empty")

        # Validate all proposals have the same timestamp (point-in-time)
        ts = proposals[0].timestamp_utc
        for p in proposals:
            if p.timestamp_utc != ts:
                raise ValueError("All proposals must have identical timestamp_utc")

        # Group by (asset_class, venue, symbol)
        grouped: dict[tuple[AssetClass, str, str], list[EngineProposal]] = {}
        for p in proposals:
            key = (p.asset_class, p.venue, p.symbol)
            grouped.setdefault(key, []).append(p)

        # Sort keys for deterministic ordering
        sorted_keys = sorted(grouped.keys(), key=lambda k: (k[0].value, k[1], k[2]))

        combined_targets: list[CombinedTarget] = []
        portfolio_gross = 0.0
        portfolio_net = 0.0

        for key in sorted_keys:
            asset_class, venue, symbol = key
            asset_proposals = grouped[key]

            # Weighted average: sum(weight * confidence * target) / sum(weight * confidence)
            numerator = 0.0
            denominator = 0.0
            contributing: list[EngineType] = []

            for prop in asset_proposals:
                w = self._norm_weights.get(prop.engine, 0.0)
                c = prop.confidence
                if w > 0.0 and c > 0.0:
                    numerator += w * c * prop.target_exposure
                    denominator += w * c
                    contributing.append(prop.engine)

            raw_target = numerator / denominator if denominator > 0.0 else 0.0

            # Clamp to per-asset cap
            cap = self.config.per_asset_exposure_cap
            clamped_target = max(-cap, min(cap, raw_target))

            # Track exposures
            gross_contrib = abs(clamped_target)
            net_contrib = clamped_target

            combined_targets.append(
                CombinedTarget(
                    asset_class=asset_class,
                    venue=venue,
                    symbol=symbol,
                    target_exposure=clamped_target,
                    contributing_engines=tuple(sorted(contributing, key=lambda e: e.value)),
                    gross_exposure_contribution=gross_contrib,
                    net_exposure_contribution=net_contrib,
                )
            )
            portfolio_gross += gross_contrib
            portfolio_net += net_contrib

        # Scale if portfolio caps exceeded
        if portfolio_gross > self.config.max_gross_exposure and portfolio_gross > 0.0:
            scale = self.config.max_gross_exposure / portfolio_gross
            combined_targets = [
                replace(t, target_exposure=t.target_exposure * scale) for t in combined_targets
            ]
            portfolio_gross = self.config.max_gross_exposure
            portfolio_net *= scale

        net_abs = abs(portfolio_net)
        if net_abs > self.config.max_net_exposure and net_abs > 0.0:
            scale = self.config.max_net_exposure / net_abs
            combined_targets = [
                replace(t, target_exposure=t.target_exposure * scale) for t in combined_targets
            ]
            portfolio_net *= scale
            portfolio_gross *= scale

        # Final sort for deterministic output
        combined_targets.sort(key=lambda t: (t.asset_class.value, t.venue, t.symbol))

        return CombinationResult(
            targets=tuple(combined_targets),
            portfolio_gross_exposure=portfolio_gross,
            portfolio_net_exposure=portfolio_net,
            timestamp_utc=ts,
            config_fingerprint=self._fingerprint(),
        )
