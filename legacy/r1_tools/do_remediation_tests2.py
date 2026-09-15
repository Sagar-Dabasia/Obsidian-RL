import os

# Fix 1: TrendSignal dummy initialization
dummy_trend_signal_args = 'direction="LONG", score=1.0, volatility_20d=0.01, latest_close=100.0, signal_timestamp_utc=1000, reason="test", input_row_hash="hash", config_identity="ident"'

path_tests = "tests/evaluation/test_trend_backtest.py"
with open(path_tests, "r") as f:
    code = f.read()

code = code.replace('return TrendSignal(direction="LONG")', f'return TrendSignal({dummy_trend_signal_args})')

# Fix 2: VenueOutage initialization dummy args
old_outage = 'OutageRegistry(entries=(VenueOutage("BINANCE_SPOT", 1000, 2000, "1"),))'
new_outage = 'OutageRegistry(entries=(VenueOutage("BINANCE_SPOT", 1000, 2000, "1", 3000, "hash", "test", ["BTCUSDT"], True),))'
code = code.replace(old_outage, new_outage)

with open(path_tests, "w") as f:
    f.write(code)


# Fix 3: test_short_disabled
path_engine = "tests/test_portfolio_engine.py"
with open(path_engine, "r") as f:
    code_eng = f.read()

old_short = """def test_short_disabled() -> None:
    eng = PortfolioEngine(PortfolioConfig(initial_cash=10_000.0, allow_short=False), CM)
    r = eng.rebalance(-1.0, 100.0)
    assert r.approved_target == 0.0
    assert eng.state.qty == 0.0"""

new_short = """def test_short_disabled() -> None:
    eng = PortfolioEngine(PortfolioConfig(initial_cash=10_000.0, allow_short=False), CM)
    import pytest
    with pytest.raises(ValueError, match="short exposure disabled"):
        eng.rebalance(-1.0, 100.0)"""

code_eng = code_eng.replace(old_short, new_short)

with open(path_engine, "w") as f:
    f.write(code_eng)
