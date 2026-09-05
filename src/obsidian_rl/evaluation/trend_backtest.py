"""Cross-Market Trend Backtesting Framework."""

import hashlib
import json
import math
from dataclasses import dataclass

from obsidian_rl.data.contracts import AssetClass, FundingRate, MarketBar
from obsidian_rl.data.outages import OutageRegistry
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import (
    ExposurePolicy,
    MarketModel,
    PortfolioConfig,
    PortfolioEngine,
)
from obsidian_rl.signals.trend import InsufficientHistoryError, TrendConfig, calculate_trend_signal, DataQualityError
from obsidian_rl.data.research_access import validate_backtest_access, validate_product_consistency


@dataclass(frozen=True)
class TrendBacktestResult:
    starting_equity: float
    ending_equity: float
    net_return: float
    gross_return: float
    total_costs: float
    trade_count: int
    turnover: float
    winning_trades: int
    losing_trades: int
    hit_rate: float
    exposure_percentage: float
    annualized_sharpe: float
    maximum_drawdown: float
    first_timestamp_utc: int
    last_timestamp_utc: int
    input_dataset_digest: str
    trend_config_identity: str
    market_model: str
    exposure_policy: str
    first_decision_ts: int | None
    first_submitted_target: float | None
    first_exec_ts: int | None
    first_exec_price: float | None
    liq_ts: int | None
    liq_price: float | None
    backtest_identity: str
    # Separate cost breakdowns
    total_trading_costs: float = 0.0  # fee + spread + slippage (includes terminal liquidation)
    total_funding: float = 0.0        # net funding paid (positive = paid)


@dataclass(frozen=True)
class TrendBacktestReport:
    strategy: TrendBacktestResult
    baseline_flat: TrendBacktestResult
    baseline_long: TrendBacktestResult


def _hash_dataset(bars: tuple[MarketBar, ...]) -> str:
    h = hashlib.sha256()
    for b in bars:
        h.update(f"{b.timestamp_utc}:{b.close}:{b.row_hash}".encode())
    return h.hexdigest()


def _get_exec_price(
    asset_class: AssetClass,
    bar: MarketBar,
    current_exposure: float,
    target_exposure: float,
) -> float:
    """Return the correct execution price for a given transition."""
    if asset_class == AssetClass.CRYPTO:
        # Crypto uses open price and the configured CostModel
        return bar.open

    # Forex uses bid/ask
    if target_exposure > current_exposure:
        # Buying (FLAT->LONG, SHORT->FLAT, SHORT->LONG) uses ask
        if bar.ask is None:
            raise ValueError(f"Missing ask price for forex execution at {bar.timestamp_utc}")
        return bar.ask
    elif target_exposure < current_exposure:
        # Selling (LONG->FLAT, FLAT->SHORT, LONG->SHORT) uses bid
        if bar.bid is None:
            raise ValueError(f"Missing bid price for forex execution at {bar.timestamp_utc}")
        return bar.bid
    else:
        # No change in exposure; price doesn't matter for trading, but need for MTM
        # We can just return the close or midpoint. Engine needs a price.
        # But if delta is 0, no trade happens. Just return close.
        return bar.close


