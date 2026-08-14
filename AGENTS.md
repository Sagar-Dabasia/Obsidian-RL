# Obsidian-RL agent rules

## Scope and safety
- Work on one bounded defect at a time.
- Inspect relevant files before editing.
- Never read or print `.env` or other secrets.
- Never connect to Binance or place exchange orders, including Testnet orders.
- Never run full training unless explicitly requested.
- Never load unidentified pickle or joblib artifacts.
- Do not alter unrelated files.
- Stop rather than inventing APIs, data, or results.

## Correctness
- Never use future data in features, labels, normalization, or selection.
- Never silently substitute synthetic market data; fail explicitly.
- Keep trading, training, evaluation, and paper-execution behaviour consistent.
- Do not weaken tests, costs, or benchmarks to improve reported numbers.
- Do not claim profitability or represent a single result as evidence of an edge.

## Validation and reporting
- Add focused tests for every fix.
- Run only relevant tests first.
- Run the complete test suite only before finalizing a patch.
- Report actual command results.
- Do not paste full source files, full diffs, or long logs.
- Use concise summaries.

## Version control
- Do not commit or push unless explicitly requested.
- Never rewrite Git history or run destructive Git reset commands.

## Graphify Architecture Mapping
- Query the active graph before editing.
- Never use the full graph to select active implementation.
- Archived/legacy nodes are historical evidence only.
- Inspect actual source before changing it.
- Regenerate graphs only when explicitly requested.
- Graphify never replaces GitHub diff review.

