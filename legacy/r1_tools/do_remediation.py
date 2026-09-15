import os
import re

engine_path = "src/obsidian_rl/portfolio/engine.py"
with open(engine_path, "r") as f:
    engine_code = f.read()

enums = """
from enum import Enum

class MarketModel(Enum):
    SPOT = "SPOT"
    PERPETUAL = "PERPETUAL"
    FOREX_MARGIN = "FOREX_MARGIN"

class ExposurePolicy(Enum):
    LONG_FLAT = "LONG_FLAT"
    BIDIRECTIONAL = "BIDIRECTIONAL"
"""
engine_code = engine_code.replace("from dataclasses import dataclass, field, replace", enums + "\nfrom dataclasses import dataclass, field, replace")

engine_state_repl = """    peak_equity: float = field(default=0.0)
    current_drawdown_pct: float = 0.0
    path_maximum_drawdown_pct: float = 0.0

    def unrealized_pnl(self, price: float) -> float:"""
engine_code = engine_code.replace("    peak_equity: float = field(default=0.0)\n\n    def unrealized_pnl(self, price: float) -> float:", engine_state_repl)

mark_to_market_old = """    def mark_to_market(self, price: float) -> PortfolioState:
        \"\"\"Update peak equity; return a snapshot copy of state.\"\"\"
        equity = self.state.net_equity(price)
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        dd = self.state.drawdown(price)
        if dd > self.path_maximum_drawdown_pct:
            self.path_maximum_drawdown_pct = dd
        return replace_state_copy(self.state)"""

mark_to_market_new = """    def mark_to_market(self, price: float) -> PortfolioState:
        \"\"\"Update peak equity; return a snapshot copy of state.\"\"\"
        equity = self.state.net_equity(price)
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        dd = self.state.drawdown(price)
        self.state.current_drawdown_pct = dd
        if dd > self.state.path_maximum_drawdown_pct:
            self.state.path_maximum_drawdown_pct = dd
        return replace_state_copy(self.state)"""
engine_code = engine_code.replace(mark_to_market_old, mark_to_market_new)
engine_code = engine_code.replace("        self.path_maximum_drawdown_pct = 0.0\n", "")

with open(engine_path, "w") as f:
    f.write(engine_code)
