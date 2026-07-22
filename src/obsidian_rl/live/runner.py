import json
import logging
import time
from typing import Any

from obsidian_rl.config import Settings
from obsidian_rl.data.binance_client import BinanceFuturesRest
from obsidian_rl.data.schema import CANDLE_COLUMNS, interval_to_ms, klines_to_frame
from obsidian_rl.data.store import CandleStore
from obsidian_rl.data.validation import drop_unfinalized, require_valid
from obsidian_rl.evaluation.backtest import DEFAULT_TARGETS
from obsidian_rl.features.schema import schema_fingerprint
from obsidian_rl.ledger.ledger import Ledger
from obsidian_rl.live.paper_trader import BUFFER_SIZE, PaperTrader
from obsidian_rl.live.stream import KlineEvent, kline_events
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig
from obsidian_rl.strategies.base import Strategy
from obsidian_rl.training.registry import get_git_source_state

logger = logging.getLogger(__name__)


class LivePaperRunner:
    def __init__(
        self,
        settings: Settings,
        strategy: Strategy,
        *,
        run_id: str | None = None,
        model_id: str | None = None,
        portfolio_config: PortfolioConfig | None = None,
        cost_model: CostModel | None = None,
        initial_cash: float = 10_000.0,
        allowed_targets: tuple[float, ...] = DEFAULT_TARGETS,
    ) -> None:
        self.settings = settings
        self.store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
        self.ledger = Ledger(settings.ledger_path)
        self.rest = BinanceFuturesRest(settings.fapi_base_url, timeout_s=settings.request_timeout_s)
        self.interval_ms = interval_to_ms(settings.interval)

        pc = portfolio_config or PortfolioConfig(initial_cash=initial_cash)
        cm = cost_model or CostModel()
        fp = schema_fingerprint()
        git_state = get_git_source_state()
        git_commit = git_state.commit
        data_source = f"ws:{settings.symbol}"
        strategy_id = getattr(strategy, "strategy_id", "unknown")

        req_config: dict[str, Any] = {
            "allowed_targets": list(allowed_targets),
            "data_source": data_source,
            "feature_schema": fp,
            "initial_cash": float(pc.initial_cash),
            "interval": settings.interval,
            "max_live_open_lag_ms": int(settings.max_live_open_lag_ms),
            "mode": "live-paper",
            "model_id": model_id,
            "portfolio_config": {
                "allow_short": pc.allow_short,
                "exposure_tolerance": pc.exposure_tolerance,
                "initial_cash": pc.initial_cash,
                "max_abs_exposure": pc.max_abs_exposure,
                "min_trade_notional": pc.min_trade_notional,
            },
            "strategy_id": strategy_id,
            "symbol": settings.symbol,
        }

        if run_id is None:
            run = self.ledger.start_run(
                strategy_id=strategy_id,
                mode="live-paper",
                initial_cash=pc.initial_cash,
                cost_model=cm,
                model_id=model_id,
                config=req_config,
                git_commit=git_commit,
            )
            run_id = run.run_id
            resume = False
        else:
            run_info = self.ledger.get_run(run_id)
            if run_info is None:
                raise ValueError(f"run {run_id} not found in ledger; cannot resume")
            ended_at = run_info["ended_at_ms"]
            closure = self.ledger.get_closure(run_id)
            if (closure is not None) != (ended_at is not None):
                msg = (
                    f"inconsistent closure/ended state for run {run_id}: "
                    f"closure={closure is not None}, ended={ended_at is not None}"
                )
                raise RuntimeError(msg)
            if closure is not None and ended_at is not None:
                raise ValueError(f"run {run_id} is already closed and cannot be resumed")

            # Validate stored cost metadata
            cost_json_str = run_info["cost_model_json"]
            try:
                stored_cm = json.loads(cost_json_str)
            except Exception as exc:
                raise ValueError(f"run {run_id} has malformed cost metadata: {exc}") from exc

            if (
                not stored_cm
                or not isinstance(stored_cm, dict)
                or not all(k in stored_cm for k in ("taker_fee", "half_spread", "slippage"))
            ):
                raise ValueError(f"run {run_id} has empty or incomplete cost metadata")

            # Validate stored config matching requested config
            if run_info["config_json"]:
                try:
                    stored_cfg = json.loads(run_info["config_json"])
                except Exception as exc:
                    raise ValueError(f"run {run_id} has malformed config metadata: {exc}") from exc

                if (
                    ("symbol" in stored_cfg and stored_cfg["symbol"] != settings.symbol)
                    or ("interval" in stored_cfg and stored_cfg["interval"] != settings.interval)
                    or ("strategy_id" in stored_cfg and stored_cfg["strategy_id"] != strategy_id)
                ):
                    raise ValueError(f"resume configuration mismatch for run {run_id}")

            resume = True

        self.run_id = run_id
        self.trader = PaperTrader(
            strategy,
            self.ledger,
            run_id,
            interval=settings.interval,
            portfolio_config=pc,
            cost_model=cm,
            allowed_targets=allowed_targets,
            data_source=data_source,
            max_live_open_lag_ms=settings.max_live_open_lag_ms,
        )
        if resume:
            state = self.ledger.restore_state(run_id)
            candles = self.store.read()
            if state is not None and len(candles):
                self.trader.restore(state, candles, now_ms=int(time.time() * 1000))
            run_info = self.ledger.get_run(run_id)
            ended_at = run_info["ended_at_ms"] if run_info is not None else None
            closure = self.ledger.get_closure(run_id)
            if closure is not None and ended_at is not None:
                raise ValueError(f"run {run_id} is already closed and cannot be resumed")
            logger.info("resuming run %s", run_id)

    # ------------------------------------------------------------------ helpers
    def _check_not_closed(self) -> None:
        run_info = self.ledger.get_run(self.run_id)
        ended_at = run_info["ended_at_ms"] if run_info is not None else None
        closure = self.ledger.get_closure(self.run_id)
        if (closure is not None) != (ended_at is not None):
            msg = (
                f"inconsistent closure/ended state for run {self.run_id}: "
                f"closure={closure is not None}, ended={ended_at is not None}"
            )
            raise RuntimeError(msg)
        if closure is not None and ended_at is not None:
            raise ValueError(f"run {self.run_id} is already closed and cannot be resumed")

    def backfill(self, now_ms: int | None = None, max_open_ms: int | None = None) -> int:
        """Fetch finalized candles between the trader's last candle and now via REST."""
        self._check_not_closed()
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        try:
            last = self.trader.last_finalized_ms
            if last is None:
                start = (
                    now // self.interval_ms
                ) * self.interval_ms - BUFFER_SIZE * self.interval_ms
            else:
                start = last + self.interval_ms
            df = self.rest.fetch_klines(self.settings.symbol, self.settings.interval, start)
            df = drop_unfinalized(df, now)
            if max_open_ms is not None:
                df = df[df["open_time"] < max_open_ms]
            if df.empty:
                return 0
            require_valid(df, self.settings.interval, now_ms=now)
            self.store.write(df, source="fapi:backfill")

            if self.trader.pending is not None:
                expected = self.trader.pending.candle_open_ms + self.interval_ms
                if any(int(row.open_time) >= expected for row in df.itertuples(index=False)):
                    self.trader.expire_pending(
                        "backfilled_over_expected_open",
                        now_ms=now,
                        details={"expected_open_ms": expected},
                    )

            if last is not None:
                first_missing = int(df.iloc[0]["open_time"])
                last_missing = int(df.iloc[-1]["open_time"])
                idempotency_key = f"{self.run_id}:gap:{first_missing}:{last_missing}"
                self.ledger.record_event(
                    run_id=self.run_id,
                    event_type="market_data_gap",
                    event_ts_ms=now,
                    idempotency_key=idempotency_key,
                    details={
                        "first_missing_open_ms": first_missing,
                        "last_missing_open_ms": last_missing,
                        "num_missing_candles": len(df),
                    },
                    created_at_ms=now,
                )

            for row in df.itertuples(index=False):
                candle = {c: getattr(row, c) for c in CANDLE_COLUMNS}
                self.trader.ingest_observation(candle)

            first_open = int(df.iloc[0]["open_time"])
            last_open = int(df.iloc[-1]["open_time"])
            idempotency_key = f"{self.run_id}:backfill_completed:{first_open}:{last_open}"
            self.ledger.record_event(
                run_id=self.run_id,
                event_type="backfill_observation_completed",
                event_ts_ms=now,
                idempotency_key=idempotency_key,
                details={
                    "first_open_ms": first_open,
                    "last_open_ms": last_open,
                    "candles_ingested": len(df),
                },
                created_at_ms=now,
            )
            return len(df)
        except Exception as exc:
            self.ledger.record_failure(
                self.run_id,
                failure_type="runner_failure",
                reason=f"backfill failed: {exc}",
                event_ts_ms=now,
            )
            raise

    def handle_event(self, event: KlineEvent) -> None:
        """Route one websocket kline event through the two-phase protocol with gap safety."""
        self._check_not_closed()
        if event.event_time_ms < event.open_time or event.close_time < event.open_time:
            return

        try:
            last = self.trader.last_finalized_ms
            if last is not None and event.open_time > last + self.interval_ms:
                logger.warning("gap detected before %s; backfilling", event.open_time)
                self.backfill(now_ms=event.event_time_ms, max_open_ms=event.open_time)
                last = self.trader.last_finalized_ms
                if last is not None and event.open_time <= last:
                    return

            if self.trader.pending is not None:
                expected = self.trader.pending.candle_open_ms + self.interval_ms
                if event.open_time > expected:
                    self.trader.expire_pending(
                        "missed_execution_window",
                        now_ms=event.event_time_ms,
                        details={
                            "event_open_time": event.open_time,
                            "expected_open_time": expected,
                        },
                    )
                elif (
                    event.open_time == expected
                    and event.event_time_ms - event.open_time > self.settings.max_live_open_lag_ms
                ):
                    self.trader.expire_pending(
                        "max_live_open_lag_exceeded",
                        now_ms=event.event_time_ms,
                        details={
                            "event_time_ms": event.event_time_ms,
                            "lag_ms": event.event_time_ms - event.open_time,
                            "max_lag_ms": self.settings.max_live_open_lag_ms,
                        },
                    )

            if (
                self.trader.pending is not None
                and event.open_time == self.trader.pending.candle_open_ms + self.interval_ms
            ):
                self.trader.on_next_open(
                    event.open_time,
                    event.open,
                    now_ms=event.event_time_ms,
                    event_time_ms=event.event_time_ms,
                )

            if event.is_closed:
                last = self.trader.last_finalized_ms
                if last is not None and event.open_time <= last:
                    return
                candle = event.to_candle()
                self.store.write(
                    klines_to_frame(
                        [
                            [
                                candle["open_time"],
                                candle["open"],
                                candle["high"],
                                candle["low"],
                                candle["close"],
                                candle["volume"],
                                candle["close_time"],
                                candle["quote_volume"],
                                candle["trades"],
                                candle["taker_buy_volume"],
                                candle["taker_buy_quote_volume"],
                                0,
                            ]
                        ]
                    ),
                    source="ws:live",
                )
                self.trader.on_finalized_candle(candle)
        except Exception as exc:
            self.ledger.record_failure(
                self.run_id,
                failure_type="runner_failure",
                reason=f"stream event handling failed: {exc}",
                event_ts_ms=event.event_time_ms,
            )
            raise

    async def run(self) -> None:
        """Consume the stream forever. No orders. No training. Frozen policy only."""
        self._check_not_closed()
        try:
            self.backfill()
            async for event in kline_events(
                self.settings.ws_base_url, self.settings.symbol, self.settings.interval
            ):
                self.handle_event(event)
        except Exception as exc:
            now = int(time.time() * 1000)
            self.ledger.record_failure(
                self.run_id,
                failure_type="runner_failure",
                reason=f"runner stream execution failed: {exc}",
                event_ts_ms=now,
            )
            raise
