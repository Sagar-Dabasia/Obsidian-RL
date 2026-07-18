"""Alpha Gate Module: LightGBM Regressor Pipeline for Unprofitable Trade Filtering.

Builds and serves a LightGBM Regressor trained to predict forward 4-candle maximum
percentage price deviations using continuous technical features: raw RSI values,
SMA crossovers, MACD histogram, and rolling ATR. Serves `predict_trade_viability`
to filter trades when expected forward move < 0.001 (0.1% friction threshold).
"""

from __future__ import annotations

import os
from pathlib import Path
import pickle
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import yfinance as yf


MODEL_FILENAME = "alpha_gate_model.pkl"
FEATURE_NAMES = ["rsi", "sma_crossover", "macd_hist", "atr"]
_model_cache: lgb.LGBMRegressor | None = None


def extract_continuous_features(
    closes: np.ndarray | pd.Series,
    highs: np.ndarray | pd.Series,
    lows: np.ndarray | pd.Series,
) -> pd.DataFrame:
    """Extracts continuous historical features from price series.

    Computes raw RSI values (14-period), SMA crossovers (20-period),
    MACD histogram (12, 26, 9), and rolling ATR (14-period normalized by Close).

    Parameters
    ----------
    closes : np.ndarray | pd.Series
        Closing prices series or array.
    highs : np.ndarray | pd.Series
        High prices series or array.
    lows : np.ndarray | pd.Series
        Low prices series or array.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns `['rsi', 'sma_crossover', 'macd_hist', 'atr']`.
    """
    c = pd.Series(closes, dtype=np.float64).reset_index(drop=True)
    h = pd.Series(highs, dtype=np.float64).reset_index(drop=True)
    l = pd.Series(lows, dtype=np.float64).reset_index(drop=True)

    # 1. Raw RSI values (14-period)
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    roll_gain = gain.rolling(window=14, min_periods=1).mean()
    roll_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = roll_gain / roll_loss.replace(0, 1e-9)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # 2. SMA crossovers (Close / SMA_20 - 1.0)
    sma_20 = c.rolling(window=20, min_periods=1).mean()
    sma_crossover = (c - sma_20) / sma_20.replace(0, 1e-9)

    # 3. MACD histogram (12 EMA - 26 EMA - 9 Signal EMA, normalized by Close)
    ema_12 = c.ewm(span=12, adjust=False).mean()
    ema_26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = (macd_line - signal_line) / c.replace(0, 1e-9)

    # 4. Rolling ATR (14-period normalized by Close)
    tr1 = h - l
    tr2 = (h - c.shift(1)).abs()
    tr3 = (l - c.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=14, min_periods=1).mean() / c.replace(0, 1e-9)

    df_features = pd.DataFrame({
        "rsi": rsi,
        "sma_crossover": sma_crossover,
        "macd_hist": macd_hist,
        "atr": atr,
    }).fillna(0.0)

    return df_features


