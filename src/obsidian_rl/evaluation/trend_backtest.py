"""Cross-Market Trend Backtesting Framework."""

import hashlib
import json
import math
from dataclasses import dataclass

from obsidian_rl.data.contracts import AssetClass, MarketBar
from obsidian_rl.data.outages import OutageRegistry
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine
from obsidian_rl.signals.trend import TrendConfig, calculate_trend_signal


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
    backtest_identity: str


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
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
) -> TrendBacktestResult:
    """Run a single pass of the backtest logic."""
    if not bars:
        raise ValueError("Empty dataset")

    dataset_digest = _hash_dataset(bars)
    config_identity = config.identity
    backtest_identity = hashlib.sha256(
        json.dumps(
            {
                "mode": mode,
                "dataset": dataset_digest,
                "config": config_identity,
            }
        ).encode("utf-8")
    ).hexdigest()

    asset_class = bars[0].asset_class

    portfolio_config = PortfolioConfig(initial_cash=10000.0, max_abs_exposure=1.0, allow_short=True)
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

    # Warmup tracking
    # To mimic real conditions, we evaluate trend on bar[t], execute on bar[t+1]
    # In 'strategy' mode, the target remains 0 until we have enough history to get a valid signal

    for i in range(len(bars)):
        bar = bars[i]
        is_eval = bar.timestamp_utc >= eval_start_ms

        if is_eval:
            if last_equity is None:
                last_equity = engine.state.net_equity(bar.open)

            # 1. Execute any pending target from the PREVIOUS bar
            # For bar 0, target is 0 for strategy and flat, 1.0 for long.
            current_exp = engine.state.exposure(bar.open)
            if target_exposure != current_exp:
                exec_px = _get_exec_price(asset_class, bar, current_exp, target_exposure)
                # Before executing, record realized pnl to detect win/loss
                old_realized = engine.state.realized_pnl
                engine.rebalance(target_exposure, exec_px)
                new_realized = engine.state.realized_pnl
                delta = new_realized - old_realized
                # If we closed some position, there was a PNL event
                if delta > 0:
                    winning_trades += 1
                elif delta < 0:
                    losing_trades += 1

            # MTM at close
            engine.mark_to_market(bar.close)

            # Record metrics
            eq = engine.state.net_equity(bar.close)
            if last_equity > 0:
                log_returns.append(math.log(eq / last_equity))
            last_equity = eq

            exposure_sum += abs(engine.state.exposure(bar.close))
            valid_bars_for_exposure += 1

        # 2. Evaluate signal for NEXT bar
        if mode == "strategy":
            # Point in time: only provide history up to current bar, observed_before_ms = current bar's observed_at
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
            except Exception:
                # E.g., InsufficientHistoryError
                target_exposure = 0.0

    # Final liquidation
    engine.liquidate(bars[-1].close)
    engine.mark_to_market(bars[-1].close)

    s = engine.state
    net_return = s.net_equity(bars[-1].close) / 10000.0 - 1.0
    total_costs = s.fees_paid + s.spread_paid + s.slippage_paid
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
        maximum_drawdown=s.drawdown(bars[-1].close),
        first_timestamp_utc=first_ts,
        last_timestamp_utc=last_ts,
        input_dataset_digest=dataset_digest,
        trend_config_identity=config_identity,
        backtest_identity=backtest_identity,
    )


def run_trend_backtest(
    bars: tuple[MarketBar, ...],
    config: TrendConfig,
    cost_model: CostModel,
    outage_registry: OutageRegistry | None = None,
    eval_start_ms: int = 0,
) -> TrendBacktestReport:
    """Run backtests for strategy, flat baseline, and long baseline."""
    if not bars:
        raise ValueError("Cannot run backtest on empty data.")

    # Validate homogeneity
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

    # Crypto requires explicit CostModel check in CLI. Here we just use the one passed.
    # Forex MUST use CostModel(fee_bps=0...) so the engine doesn't double-charge
    if asset == AssetClass.FOREX:
        cost_model = CostModel(taker_fee=0.0, half_spread=0.0, slippage=0.0)

    res_strategy = _run_single_backtest(bars, config, cost_model, "strategy", outage_registry, eval_start_ms)
    res_flat = _run_single_backtest(bars, config, cost_model, "flat", outage_registry, eval_start_ms)
    res_long = _run_single_backtest(bars, config, cost_model, "long", outage_registry, eval_start_ms)

    return TrendBacktestReport(
        strategy=res_strategy,
        baseline_flat=res_flat,
        baseline_long=res_long,
    )
