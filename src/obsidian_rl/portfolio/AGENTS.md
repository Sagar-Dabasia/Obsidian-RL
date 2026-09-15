# Portfolio AGENTS.md
These rules apply ONLY within src/obsidian_rl/portfolio/.
Root AGENTS.md invariants remain absolute; this file adds domain-specific constraints.

## Financial State Ownership
- PortfolioEngine is the single authoritative owner of portfolio state (cash, equity, positions, PnL).
- Ledger is the immutable audit trail; never modify committed ledger entries.
- No external component may directly mutate PortfolioEngine internals.

## Multi-Asset Consistency
- All asset-level state changes must go through PortfolioEngine methods.
- Cross-asset operations (rebalance, transfer) must be atomic or explicitly compensated.
- Restart/recovery must reconstruct identical state from ledger + config.

## Fail-Closed Invariants
- Negative cash -> FAIL (not overdraft).
- Position quantity sign mismatch with side -> FAIL.
- PnL != realized + unrealized -> FAIL.
- Fee/funding application must be deterministic and replayable.

## Paper Trading Only
- No live/Testnet order submission from portfolio/ledger code paths.
- No exchange API keys in this domain.
- All costs applied via CostModel; execution simulated by PortfolioEngine.

## No Legacy Imports
- Do not import from legacy/ or archived Cycle-1 portfolio logic.
- Graphify query "legacy portfolio" before touching this domain.