def train_alpha_gate_model(
    ticker: str = "BTC-USD",
    period: str = "60d",
    interval: str = "15m",
    save_path: str | Path | None = None,
) -> lgb.LGBMRegressor:
    """Trains a LightGBM Regressor pipeline to predict forward 4-candle max price deviation.

    Parameters
    ----------
    ticker : str, default="BTC-USD"
        Asset symbol to fetch historical training data for via yfinance.
    period : str, default="60d"
        Historical data fetch duration.
    interval : str, default="15m"
        Bar interval.
    save_path : str | Path | None, default=None
        Path to save trained `.pkl` model checkpoint.

    Returns
    -------
    lgb.LGBMRegressor
        Trained LightGBM regressor model.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    except Exception:
        df = pd.DataFrame()

    if df.empty or len(df) < 50:
        np.random.seed(42)
        n_synthetic = 2000
        returns = np.random.normal(0.0001, 0.005, n_synthetic)
        closes = 60000.0 * np.exp(np.cumsum(returns))
        highs = closes * (1.0 + np.abs(np.random.normal(0.002, 0.001, n_synthetic)))
        lows = closes * (1.0 - np.abs(np.random.normal(0.002, 0.001, n_synthetic)))
        df = pd.DataFrame({"Close": closes, "High": highs, "Low": lows})

    X = extract_continuous_features(df["Close"], df["High"], df["Low"]).reset_index(drop=True)

    # Target: maximum percentage price deviation (high/low bounds) over forward window of 4 candles
    forward_high = df["High"].shift(-1).rolling(window=4, min_periods=1).max()
    forward_low = df["Low"].shift(-1).rolling(window=4, min_periods=1).min()
    high_dev = (forward_high - df["Close"]).abs() / df["Close"]
    low_dev = (forward_low - df["Close"]).abs() / df["Close"]
    y = pd.concat([high_dev, low_dev], axis=1).max(axis=1).fillna(0.0).reset_index(drop=True)

    valid_mask = ~y.isna() & (y > 0.0)
    if valid_mask.sum() > 20:
        X_train = X[valid_mask]
        y_train = y[valid_mask]
    else:
        X_train = X
        y_train = y

    model = lgb.LGBMRegressor(
        n_estimators=100,
        learning_rate=0.05,
        num_leaves=31,
        random_state=42,
        verbosity=-1,
    )
    model.fit(X_train[FEATURE_NAMES], y_train)

    target_path = Path(save_path) if save_path is not None else Path(__file__).resolve().parent.parent / MODEL_FILENAME
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "wb") as f:
        pickle.dump(model, f)

    return model


def get_alpha_gate_model(model_path: str | Path | None = None) -> lgb.LGBMRegressor:
    """Retrieves or trains the LightGBM regressor model.

    Parameters
    ----------
    model_path : str | Path | None, default=None
        Path to checkpoint file.

    Returns
    -------
    lgb.LGBMRegressor
        Loaded or freshly trained model instance.
    """
import joblib


def get_alpha_gate_model(model_path: str | Path | None = None) -> lgb.LGBMRegressor:
    """Retrieves or trains the LightGBM regressor model.

    Parameters
    ----------
    model_path : str | Path | None, default=None
        Path to checkpoint file.

    Returns
    -------
    lgb.LGBMRegressor
        Loaded or freshly trained model instance.
    """
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    root_dir = Path(__file__).resolve().parent.parent
    candidate_paths: list[Path] = []
    if model_path is not None:
        candidate_paths.append(Path(model_path))
    else:
        candidate_paths.extend([
            root_dir / "alpha_gate.pkl",
            Path("alpha_gate.pkl"),
            root_dir / MODEL_FILENAME,
            Path(MODEL_FILENAME),
        ])

    for target_path in candidate_paths:
        if target_path.exists():
            try:
                if str(target_path).endswith(".pkl"):
                    try:
                        _model_cache = joblib.load(target_path)
                        return _model_cache
                    except Exception:
                        with open(target_path, "rb") as f:
                            _model_cache = pickle.load(f)
                            return _model_cache
            except Exception:
                pass

    _model_cache = train_alpha_gate_model(save_path=root_dir / MODEL_FILENAME)
    return _model_cache


def extract_uppercase_features(
    closes: np.ndarray | pd.Series,
    highs: np.ndarray | pd.Series,
    lows: np.ndarray | pd.Series,
) -> pd.DataFrame:
    """Extracts uppercase indicators (`RSI`, `SMA`, `MACD`, `ATR`) matching `train_alpha_gate.py`."""
    c = pd.Series(closes, dtype=np.float64).reset_index(drop=True)
    h = pd.Series(highs, dtype=np.float64).reset_index(drop=True)
    l = pd.Series(lows, dtype=np.float64).reset_index(drop=True)

    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    roll_gain = gain.rolling(window=14, min_periods=1).mean()
    roll_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = roll_gain / roll_loss.replace(0, 1e-9)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    sma = c.rolling(window=50, min_periods=1).mean()

    ema_12 = c.ewm(span=12, adjust=False).mean()
    ema_26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd = macd_line - signal_line

    tr1 = h - l
    tr2 = (h - c.shift(1)).abs()
    tr3 = (l - c.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=14, min_periods=1).mean()

    return pd.DataFrame({"RSI": rsi, "SMA": sma, "MACD": macd, "ATR": atr}).fillna(0.0)


def predict_trade_viability(state_data: Any) -> bool:
    """Predicts whether the expected forward price move meets the friction threshold.

    Parameters
    ----------
    state_data : Any
        Either a tuple/dict containing `(closes, highs, lows)` price arrays/series,
        a `pd.DataFrame` with historical price bars or features, or a feature vector/dict
        containing `rsi`, `sma_crossover`, `macd_hist`, and `atr` (`or `RSI`, `SMA`, `MACD`, `ATR`).

    Returns
    -------
    bool
        True if the predicted forward 4-candle maximum move >= 0.001 (0.1%), False otherwise.
    """
    model = get_alpha_gate_model()
    model_features = getattr(model, "feature_name_", FEATURE_NAMES)
    use_uppercase = any(col in model_features for col in ["RSI", "SMA", "MACD", "ATR"])
    target_features = ["RSI", "SMA", "MACD", "ATR"] if use_uppercase else FEATURE_NAMES

    if isinstance(state_data, pd.DataFrame):
        if all(col in state_data.columns for col in target_features):
            X_input = state_data[target_features].iloc[[-1]]
        elif all(col in state_data.columns for col in ["Close", "High", "Low"]):
            df_feat = extract_uppercase_features(state_data["Close"], state_data["High"], state_data["Low"]) if use_uppercase else extract_continuous_features(state_data["Close"], state_data["High"], state_data["Low"])
            X_input = df_feat[target_features].iloc[[-1]]
        else:
            raise ValueError(f"Unsupported DataFrame format for Alpha Gate features: {state_data.columns}")
    elif isinstance(state_data, dict):
        if all(k in state_data for k in target_features):
            X_input = pd.DataFrame([{k: float(state_data[k]) for k in target_features}])
        elif all(k in state_data for k in ["closes", "highs", "lows"]):
            df_feat = extract_uppercase_features(state_data["closes"], state_data["highs"], state_data["lows"]) if use_uppercase else extract_continuous_features(state_data["closes"], state_data["highs"], state_data["lows"])
            X_input = df_feat[target_features].iloc[[-1]]
        elif all(k in state_data for k in ["Close", "High", "Low"]):
            df_feat = extract_uppercase_features(state_data["Close"], state_data["High"], state_data["Low"]) if use_uppercase else extract_continuous_features(state_data["Close"], state_data["High"], state_data["Low"])
            X_input = df_feat[target_features].iloc[[-1]]
        else:
            raise ValueError(f"Unsupported dictionary keys for Alpha Gate features: {list(state_data.keys())}")
    elif isinstance(state_data, (tuple, list)):
        if len(state_data) == 3 and all(hasattr(x, "__len__") for x in state_data):
            closes, highs, lows = state_data
            df_feat = extract_uppercase_features(closes, highs, lows) if use_uppercase else extract_continuous_features(closes, highs, lows)
            X_input = df_feat[target_features].iloc[[-1]]
        elif len(state_data) == 4:
            X_input = pd.DataFrame([dict(zip(target_features, [float(x) for x in state_data]))])
        else:
            raise ValueError(f"Unsupported tuple/list format for Alpha Gate input: len={len(state_data)}")
    else:
        raise TypeError(f"Unsupported state_data type for Alpha Gate prediction: {type(state_data)}")

    prediction = float(model.predict(X_input)[0])
    return prediction >= 0.001
