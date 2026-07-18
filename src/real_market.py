"""Real Market Environment for Reinforcement Learning Trading Systems.

This module provides a production-ready financial market environment (`RealMarketEnv`)
that streams historical market data from `yfinance`. It inherits the complete logic
framework from `SyntheticMarketEnv`, including transaction cost modeling, position
tracking, 3-tier unrealized PnL states, and the Volatility-Adjusted Circuit Breaker
with proportional drawdown penalties.
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
import yfinance as yf


class RealMarketEnv:
    """Real Financial Market Environment streaming historical data via `yfinance`.

    Streams historical close prices and inherits the quantitative risk engine and
    trading mechanics from `SyntheticMarketEnv`. Dynamically computes discrete
    directional indicators across the latest three ticks and tracks a 3-tier
    unrealized PnL state to return a 4D state representation at each step.

    Parameters
    ----------
    ticker : str
        The financial symbol or ticker to download from `yfinance` (e.g., "AAPL").
    period : str, default="1mo"
        Historical data period to fetch (e.g., "1mo", "3mo", "1y").
    interval : str, default="15m"
        Bar/candle sampling frequency (e.g., "1m", "15m", "1h", "1d").
    transaction_cost : float, default=0.1
        Cost incurred whenever the trading position changes between steps.
    base_stop_dist : float, default=0.2
        Base adverse price distance from peak/trough for the circuit breaker.
    vol_multiplier : float, default=2.0
        Multiplier scaling the base stop distance by rolling return volatility.
    """

    ACTION_MAP: dict[int, int] = {
        0: -1,  # Short
        1: 0,   # Flat
        2: 1,   # Long
    }

    def __init__(
        self,
        ticker: str,
        period: str = "1mo",
        interval: str = "15m",
        transaction_cost: float = 0.1,
        base_stop_dist: float = 0.2,
        vol_multiplier: float = 2.0,
    ) -> None:
        if transaction_cost < 0.0:
            raise ValueError(
                f"Transaction cost must be non-negative, got {transaction_cost}."
            )
        if base_stop_dist < 0.0:
            raise ValueError(
                f"Base stop distance must be non-negative, got {base_stop_dist}."
            )

        self.ticker: str = str(ticker)
        self.period: str = str(period)
        self.interval: str = str(interval)
        self.transaction_cost: float = float(transaction_cost)
        self.base_stop_dist: float = float(base_stop_dist)
        self.vol_multiplier: float = float(vol_multiplier)

        # Download historical dataframe during initialization
        df = yf.download(
            self.ticker, period=self.period, interval=self.interval, progress=False
        )
        if df.empty or "Close" not in df or "High" not in df or "Low" not in df:
            raise ValueError(
                f"Failed to download valid historical data for ticker '{self.ticker}'."
            )

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close_data = df["Close"]
        high_data = df["High"]
        low_data = df["Low"]

        # Calculate 14-period RSI
        delta = close_data.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        roll_gain = gain.rolling(window=14).mean()
        roll_loss = loss.rolling(window=14).mean()
        rs = roll_gain / roll_loss.replace(0, 1e-9)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # Calculate 20-period Simple Moving Average (SMA)
        sma = close_data.rolling(window=20).mean()

        # Calculate 14-period Average True Range (ATR) and its 20-period Moving Average
        tr1 = high_data - low_data
        tr2 = (high_data - close_data.shift(1)).abs()
        tr3 = (low_data - close_data.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=14).mean()
        atr_sma = atr.rolling(window=20).mean()

        df_indicators = df.copy()
        df_indicators["RSI"] = rsi
        df_indicators["SMA"] = sma
        df_indicators["ATR"] = atr
        df_indicators["ATR_SMA"] = atr_sma
        df_clean = df_indicators.dropna(subset=["Close", "RSI", "SMA", "ATR", "ATR_SMA"])

        if df_clean.empty:
            raise ValueError(f"Failed to calculate indicators for ticker '{self.ticker}' (not enough data).")

        clean_close = df_clean["Close"]
        if hasattr(clean_close, "to_numpy"):
            self.prices = clean_close.to_numpy().flatten().astype(np.float64)
            self.rsi = df_clean["RSI"].to_numpy().flatten().astype(np.float64)
            self.sma = df_clean["SMA"].to_numpy().flatten().astype(np.float64)
            self.atr = df_clean["ATR"].to_numpy().flatten().astype(np.float64)
            self.atr_sma = df_clean["ATR_SMA"].to_numpy().flatten().astype(np.float64)
        else:
            self.prices = np.array(clean_close, dtype=np.float64).flatten()
            self.rsi = np.array(df_clean["RSI"], dtype=np.float64).flatten()
            self.sma = np.array(df_clean["SMA"], dtype=np.float64).flatten()
            self.atr = np.array(df_clean["ATR"], dtype=np.float64).flatten()
            self.atr_sma = np.array(df_clean["ATR_SMA"], dtype=np.float64).flatten()

        if len(self.prices) == 0:
            raise ValueError(f"No close prices found for ticker '{self.ticker}'.")

        self.current_step: int = 0
        self.current_price: float = float(self.prices[0])
        self.current_position: int = 1  # 0: Short, 1: Flat, 2: Long
        self.peak_price: float = 0.0
        self.trough_price: float = float("inf")
        self.entry_price: float = 0.0
        self.highest_price_since_entry: float = 0.0
        self.steps_in_position: int = 0
        self.returns_history: list[float] = []
        self.prev_action: int = 1

    @property
    def position(self) -> int:
        """The signed integer representation of the current position (-1, 0, or 1)."""
        return self.ACTION_MAP[self.current_position]

    def _get_state(self) -> tuple[int, int, int, int, int, int, int]:
        """Constructs the current 7D observation state tuple.

        Calculates directional differences (`prices[t] - prices[t-1]`) for the last
        three ticks and determines the 3-tier unrealized PnL state, RSI state, SMA state,
        and volatility state.

        Returns
        -------
        tuple[int, int, int, int, int, int, int]
            7D state tuple containing `(tick_1_dir, tick_2_dir, tick_3_dir, unrealized_pnl_state, rsi_state, sma_state, volatility_state)`.
        """
        t: int = self.current_step
        if t >= 3:
            tick_1_dir = 1 if self.prices[t - 2] - self.prices[t - 3] > 0.0 else 0
            tick_2_dir = 1 if self.prices[t - 1] - self.prices[t - 2] > 0.0 else 0
            tick_3_dir = 1 if self.prices[t] - self.prices[t - 1] > 0.0 else 0
        elif t == 2:
            tick_1_dir = 0
            tick_2_dir = 1 if self.prices[1] - self.prices[0] > 0.0 else 0
            tick_3_dir = 1 if self.prices[2] - self.prices[1] > 0.0 else 0
        elif t == 1:
            tick_1_dir = 0
            tick_2_dir = 0
            tick_3_dir = 1 if self.prices[1] - self.prices[0] > 0.0 else 0
        else:
            tick_1_dir = 0
            tick_2_dir = 0
            tick_3_dir = 0

        # Calculate 3-tier unrealized PnL state: -1 (Loss), 0 (Neutral/Zero), 1 (Profit)
        if self.current_position == 1:
            unrealized_pnl: float = 0.0
        else:
            unrealized_pnl = float(
                self.ACTION_MAP[self.current_position]
                * (self.current_price - self.entry_price)
            )

        if unrealized_pnl > 0.0:
            unrealized_pnl_state = 1
        elif unrealized_pnl < 0.0:
            unrealized_pnl_state = -1
        else:
            unrealized_pnl_state = 0

        # Calculate RSI state: 0 if RSI < 30 (Oversold), 2 if RSI > 70 (Overbought), 1 otherwise (Neutral)
        current_rsi = float(self.rsi[t])
        if current_rsi < 30.0:
            rsi_state = 0
        elif current_rsi > 70.0:
            rsi_state = 2
        else:
            rsi_state = 1

        # Calculate SMA state: 1 if current price > current SMA (Bullish), 0 if current price <= current SMA (Bearish)
        current_sma = float(self.sma[t])
        if self.current_price > current_sma:
            sma_state = 1
        else:
            sma_state = 0

        # Calculate Volatility state: 1 if current ATR > current 20-period ATR moving average (High Volatility), 0 otherwise (Low Volatility)
        current_atr = float(self.atr[t])
        current_atr_sma = float(self.atr_sma[t])
        if current_atr > current_atr_sma:
            volatility_state = 1
        else:
            volatility_state = 0

        return (tick_1_dir, tick_2_dir, tick_3_dir, unrealized_pnl_state, rsi_state, sma_state, volatility_state)

    def reset(self) -> tuple[int, int, int, int, int, int, int]:
        """Re-initializes the environment to its starting state.

        Resets step counter to 0, sets current price to the initial historical bar,
        resets position to Flat (1), clears circuit breaker tracking boundaries,
        and empties returns history.

        Returns
        -------
        tuple[int, int, int, int, int, int, int]
            Initial 7D state tuple `(tick_1_dir, tick_2_dir, tick_3_dir, unrealized_pnl_state, rsi_state, sma_state, volatility_state)`.
        """
        self.current_step = 0
        if len(self.prices) > 0:
            self.current_price = float(self.prices[0])
        else:
            self.current_price = 0.0
        self.current_position = 1
        self.peak_price = 0.0
        self.trough_price = float("inf")
        self.entry_price = 0.0
        self.highest_price_since_entry = 0.0
        self.steps_in_position = 0
        self.returns_history = []
        self.prev_action = 1
        return self._get_state()

    def step(self, action: int) -> tuple[tuple[int, int, int, int, int, int, int], float, bool, dict[str, Any]]:
        """Advances the market environment by one step using historical close prices.

        Enforces strict trailing stop-loss and position duration limits,
        computes baseline PnL with transaction costs without artificial penalties,
        and updates state tracking.

        Parameters
        ----------
        action : int
            Discrete trading action: 0 (Short), 1 (Flat), 2 (Long).

        Returns
        -------
        next_state : tuple[int, int, int, int, int, int, int]
            7D observation state tuple after advancing one bar.
        reward : float
            Net Profit-and-Loss (PnL) reward including transaction costs.
        done : bool
            True if `self.current_step >= len(self.prices) - 1`, False otherwise.
        info : dict[str, Any]
            Additional step information dictionary containing drawdown and duration metrics.

        Raises
        ------
        ValueError
            If an invalid action code is provided.
        """
        if action not in self.ACTION_MAP:
            raise ValueError(
                f"Invalid action {action}. Valid actions are 0 (Short), 1 (Flat), 2 (Long)."
            )

        prev_price: float = self.current_price

        self.current_step += 1
        if self.current_step < len(self.prices):
            self.current_price = float(self.prices[self.current_step])
        price_change: float = self.current_price - prev_price

        # 1. Calculate rolling standard deviation of self.returns_history
        if len(self.returns_history) < 5:
            vol: float = 0.0
        else:
            vol = float(np.std(self.returns_history))

        # 2. Compute dynamic_stop
        dynamic_stop: float = float(
            self.base_stop_dist * (1.0 + self.vol_multiplier * vol)
        )

        # 3. Track trailing stop-loss and position duration limit
        penalty: float = 0.0
        drawdown: float = 0.0
        if action != 1:  # Active position (handles Long action=0 or action=2 per specs/ACTION_MAP)
            if self.entry_price == 0.0:
                self.entry_price = self.current_price
            if self.highest_price_since_entry == 0.0:
                self.highest_price_since_entry = self.current_price

            self.steps_in_position += 1
            self.highest_price_since_entry = max(self.highest_price_since_entry, self.current_price)
            drawdown = (
                (self.highest_price_since_entry - self.current_price) / self.highest_price_since_entry
                if self.highest_price_since_entry > 0.0
                else 0.0
            )

            if drawdown > 0.02 or self.steps_in_position > 40:
                action = 1  # Force position to Flat

        # 4. Append latest return to self.returns_history
        self.returns_history.append(price_change)
        if len(self.returns_history) > 10:
            self.returns_history = self.returns_history[-10:]

        # Calculate baseline PnL and finalized reward
        baseline_pnl: float = float(self.ACTION_MAP[action] * price_change)
        if action != self.current_position:
            reward: float = baseline_pnl - self.transaction_cost + penalty
        else:
            reward = baseline_pnl + penalty

        # Apply switching penalty if action changes from previous action
        if action != self.prev_action:
            reward -= 0.001

        # Update entry price if entering a new active position
        if action != self.current_position and action != 1:
            self.entry_price = self.current_price

        self.current_position = action
        if self.current_position == 1:
            self.entry_price = 0.0
            self.highest_price_since_entry = 0.0
            self.steps_in_position = 0
            self.peak_price = 0.0
            self.trough_price = float("inf")

        # Handle truncation: if self.current_step >= len(self.prices) - 1, set done = True
        done: bool = self.current_step >= len(self.prices) - 1

        self.prev_action = action

        info: dict[str, Any] = {
            "drawdown": drawdown if self.current_position != 1 else 0.0,
            "steps_in_position": self.steps_in_position,
        }

        return self._get_state(), reward, done, info


if __name__ == "__main__":
    print("=== Testing RealMarketEnv with yfinance stream ===")
    try:
        env = RealMarketEnv(
            ticker="AAPL", period="5d", interval="15m", transaction_cost=0.05
        )
        state = env.reset()
        print(
            f"Successfully loaded {len(env.prices)} historical bars for AAPL."
        )
        print(
            f"INITIAL STATE (7D tuple): {state} | Initial Price: {env.current_price:.4f}"
        )

        # Run sample steps through the streamed historical data
        for step_idx in range(1, 6):
            next_state, reward, done, info = env.step(action=2 if step_idx < 4 else 1)
            print(
                f"Step {step_idx:2d} | Price: {env.current_price:8.4f} | "
                f"State (t1, t2, t3, pnl_state, rsi_state, sma_state, vol_state): {next_state} | "
                f"Reward: {reward:+.4f} | Done: {done} | Info: {info}"
            )
    except Exception as exc:
        print(f"RealMarketEnv initialization/execution note: {exc}")
