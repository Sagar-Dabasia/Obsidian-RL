"""Streamlit dashboard over the ledger. Run:
    .venv\\Scripts\\python.exe -m streamlit run src/obsidian_rl/dashboard/app.py

Every number shown is SIMULATED paper performance. Sessions are never merged.
"""

from datetime import UTC, datetime

import streamlit as st

from obsidian_rl.config import get_settings
from obsidian_rl.dashboard.queries import (
    closed_trade_events,
    equity_and_drawdown,
    get_run_closure,
    kpis,
    list_run_summaries,
    run_frame,
    warnings_for_run,
)


def _fmt_ts(ms: int | None) -> str:
    if ms is None:
        return "running"
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def main() -> None:
    st.set_page_config(page_title="Obsidian-RL (paper)", layout="wide")
    st.title("Obsidian-RL — simulated paper performance")
    st.caption(
        "Research software. All results are simulated paper execution on public market "
        "data with assumed costs. Nothing here is financial advice or a profit claim."
    )
    settings = get_settings()
    runs = list_run_summaries(settings.ledger_path)
    if not runs:
        st.warning(f"No runs found in {settings.ledger_path}")
        return

    labels = {
        f"{r.run_id} · {r.strategy_id} · {r.mode} · {_fmt_ts(r.started_at_ms)}": r for r in runs
    }
    choice = st.sidebar.selectbox("Session (never merged)", list(labels))
    run = labels[choice]

    st.subheader(f"Run {run.run_id}")
    meta_cols = st.columns(5)
    meta_cols[0].metric("Strategy", run.strategy_id)
    meta_cols[1].metric("Model", run.model_id or "—")
    meta_cols[2].metric("Mode", run.mode)
    meta_cols[3].metric("Started", _fmt_ts(run.started_at_ms))
    meta_cols[4].metric("Ended", _fmt_ts(run.ended_at_ms))

    frame = run_frame(settings.ledger_path, run.run_id)
    closure = get_run_closure(settings.ledger_path, run.run_id)
    for w in warnings_for_run(
        frame, interval=settings.interval, run_ended=run.ended_at_ms is not None
    ):
        st.warning(w)
    if frame.empty and closure is None:
        return

    k = kpis(frame, run.initial_cash, closure=closure)
    row1 = st.columns(6)
    row1[0].metric("Net equity", f"${k['net_equity']:,.2f}", f"{k['net_return_pct']:+.2f}%")
    row1[1].metric("Cash", f"${k['cash']:,.2f}")
    row1[2].metric("Position (BTC)", f"{k['position_qty']:.6f}")
    row1[3].metric("Exposure", f"{k['executed_target']:+.2f}")
    row1[4].metric("Realized P&L", f"${k['realized_pnl']:,.2f}")
    row1[5].metric("Unrealized P&L", f"${k['unrealized_pnl']:,.2f}")
    row2 = st.columns(6)
    row2[0].metric("Fees", f"${k['fees']:,.2f}")
    row2[1].metric("Spread", f"${k['spread']:,.2f}")
    row2[2].metric("Slippage", f"${k['slippage']:,.2f}")
    row2[3].metric("Funding", f"${k['funding']:,.2f}")
    row2[4].metric("Turnover", f"${k['turnover']:,.0f}")
    row2[5].metric("Trades", f"{int(k['trade_count'])}")

    curves = equity_and_drawdown(frame, closure=closure)
    curves["time"] = curves["candle_open_ms"].apply(
        lambda ms: datetime.fromtimestamp(ms / 1000, tz=UTC)
    )
    st.subheader("Equity (this session only)")
    st.line_chart(curves.set_index("time")["net_equity"])
    st.subheader("Drawdown")
    st.area_chart(curves.set_index("time")["drawdown"])

    st.subheader("Realized P&L events (reversal-aware)")
    st.dataframe(closed_trade_events(frame, closure=closure).tail(25))


if __name__ == "__main__":
    main()
