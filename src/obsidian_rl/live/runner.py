"""Live-paper session runner: bootstrap, backfill, stream consumption, persistence.

Event handling on top of PaperTrader's two-phase protocol:
- k.x == true  -> finalized candle: persist to the candle store, phase 1 (decide);
- first event of a NEW candle (k.t advanced) -> phase 2 (execute at its open price).
Missed candles after disconnects are backfilled through REST before resuming.
"""

import logging
import time

from obsidian_rl.config import Settings
from obsidian_rl.data.binance_client import BinanceFuturesRest
from obsidian_rl.data.schema import interval_to_ms, klines_to_frame
from obsidian_rl.data.store import CandleStore
from obsidian_rl.data.validation import drop_unfinalized, require_valid
from obsidian_rl.ledger.ledger import Ledger
from obsidian_rl.live.paper_trader import BUFFER_SIZE, PaperTrader, replay_candles
from obsidian_rl.live.stream import KlineEvent, kline_events
from obsidian_rl.strategies.base import Strategy

logger = logging.getLogger(__name__)


class LivePaperRunner:
    def __init__(
        self,
        settings: Settings,
        strategy: Strategy,
        *,
        run_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.store = CandleStore(settings.data_dir, settings.symbol, settings.interval)
        self.ledger = Ledger(settings.ledger_path)
        self.rest = BinanceFuturesRest(settings.fapi_base_url, timeout_s=settings.request_timeout_s)
        self.interval_ms = interval_to_ms(settings.interval)

        strategy_id = getattr(strategy, "strategy_id", "unknown")
        if run_id is None:
            run = self.ledger.start_run(
                strategy_id,
                "live-paper",
                10_000.0,
                cost_model={},
                model_id=model_id,
            )
            run_id = run.run_id
            resume = False
        else:
            resume = self.ledger.get_run(run_id) is not None
            if not resume:
                raise ValueError(f"run {run_id} not found in ledger; cannot resume")
        self.run_id = run_id
        self.trader = PaperTrader(
            strategy,
            self.ledger,
            run_id,
            interval=settings.interval,
            data_source=f"ws:{settings.symbol}",
        )
        if resume:
            state = self.ledger.restore_state(run_id)
            candles = self.store.read()
            if state is not None and len(candles):
                self.trader.restore(state, candles)
            logger.info("resuming run %s", run_id)

    # ------------------------------------------------------------------ helpers
    def backfill(self, now_ms: int | None = None) -> int:
        """Fetch finalized candles between the trader's last candle and now via REST."""
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        last = self.trader.last_finalized_ms
        if last is None:
            start = (now // self.interval_ms) * self.interval_ms - BUFFER_SIZE * self.interval_ms
        else:
            start = last + self.interval_ms
        df = self.rest.fetch_klines(self.settings.symbol, self.settings.interval, start)
        df = drop_unfinalized(df, now)
        if df.empty:
            return 0
        require_valid(df, self.settings.interval, now_ms=now)
        self.store.write(df, source="fapi:backfill")
        replay_candles(self.trader, df)
        return len(df)

    def handle_event(self, event: KlineEvent) -> None:
        """Route one websocket kline event through the two-phase protocol."""
        last = self.trader.last_finalized_ms
        # Phase 2: the first event of a new candle carries its (fixed) open price.
        if (
            self.trader.pending is not None
            and event.open_time == self.trader.pending.candle_open_ms + self.interval_ms
        ):
            self.trader.on_next_open(event.open_time, event.open)
        if event.is_closed:
            if last is not None and event.open_time > last + self.interval_ms:
                logger.warning("gap detected before %s; backfilling", event.open_time)
                self.backfill()
                if self.trader.last_finalized_ms is not None and (
                    event.open_time <= self.trader.last_finalized_ms
                ):
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

    async def run(self) -> None:
        """Consume the stream forever. No orders. No training. Frozen policy only."""
        self.backfill()
        async for event in kline_events(
            self.settings.ws_base_url, self.settings.symbol, self.settings.interval
        ):
            self.handle_event(event)
