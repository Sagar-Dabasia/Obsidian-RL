"""Alpha Gate Training Module for Institutional RL Trading Systems.

Fetches historical 15m klines from the Binance Testnet for `BTCUSDT`, engineers
continuous technical indicator features (`RSI`, `SMA`, `MACD`, `ATR`), constructs
the forward 4-candle `Max_Deviation` target variable, fits a LightGBM Regressor (`LGBMRegressor`),
and persists the trained model artifact (`alpha_gate.pkl`) using `joblib`.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from binance.client import Client
from dotenv import load_dotenv
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

# Ensure project root is accessible on sys.path for robust module execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def fetch_binance_testnet_klines(
    symbol: str = "BTCUSDT",
    limit: int = 5000,
    interval: str = Client.KLINE_INTERVAL_15MINUTE,
) -> pd.DataFrame:
    """Retrieves historical klines from Binance Testnet and parses into a clean DataFrame.

    Parameters
    ----------
    symbol : str, default="BTCUSDT"
        Target trading pair symbol.
    limit : int, default=5000
        Number of historical candles to fetch.
    interval : str, default=Client.KLINE_INTERVAL_15MINUTE
        Bar interval string.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns `['Open', 'High', 'Low', 'Close', 'Volume']` as float.
    """
    env_path = Path(_project_root) / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    client = Client(api_key, api_secret, testnet=True)

    # To ensure up to 5,000 candles on 15m interval (approx 52.1 days), fetch from 60 days ago
    start_str = "60 days ago UTC"
    raw_klines = client.get_historical_klines(symbol, interval, start_str=start_str)

    if not raw_klines or len(raw_klines) == 0:
        raise ValueError(f"Failed to fetch historical klines from Binance Testnet for {symbol}.")

    if len(raw_klines) > limit:
        raw_klines = raw_klines[-limit:]

    df = pd.DataFrame(raw_klines, columns=[
        "Open_Time", "Open", "High", "Low", "Close", "Volume",
        "Close_Time", "Quote_Volume", "Trades", "Taker_Base", "Taker_Quote", "Ignore"
    ])
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df.reset_index(drop=True)


def engineer_features_and_target(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates technical indicators (`RSI`, `SMA`, `MACD`, `ATR`) and `Max_Deviation` target.

    Parameters
    ----------
    df : pd.DataFrame
        Raw OHLCV dataframe.

    Returns
    -------
    pd.DataFrame
        DataFrame augmented with technical indicators and `Max_Deviation` column.
    """
    df_feat = df.copy()

    # 1. RSI (14)
    delta = df_feat["Close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    roll_gain = gain.rolling(window=14, min_periods=1).mean()
    roll_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = roll_gain / roll_loss.replace(0, 1e-9)
    df_feat["RSI"] = 100.0 - (100.0 / (1.0 + rs))

    # 2. SMA (50)
    df_feat["SMA"] = df_feat["Close"].rolling(window=50, min_periods=1).mean()

    # 3. MACD (12 EMA - 26 EMA - 9 Signal EMA)
    ema_12 = df_feat["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = df_feat["Close"].ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    df_feat["MACD"] = macd_line - signal_line

    # 4. ATR (14)
    tr1 = df_feat["High"] - df_feat["Low"]
    tr2 = (df_feat["High"] - df_feat["Close"].shift(1)).abs()
    tr3 = (df_feat["Low"] - df_feat["Close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df_feat["ATR"] = tr.rolling(window=14, min_periods=1).mean()

    # 5. Target: Max_Deviation over subsequent 4 rows
    forward_high = df_feat["High"].shift(-1).rolling(window=4, min_periods=1).max()
    forward_low = df_feat["Low"].shift(-1).rolling(window=4, min_periods=1).min()
    high_diff_pct = (forward_high - df_feat["Close"]).abs() / df_feat["Close"]
    low_diff_pct = (forward_low - df_feat["Close"]).abs() / df_feat["Close"]
    df_feat["Max_Deviation"] = pd.concat([high_diff_pct, low_diff_pct], axis=1).max(axis=1)

    return df_feat


def train_and_save_alpha_gate(
    symbol: str = "BTCUSDT",
    limit: int = 5000,
    model_output_path: str | Path | None = None,
) -> lgb.LGBMRegressor:
    """Fetches Binance Testnet data, engineers features/targets, fits LGBMRegressor, and saves via joblib.

    Parameters
    ----------
    symbol : str, default="BTCUSDT"
        Trading pair symbol to train on.
    limit : int, default=5000
        Maximum number of historical klines to fetch.
    model_output_path : str | Path | None, default=None
        Path to save output `.pkl` model. Defaults to `alpha_gate.pkl` in project root.

    Returns
    -------
    lgb.LGBMRegressor
        Fitted LightGBM regressor instance.
    """
    df_raw = fetch_binance_testnet_klines(symbol=symbol, limit=limit)
    df_augmented = engineer_features_and_target(df_raw)

    feature_cols = ["RSI", "SMA", "MACD", "ATR"]
    target_col = "Max_Deviation"

    df_clean = df_augmented.dropna(subset=feature_cols + [target_col]).reset_index(drop=True)

    X = df_clean[feature_cols]
    y = df_clean[target_col]

    model = lgb.LGBMRegressor(
        n_estimators=150,
        learning_rate=0.05,
        num_leaves=31,
        random_state=42,
        verbosity=-1,
    )
    model.fit(X, y)

    target_path = Path(model_output_path) if model_output_path is not None else Path(_project_root) / "alpha_gate.pkl"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, target_path)

    print(f"[SUCCESS] LightGBM Alpha Gate model trained on {len(df_clean):,} historical {symbol} candles.")
    print(f"[SAVED] Saved model artifact to: {target_path}")
    print(f"[BASELINE] Historical baseline established. Target mean Max_Deviation: {y.mean():.4f} (std: {y.std():.4f})")
    return model


if __name__ == "__main__":
    train_and_save_alpha_gate(symbol="BTCUSDT", limit=5000)
