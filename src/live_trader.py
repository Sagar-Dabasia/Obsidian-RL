"""Live Paper-Trading Execution Module for Institutional RL Trading Systems.

Connects to the Binance Testnet to stream real-time 15m klines for `BTCUSDT`.
Dynamically extracts the 7D state representation (`tick_1, tick_2, tick_3, pnl_state, rsi_state, sma_state, volatility_state`),
forces deterministic action selection via `QLearningAgent` (`epsilon = 0.0`),
and tracks a virtual paper trading balance starting at $10,000 with exact realized
PnL accounting and 0.05% transaction costs on position changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

from binance.client import Client
from dotenv import load_dotenv
import joblib
import numpy as np
import pandas as pd

# Ensure project root is accessible on sys.path for robust module execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.ql_agent import QLearningAgent


ACTION_MAP: dict[int, int] = {
    0: -1,  # Short
    1: 0,   # Flat
    2: 1,   # Long
}

ACTION_NAMES: dict[int, str] = {
    0: "Short (0)",
    1: "Flat (1)",
    2: "Long (2)",
}


def setup_logger(log_file: str | Path = "live_trades.log") -> logging.Logger:
    """Configures and returns the production logger for live paper trading.

    Appends execution steps, timestamps, asset prices, actions, and account
    balances to both console output and `live_trades.log`.

    Parameters
    ----------
    log_file : str | Path, default="live_trades.log"
        Path to the local log file.

    Returns
    -------
    logging.Logger
        Configured logger instance.
    """
    logger = logging.getLogger("live_trader")
    logger.setLevel(logging.INFO)

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        console_handler = logging.StreamHandler(sys.stdout)

        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


def load_agent_checkpoint(
    agent: QLearningAgent,
    checkpoint_path: str | Path | None = None,
) -> QLearningAgent:
    """Loads a saved 7D Q-table checkpoint into the provided QLearningAgent.

    Parameters
    ----------
    agent : QLearningAgent
        Target agent instance to populate.
    checkpoint_path : str | Path | None, default=None
        Explicit path to checkpoint file. If None, searches standard project paths.

    Returns
    -------
    QLearningAgent
        Agent loaded with the saved Q-table.

    Raises
    ------
    FileNotFoundError
        If no checkpoint file can be located.
    """
    candidate_paths: list[Path] = []
    if checkpoint_path is not None:
        candidate_paths.append(Path(checkpoint_path))
    else:
        candidate_paths.extend([
            Path(_project_root) / "q_table.pkl",
            Path("q_table.pkl"),
            Path(_project_root) / "src" / "q_table.pkl",
            Path(_project_root) / "q_table_7d.pkl",
            Path("q_table_7d.pkl"),
        ])

    for path in candidate_paths:
        if path.exists():
            agent.load_checkpoint(path)
            return agent

    raise FileNotFoundError(
        f"Could not locate saved Q-table checkpoint in paths: {[str(p) for p in candidate_paths]}. "
        f"Please run `python src/train.py` first to generate a checkpoint."
    )


def compute_7d_state(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    current_position: int,
    entry_price: float,
) -> tuple[int, int, int, int, int, int, int]:
    """Calculates the 7D observation state tuple from recent market price arrays.

    Replicates the exact quantitative indicator and state boundaries found in `src/real_market.py`.

    Parameters
    ----------
    closes : np.ndarray
        Array of recent bar closing prices.
    highs : np.ndarray
        Array of recent bar high prices.
    lows : np.ndarray
        Array of recent bar low prices.
    current_position : int
        Current trading position code: 0 (Short), 1 (Flat), 2 (Long).
    entry_price : float
        Price at which the current active position was opened.

    Returns
    -------
    tuple[int, int, int, int, int, int, int]
        7D observation state `(tick_1_dir, tick_2_dir, tick_3_dir, unrealized_pnl_state, rsi_state, sma_state, volatility_state)`.
    """
    n = len(closes)
    current_price = float(closes[-1])

    # Directional differences across the latest three ticks
    if n >= 4:
        tick_1_dir = 1 if closes[-2] - closes[-3] > 0.0 else 0
        tick_2_dir = 1 if closes[-1] - closes[-2] > 0.0 else 0
        tick_3_dir = 1 if current_price - closes[-1] > 0.0 else 0
    elif n == 3:
        tick_1_dir = 0
        tick_2_dir = 1 if closes[-1] - closes[-2] > 0.0 else 0
        tick_3_dir = 1 if current_price - closes[-1] > 0.0 else 0
    elif n == 2:
        tick_1_dir = 0
        tick_2_dir = 0
        tick_3_dir = 1 if current_price - closes[-1] > 0.0 else 0
    else:
        tick_1_dir = 0
        tick_2_dir = 0
        tick_3_dir = 0

    # Unrealized PnL state: -1 (Loss), 0 (Neutral), 1 (Profit)
    if current_position == 1:
        unrealized_pnl: float = 0.0
    else:
        unrealized_pnl = float(ACTION_MAP[current_position] * (current_price - entry_price))

    if unrealized_pnl > 0.0:
        unrealized_pnl_state = 1
    elif unrealized_pnl < 0.0:
        unrealized_pnl_state = -1
    else:
        unrealized_pnl_state = 0

    close_series = pd.Series(closes)
    high_series = pd.Series(highs)
    low_series = pd.Series(lows)

    # 14-period RSI
    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    roll_gain = gain.rolling(window=14, min_periods=1).mean()
    roll_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = roll_gain / roll_loss.replace(0, 1e-9)
    rsi_series = 100.0 - (100.0 / (1.0 + rs))
    current_rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    if current_rsi < 30.0:
        rsi_state = 0
    elif current_rsi > 70.0:
        rsi_state = 2
    else:
        rsi_state = 1

    # 20-period Simple Moving Average (SMA)
    sma_series = close_series.rolling(window=20, min_periods=1).mean()
    current_sma = float(sma_series.iloc[-1]) if not pd.isna(sma_series.iloc[-1]) else current_price
    sma_state = 1 if current_price > current_sma else 0

    # 14-period ATR and 20-period ATR Moving Average
    tr1 = high_series - low_series
    tr2 = (high_series - close_series.shift(1)).abs()
    tr3 = (low_series - close_series.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_series = tr.rolling(window=14, min_periods=1).mean()
    atr_sma_series = atr_series.rolling(window=20, min_periods=1).mean()

    current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0
    current_atr_sma = float(atr_sma_series.iloc[-1]) if not pd.isna(atr_sma_series.iloc[-1]) else 0.0
    volatility_state = 1 if current_atr > current_atr_sma else 0

    return (tick_1_dir, tick_2_dir, tick_3_dir, unrealized_pnl_state, rsi_state, sma_state, volatility_state)


def extract_current_kline_features(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> pd.DataFrame:
    """Calculates RSI (14), SMA (50), MACD, and ATR (14) for the latest bar matching train_alpha_gate.py."""
    close_series = pd.Series(closes, dtype=np.float64)
    high_series = pd.Series(highs, dtype=np.float64)
    low_series = pd.Series(lows, dtype=np.float64)

    # 1. RSI (14)
    delta = close_series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    roll_gain = gain.rolling(window=14, min_periods=1).mean()
    roll_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = roll_gain / roll_loss.replace(0, 1e-9)
    rsi_series = 100.0 - (100.0 / (1.0 + rs))
    current_rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    # 2. SMA (50)
    sma_series = close_series.rolling(window=50, min_periods=1).mean()
    current_sma = float(sma_series.iloc[-1]) if not pd.isna(sma_series.iloc[-1]) else float(closes[-1])

    # 3. MACD (12 EMA - 26 EMA - 9 Signal EMA)
    ema_12 = close_series.ewm(span=12, adjust=False).mean()
    ema_26 = close_series.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_series = macd_line - signal_line
    current_macd = float(macd_series.iloc[-1]) if not pd.isna(macd_series.iloc[-1]) else 0.0

    # 4. ATR (14)
    tr1 = high_series - low_series
    tr2 = (high_series - close_series.shift(1)).abs()
    tr3 = (low_series - close_series.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_series = tr.rolling(window=14, min_periods=1).mean()
    current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0

    return pd.DataFrame(
        [[current_rsi, current_sma, current_macd, current_atr]],
        columns=["RSI", "SMA", "MACD", "ATR"],
    )


def sleep_until_next_15m_candle(logger: logging.Logger, is_test: bool = False) -> None:
    """Calculates time remaining to next 15m mark (+2s buffer), logs, and pauses execution.

    Parameters
    ----------
    logger : logging.Logger
        Active execution logger instance.
    is_test : bool, default=False
        If True, pauses briefly (1s) instead of waiting minutes during verification runs.
    """
    now = datetime.now()
    minute_floor = (now.minute // 15) * 15
    current_mark = now.replace(minute=minute_floor, second=0, microsecond=0)
    next_mark = current_mark + timedelta(minutes=15) + timedelta(seconds=2)
    if next_mark <= now:
        next_mark += timedelta(minutes=15)

    seconds_remaining = (next_mark - now).total_seconds()
    logger.info(f"Waiting {seconds_remaining:.1f}s until next 15m candle close execution window ({next_mark.strftime('%H:%M:%S')}).")

    if is_test:
        time.sleep(1.0)
    else:
        if seconds_remaining > 0:
            time.sleep(seconds_remaining)


def run_live_trader(
    symbol: str = "BTCUSDT",
    initial_balance: float = 10000.0,
    max_steps: int | None = None,
    checkpoint_path: str | Path | None = None,
    log_file: str | Path = "live_trades.log",
) -> float:
    """Executes the continuous live paper-trading loop connected to Binance Testnet.

    Streams the last 65 15m klines, filters for finalized closed candles, computes
    the exact 7D state, forces exploration `epsilon = 0.0`, uses the loaded `alpha_gate.pkl`
    LightGBM model to filter actions when expected `Max_Deviation < 0.001`, manages virtual
    paper balance with realized PnL accounting upon position changes, subtracts 0.05%
    transaction costs, and logs steps.

    Parameters
    ----------
    symbol : str, default="BTCUSDT"
        Trading pair symbol on Binance.
    initial_balance : float, default=10000.0
        Starting paper trading account balance in USD.
    max_steps : int | None, default=None
        Optional step cap for verification runs. If None, loops indefinitely (`while True:`).
    checkpoint_path : str | Path | None, default=None
        Path to explicit Q-table checkpoint `.pkl` file.
    log_file : str | Path, default="live_trades.log"
        Path to local log output file.

    Returns
    -------
    float
        Final virtual paper trading balance when execution stops.
    """
    logger = setup_logger(log_file)
    logger.info(
        f"=== Starting Live Paper-Trading Engine | Asset: {symbol} | "
        f"Initial Balance: ${initial_balance:,.2f} ==="
    )

    # Load environment credentials and initialize Binance Client strictly on Testnet
    env_path = Path(_project_root) / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")

    client: Client | None = None
    client_retries = 0
    while client is None:
        try:
            client = Client(api_key, api_secret, testnet=True)
        except Exception as e:
            client_retries += 1
            if max_steps is not None and client_retries >= 3:
                raise RuntimeError(f"Failed to connect to Binance Testnet after {client_retries} retries: {e}") from e
            logger.warning(f"Network error initializing Binance Client ({e}). Retrying in 15s...")
            time.sleep(15)

    agent = QLearningAgent()
    load_agent_checkpoint(agent, checkpoint_path=checkpoint_path)
    agent.epsilon = 0.0
    logger.info(
        f"Connected to Binance Testnet for {symbol}. Agent checkpoint loaded ({len(agent.q_table)} keys). "
        f"Epsilon strictly locked to {agent.epsilon:.1f}."
    )

    alpha_gate_path = Path(_project_root) / "alpha_gate.pkl"
    if not alpha_gate_path.exists():
        alpha_gate_path = Path("alpha_gate.pkl")
    if not alpha_gate_path.exists():
        raise FileNotFoundError(f"Alpha Gate model artifact not found at {alpha_gate_path}. Please run `python src/train_alpha_gate.py` first.")
    alpha_gate = joblib.load(alpha_gate_path)
    logger.info(f"Loaded LightGBM Alpha Gate model from {alpha_gate_path}.")

    paper_balance: float = float(initial_balance)
    current_position: int = 1  # 0: Short, 1: Flat, 2: Long
    entry_price: float = 0.0
    step_count: int = 0

    while True:
        # Temporal lock: wait until exactly 2 seconds after the 15-minute mark to ensure closed candle
        sleep_until_next_15m_candle(logger, is_test=(max_steps is not None))

        step_count += 1

        # Fetch the last 65 15m klines for BTCUSDT using client.get_klines()
        try:
            raw_klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=65)
        except Exception as e:
            logger.warning(f"Network error fetching klines from Binance for {symbol} ({e}). Retrying...")
            time.sleep(15)
            continue
        if not raw_klines or len(raw_klines) == 0:
            logger.warning(f"No kline data received from Binance for {symbol}. Retrying...")
            time.sleep(15)
            continue

        # ONLY use finalized closed candles (exclude currently forming, incomplete candle based on Close time k[6])
        current_time_ms = int(time.time() * 1000)
        closed_klines = [k for k in raw_klines if int(k[6]) < current_time_ms]
        if len(closed_klines) == 0:
            closed_klines = raw_klines[:-1] if len(raw_klines) > 1 else raw_klines

        klines = closed_klines[-60:]
        if len(klines) == 0:
            logger.warning(f"No closed kline data available for {symbol}. Retrying...")
            time.sleep(15)
            continue

        highs = np.array([float(k[2]) for k in klines], dtype=np.float64)
        lows = np.array([float(k[3]) for k in klines], dtype=np.float64)
        closes = np.array([float(k[4]) for k in klines], dtype=np.float64)
        current_price = float(closes[-1])

        # Dynamically calculate the 7D state from this live data array
        state = compute_7d_state(closes, highs, lows, current_position, entry_price)
        action: int = agent.choose_action(state)

        # Alpha Gate: format current kline features into pandas DataFrame matching training structure
        alpha_gate_features = extract_current_kline_features(closes, highs, lows)
        predicted_max_dev = float(alpha_gate.predict(alpha_gate_features)[0])

        if predicted_max_dev < 0.001:
            if action in (0, 2):
                logger.info("Trade blocked by Alpha Gate: Expected move below friction threshold.")
            action = 1

        action_str = ACTION_NAMES.get(action, f"Unknown ({action})")

        # PnL accounting logic
        realized_pnl: float = 0.0
        tx_cost: float = 0.0

        if action != current_position:
            # If closing or switching out of an existing active position, realize PnL
            if current_position != 1 and entry_price > 0.0:
                position_sign = ACTION_MAP[current_position]
                realized_pnl = float(position_sign * (current_price - entry_price))

            # Add realized profit/loss to virtual balance BEFORE applying the 0.05% transaction cost
            paper_balance += realized_pnl
            tx_cost = 0.0005 * current_price
            paper_balance -= tx_cost

            # Update entry_price = current_price upon entering a new active position
            if action != 1:
                entry_price = current_price
            else:
                entry_price = 0.0

            current_position = action

        timestamp_str = datetime.now().isoformat()
        logger.info(
            f"Step: {step_count:4d} | Time: {timestamp_str} | Price: ${current_price:10.4f} | "
            f"Action: {action_str:9s} | PnL: ${realized_pnl:+7.2f} | TxCost: ${tx_cost:5.2f} | "
            f"Balance: ${paper_balance:12.4f} | State 7D: {state}"
        )

        if max_steps is not None and step_count >= max_steps:
            logger.info(f"Reached maximum requested verification steps ({max_steps}). Exiting live loop.")
            break

    logger.info(f"=== Live Paper-Trading Ended | Final Balance: ${paper_balance:,.2f} ===")
    return paper_balance


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("=== Running Verification Test for Live Trader on Binance Testnet ===")
        run_live_trader(symbol="BTCUSDT", max_steps=3)
    else:
        run_live_trader(symbol="BTCUSDT")
