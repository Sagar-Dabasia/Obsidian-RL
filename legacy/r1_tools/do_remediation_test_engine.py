import os

path = "tests/test_portfolio_engine.py"
with open(path, "a") as f:
    f.write("\n\ndef test_path_maximum_drawdown_survives_recovery() -> None:\n")
    f.write("    eng = make_engine()\n")
    f.write("    eng.rebalance(1.0, 100.0)\n")
    f.write("    eng.mark_to_market(100.0)\n")
    f.write("    eng.mark_to_market(50.0)\n")
    f.write("    assert eng.state.current_drawdown_pct > 0.4\n")
    f.write("    assert eng.state.path_maximum_drawdown_pct == eng.state.current_drawdown_pct\n")
    f.write("    max_dd = eng.state.path_maximum_drawdown_pct\n")
    f.write("    eng.mark_to_market(120.0)\n")
    f.write("    assert eng.state.current_drawdown_pct == 0.0\n")
    f.write("    assert eng.state.path_maximum_drawdown_pct == max_dd\n")