def _run_single_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    mode: str,
    eval_start_ms: int,
    market_model: MarketModel,
    exposure_policy: ExposurePolicy,
    funding_rates: tuple[FundingRate, ...] = (),
    outage_registry: OutageRegistry | None = None,
    manifest_digest: str | None = None,
) -> TrendBacktestResult:
    """Run a single pass of the backtest logic."""
    if not bars:
        raise ValueError("Empty dataset")

    if market_model == MarketModel.SPOT and exposure_policy == ExposurePolicy.BIDIRECTIONAL:
        raise ValueError("SPOT market model cannot execute BIDIRECTIONAL positions")

    dataset_digest = _hash_dataset(bars)
    config_identity = config.identity
    tf = bars[0].timeframe
    expected_interval = tf.value_ms() if hasattr(tf, "value_ms") else 14400000
    outage_id = outage_registry.identity() if outage_registry is not None else "empty"
    backtest_identity = hashlib.sha256(
        json.dumps(
            {
                "mode": mode,
                "manifest_digest": manifest_digest,
                "runtime_digest": dataset_digest,
                "asset_class": bars[0].asset_class.value,
                "venue": bars[0].venue,
                "symbol": bars[0].symbol,
                "timeframe": tf.value,
                "data_start": bars[0].timestamp_utc,
                "eval_start_ms": eval_start_ms,
                "eval_end_excl_ms": bars[-1].timestamp_utc + expected_interval,
                "config": config_identity,
                "portfolio": {
                    "initial_cash": 10000.0,
                    "max_abs_exposure": 1.0,
                    "allow_short": exposure_policy == ExposurePolicy.BIDIRECTIONAL,
                },
                "cost_model": {
                    "taker_fee": cost_model.taker_fee,
                    "half_spread": cost_model.half_spread,
                    "slippage": cost_model.slippage,
                },
                "execution_timing": "NEXT_BAR_OPEN",
                "terminal_liquidation": "LAST_BAR_CLOSE",
                "market_model": market_model.value,
                "exposure_policy": exposure_policy.value,
                "outage_registry_identity": outage_id,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    asset_class = bars[0].asset_class

    portfolio_config = PortfolioConfig(
        initial_cash=10000.0,
        max_abs_exposure=1.0,
        allow_short=(exposure_policy == ExposurePolicy.BIDIRECTIONAL),
    )
    engine = PortfolioEngine(portfolio_config, cost_model)

    eval_bars = [b for b in bars if b.timestamp_utc >= eval_start_ms]
    if not eval_bars:
        raise ValueError("No bars in evaluation period")

    first_ts = eval_bars[0].timestamp_utc
    last_ts = eval_bars[-1].timestamp_utc

    winning_trades = 0
    losing_trades = 0
    exposure_sum = 0.0
    valid_bars_for_exposure = 0

    log_returns = []
    last_equity = None

    target_exposure = 0.0
    if mode == "long":
        target_exposure = 1.0

    first_decision_ts = None
    first_submitted_target = None
    first_exec_ts = None
    first_exec_price = None

    # Track separate cost components
    total_trading_costs = 0.0
    total_funding_paid = 0.0

    funding_idx = 0

    for i in range(len(bars)):
        bar = bars[i]
        is_eval = bar.timestamp_utc >= eval_start_ms

        if is_eval:
            if last_equity is None:
                last_equity = engine.state.net_equity(bar.open)

            # Apply any funding due exactly at this bar's open timestamp
            while (
                funding_idx < len(funding_rates)
                and funding_rates[funding_idx].timestamp_utc <= bar.timestamp_utc
            ):
                fr = funding_rates[funding_idx]
                if fr.timestamp_utc == bar.timestamp_utc:
                    flow = engine.apply_funding(bar.open, fr.rate)
                    total_funding_paid += -flow  # positive = paid
                funding_idx += 1

            current_exp = engine.state.exposure(bar.open)
            if target_exposure != current_exp:
                exec_px = _get_exec_price(asset_class, bar, current_exp, target_exposure)
                old_realized = engine.state.realized_pnl
                res = engine.rebalance(target_exposure, exec_px)
                new_realized = engine.state.realized_pnl
                delta = new_realized - old_realized
                if res.delta_qty != 0.0:
                    if first_exec_ts is None:
                        first_exec_ts = bar.timestamp_utc
                        first_exec_price = exec_px
                    total_trading_costs += res.total_cost
                    if delta > 0:
                        winning_trades += 1
                    elif delta < 0:
                        losing_trades += 1

            engine.mark_to_market(bar.close)

            eq = engine.state.net_equity(bar.close)
            if last_equity > 0:
                log_returns.append(math.log(eq / last_equity))
            last_equity = eq

            exposure_sum += abs(engine.state.exposure(bar.close))
            valid_bars_for_exposure += 1

        if mode == "strategy":
            history = bars[: i + 1]
            try:
                sig = calculate_trend_signal(
                    history, observed_before_ms=bar.observed_at_utc, config=config
                )
                if sig.direction == "LONG":
                    target_exposure = 1.0
                elif sig.direction == "SHORT":
                    target_exposure = -1.0
                else:
                    target_exposure = 0.0

                if first_decision_ts is None and target_exposure != 0.0:
                    first_decision_ts = bar.timestamp_utc
                    first_submitted_target = target_exposure
            except (InsufficientHistoryError, ValueError, DataQualityError) as e:
                # InsufficientHistoryError -> fallback to FLAT
                # DataQualityError/ValueError -> propagate as ValueError
                if isinstance(e, InsufficientHistoryError):
                    target_exposure = 0.0
                else:
                    if isinstance(e, DataQualityError):
                        raise ValueError(str(e))
                    else:
                        raise

    liq_res = engine.liquidate(bars[-1].close)
    engine.mark_to_market(bars[-1].close)

    liq_ts = bars[-1].timestamp_utc if liq_res.delta_qty != 0.0 else None
    liq_price = bars[-1].close if liq_res.delta_qty != 0.0 else None

    # Include terminal liquidation cost in total_trading_costs (it's a trading cost, not funding)
    total_trading_costs += liq_res.total_cost

    s = engine.state
    net_return = s.net_equity(bars[-1].close) / 10000.0 - 1.0
    total_costs = s.total_costs()
    gross_return = (s.net_equity(bars[-1].close) + total_costs) / 10000.0 - 1.0

    hit_rate = 0.0
    total_closed = winning_trades + losing_trades
    if total_closed > 0:
        hit_rate = winning_trades / total_closed

    mean_log_ret = sum(log_returns) / len(log_returns) if log_returns else 0.0
    var_log_ret = (
        sum((r - mean_log_ret) ** 2 for r in log_returns) / len(log_returns) if log_returns else 0.0
    )
    sharpe = 0.0
    if var_log_ret > 0:
        years_elapsed = (last_ts - first_ts) / (365.25 * 24 * 3600 * 1000)
        bars_per_year_effective = len(log_returns) / years_elapsed if years_elapsed > 0 else 0.0
        sharpe = (mean_log_ret / math.sqrt(var_log_ret)) * math.sqrt(bars_per_year_effective)

    return TrendBacktestResult(
        starting_equity=10000.0,
        ending_equity=s.net_equity(bars[-1].close),
        net_return=net_return,
        gross_return=gross_return,
        total_costs=total_costs,
        trade_count=s.trade_count,
        turnover=s.turnover,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        hit_rate=hit_rate,
        exposure_percentage=(exposure_sum / valid_bars_for_exposure)
        if valid_bars_for_exposure
        else 0.0,
        annualized_sharpe=sharpe,
        maximum_drawdown=engine.state.path_maximum_drawdown_pct,
        first_timestamp_utc=first_ts,
        last_timestamp_utc=last_ts,
        input_dataset_digest=dataset_digest,
        trend_config_identity=config_identity,
        market_model=market_model.value,
        exposure_policy=exposure_policy.value,
        first_decision_ts=first_decision_ts,
        first_exec_ts=first_exec_ts,
        first_submitted_target=first_submitted_target,
        first_exec_price=first_exec_price,
        liq_ts=liq_ts,
        liq_price=liq_price,
        backtest_identity=backtest_identity,
        total_trading_costs=total_trading_costs,
        total_funding=total_funding_paid,
    )


def run_trend_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    eval_start_ms: int,
    market_model: MarketModel,
    exposure_policy: ExposurePolicy,
    funding_rates: tuple[FundingRate, ...] = (),
    outage_registry: OutageRegistry | None = None,
    manifest_digest: str | None = None,
) -> TrendBacktestReport:
    """Run backtests for strategy, flat baseline, and long baseline."""
    if not bars:
        raise ValueError("Cannot run backtest on empty data.")

    # Cycle 2 research temporal + product access guard
    bars_start_ms = bars[0].timestamp_utc
    bars_end_ms = bars[-1].timestamp_utc + 1  # Exclusive end
    validate_backtest_access(
        bars_start_ms=bars_start_ms,
        bars_end_ms=bars_end_ms,
        eval_start_ms=eval_start_ms,
        asset_class=bars[0].asset_class,
        venue=bars[0].venue,
        market_model=market_model,
        exposure_policy=exposure_policy,
    )

    asset = bars[0].asset_class
    venue = bars[0].venue
    symbol = bars[0].symbol
    tf = bars[0].timeframe
    last_ts = -1

    for b in bars:
        if b.asset_class != asset or b.venue != venue or b.symbol != symbol or b.timeframe != tf:
            raise ValueError("Mixed datasets are rejected.")
        if not b.row_hash or len(b.row_hash) != 64:
            raise ValueError("Invalid row hash in dataset.")
        if b.timestamp_utc <= last_ts:
            raise ValueError("Bars are out of order or duplicate.")
        last_ts = b.timestamp_utc

    if asset == AssetClass.FOREX:
        cost_model = CostModel(taker_fee=0.0, half_spread=0.0, slippage=cost_model.slippage)

    res_strategy = _run_single_backtest(
        bars,
        config,
        cost_model,
        "strategy",
        eval_start_ms,
        market_model,
        exposure_policy,
        funding_rates,
        outage_registry,
        manifest_digest,
    )
    res_flat = _run_single_backtest(
        bars,
        config,
        cost_model,
        "flat",
        eval_start_ms,
        market_model,
        exposure_policy,
        funding_rates,
        outage_registry,
        manifest_digest,
    )
    res_long = _run_single_backtest(
        bars,
        config,
        cost_model,
        "long",
        eval_start_ms,
        market_model,
        exposure_policy,
        funding_rates,
        outage_registry,
        manifest_digest,
    )

    return TrendBacktestReport(
        strategy=res_strategy,
        baseline_flat=res_flat,
        baseline_long=res_long,
    )