"""Streamlit Web Dashboard for Monitoring Paper-Trading Performance.

This lightweight quantitative dashboard reads and parses real-time execution logs
from `live_trades.log` into a structured `pandas.DataFrame`. It displays top-level
institutional metric cards (`st.metric`), renders interactive account balance
trajectories over time, provides sidebar controls for refresh intervals and manual
re-parsing, and exhibits a bottom table summarizing the last 10 executed trade actions.
"""

from __future__ import annotations

from pathlib import Path
import re
import time
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Quantitative Paper-Trading Dashboard",
    page_icon="📈",
    layout="wide",
)


def parse_trades_log(log_path: str | Path = "live_trades.log") -> pd.DataFrame:
    """Reads and parses `live_trades.log` into a structured pandas DataFrame.

    Handles missing file exceptions, empty logs, and malformed entries gracefully.

    Parameters
    ----------
    log_path : str | Path, default="live_trades.log"
        Path to the paper trading log file.

    Returns
    -------
    pd.DataFrame
        DataFrame containing parsed columns: `Step`, `Timestamp`, `Asset`, `Action`,
        `Price`, `PnL`, `TxCost`, `Balance`.
    """
    path = Path(log_path)
    columns = ["Step", "Timestamp", "Asset", "Action", "Price", "PnL", "TxCost", "Balance"]
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)

    records: list[dict[str, Any]] = []
    current_asset: str = "BTC-USD"

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_str = line.strip()
                if "Asset:" in line_str:
                    parts = line_str.split("Asset:")
                    if len(parts) > 1:
                        asset_part = parts[1].split("|")[0].strip()
                        if asset_part:
                            current_asset = asset_part

                if "Step:" in line_str and "Time:" in line_str and "Balance:" in line_str:
                    try:
                        step_match = re.search(r"Step:\s*(\d+)", line_str)
                        time_match = re.search(r"Time:\s*([^\s|]+)", line_str)
                        price_match = re.search(r"Price:\s*\$?\s*([0-9.,+-]+)", line_str)
                        action_match = re.search(r"Action:\s*([^|]+)", line_str)
                        pnl_match = re.search(r"PnL:\s*\$?\s*([0-9.,+-]+)", line_str)
                        tx_match = re.search(r"TxCost:\s*\$?\s*([0-9.,+-]+)", line_str)
                        bal_match = re.search(r"Balance:\s*\$?\s*([0-9.,+-]+)", line_str)

                        if step_match and time_match and bal_match:
                            records.append({
                                "Step": int(step_match.group(1)),
                                "Timestamp": time_match.group(1),
                                "Asset": current_asset,
                                "Action": action_match.group(1).strip() if action_match else "Flat (1)",
                                "Price": float(price_match.group(1).replace(",", "")) if price_match else 0.0,
                                "PnL": float(pnl_match.group(1).replace(",", "")) if pnl_match else 0.0,
                                "TxCost": float(tx_match.group(1).replace(",", "")) if tx_match else 0.0,
                                "Balance": float(bal_match.group(1).replace(",", "")),
                            })
                    except Exception:
                        continue
    except Exception:
        return pd.DataFrame(columns=columns)

    if not records:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(records)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    return df


def compute_closed_trades_metrics(df: pd.DataFrame) -> tuple[int, float]:
    """Calculates total closed trades count and win rate from closed positions.

    Parameters
    ----------
    df : pd.DataFrame
        Parsed execution log dataframe.

    Returns
    -------
    tuple[int, float]
        A tuple containing `(total_closed_trades, win_rate_percentage)`.
    """
    if df.empty:
        return 0, 0.0

    closed_trade_pnls: list[float] = []
    active_trade_pnl: float = 0.0
    in_position: bool = False

    for _, row in df.iterrows():
        action_str = str(row.get("Action", ""))
        pnl_val = float(row.get("PnL", 0.0))
        tx_val = float(row.get("TxCost", 0.0))

        is_active = "Long" in action_str or "Short" in action_str or "(0)" in action_str or "(2)" in action_str

        if is_active:
            in_position = True
            active_trade_pnl += pnl_val - tx_val
        else:
            if in_position:
                closed_trade_pnls.append(active_trade_pnl - tx_val)
                active_trade_pnl = 0.0
                in_position = False

    # If currently in a position right at the end, optionally track or keep strictly as closed trades
    total_closed = len(closed_trade_pnls)
    if total_closed == 0:
        return 0, 0.0

    winning_trades = sum(1 for p in closed_trade_pnls if p > 0.0)
    win_rate = (winning_trades / total_closed) * 100.0
    return total_closed, win_rate


def render_dashboard() -> None:
    """Renders the Streamlit quantitative monitoring dashboard."""
    st.title("📈 Institutional RL Paper-Trading Dashboard")

    # Sidebar controls
    st.sidebar.header("⚙️ Dashboard Controls")
    log_file_input = st.sidebar.text_input("Log File Path", value="live_trades.log")
    refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", min_value=1, max_value=60, value=5)
    auto_refresh = st.sidebar.checkbox("Enable Auto-Refresh", value=False)
    manual_refresh = st.sidebar.button("🔄 Refresh / Re-parse Log", use_container_width=True)

    if manual_refresh:
        st.rerun()

    # Parse execution logs
    df = parse_trades_log(log_file_input)

    # Top-level metric cards
    st.subheader("📊 Key Performance Indicators")
    col1, col2, col3, col4 = st.columns(4)

    if not df.empty:
        initial_balance: float = float(df["Balance"].iloc[0] - df["PnL"].iloc[0] + df["TxCost"].iloc[0])
        if initial_balance <= 0.0:
            initial_balance = 10000.0
        current_balance: float = float(df["Balance"].iloc[-1])
        cumulative_pnl: float = current_balance - initial_balance
        cumulative_return_pct: float = (cumulative_pnl / initial_balance) * 100.0

        total_closed_trades, win_rate = compute_closed_trades_metrics(df)
        total_trades_display = total_closed_trades if total_closed_trades > 0 else len(df[df["Action"].str.contains("Long|Short|0|2", case=False, na=False)])

        col1.metric("Total Trades", f"{total_trades_display}")
        col2.metric("Current Balance", f"${current_balance:,.2f}", f"{cumulative_pnl:+,.2f} USD")
        col3.metric("Cumulative Return %", f"{cumulative_return_pct:+.2f}%")
        col4.metric("Win Rate (Closed Trades)", f"{win_rate:.1f}%")
    else:
        col1.metric("Total Trades", "0")
        col2.metric("Current Balance", "$10,000.00", "0.00 USD")
        col3.metric("Cumulative Return %", "0.00%")
        col4.metric("Win Rate (Closed Trades)", "0.0%")
        st.warning(f"No valid trading data found in `{log_file_input}`. Ensure `live_trader.py` is actively writing records.")

    st.divider()

    # Interactive line chart of virtual account balance over time
    st.subheader("📈 Virtual Account Balance Over Time")
    if not df.empty and "Timestamp" in df.columns and not df["Timestamp"].isna().all():
        chart_data = df.set_index("Timestamp")[["Balance"]]
        st.line_chart(chart_data, use_container_width=True)

        # Optional matplotlib analytical plot breakdown inside expander per institutional standards
        with st.expander("📉 View Analytical Matplotlib PnL & Balance Trajectory"):
            fig, ax1 = plt.subplots(figsize=(10, 4))
            ax1.plot(df["Timestamp"], df["Balance"], color="#1f77b4", label="Account Balance ($)", linewidth=1.8)
            ax1.set_xlabel("Timestamp")
            ax1.set_ylabel("Balance (USD)", color="#1f77b4")
            ax1.tick_params(axis="y", labelcolor="#1f77b4")
            ax1.grid(True, linestyle="--", alpha=0.5)

            ax2 = ax1.twinx()
            ax2.bar(df["Timestamp"], df["PnL"], color="#2ca02c", alpha=0.3, label="Step PnL ($)", width=0.0001)
            ax2.set_ylabel("Step PnL (USD)", color="#2ca02c")
            ax2.tick_params(axis="y", labelcolor="#2ca02c")

            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
    else:
        st.info("Insufficient timestamp data to render balance chart.")

    st.divider()

    # Data table of last 10 executed trade actions
    st.subheader("📜 Last 10 Executed Trade Actions")
    if not df.empty:
        recent_trades = df[["Timestamp", "Asset", "Action", "Price", "Balance"]].tail(10).copy()
        recent_trades["Timestamp"] = recent_trades["Timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(
            recent_trades.reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No trade actions recorded yet.")

    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    render_dashboard()
