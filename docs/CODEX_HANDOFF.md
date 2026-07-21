# Codex handoff

Updated: 2026-07-21

## Current branch and commit
- Branch: `wip/phase5-alpha-gate-direction`
- Starting commit: `f0418c5dc45bb7eff84bf42cfd1d02f411767d63`

## Status
Phase 5 — Alpha Gate Signed Directional Net Edge — **COMPLETE (verified & committed)**

See full run report: [docs/AGENT_RUN_REPORT.md](AGENT_RUN_REPORT.md)
Timestamped archive: [docs/agent-runs/2026-07-21T141000Z-phase5-alpha-gate-direction.md](agent-runs/2026-07-21T141000Z-phase5-alpha-gate-direction.md)

## What was implemented/fixed in Phase 5

### Signed directional label (`labels.py`)
- Added `signed_directional_net_edge(open_, horizon, round_trip_cost)`:
  `sign(gross) * max(abs(gross) - round_trip_cost, 0)` where `gross = log(open[t+1+h] / open[t+1])`.
- Correctly represents both long edge (`+gross - cost`) and short edge (`-(abs(gross) - cost)`).
- Sub-cost moves return exactly 0.
- Strict input validation: non-bool `int >= 1` horizon, finite non-bool non-negative cost, finite strictly-positive prices.
- Legacy `forward_executable_net_return` retained for compatibility only; not used for gate training.

### Gate schema v2 (`alpha_gate.py`)
- `GATE_SCHEMA_VERSION = "gate-schema-v2"`.
- `save_gate` persists: `gate_schema_version`, `target_name` (`signed-directional-net-edge-v1`), `feature_schema_version`, `features`, `horizon`, `round_trip_cost`, `artifact_sha256`.
- `load_gate` validates all 8 required fields; rejects legacy schema; validates horizon, cost, feature order, and SHA-256.
- `AlphaGate.predict_row` validates finite inputs and non-finite predictions.
- `AlphaGate.decide(row, margin)` returns `+1`/`-1`/`0` with validated non-negative margin.
- `build_training_frame` uses the new signed label.

### Gated strategies (`gated.py`)
- `GatedStrategy` and `GateDirectStrategy` use `gate.decide()` for validated direction; margin validated at construction time.

## Files changed
- `src/obsidian_rl/features/labels.py`
- `src/obsidian_rl/gate/alpha_gate.py`
- `src/obsidian_rl/strategies/gated.py`
- `tests/test_labels.py`
- `tests/test_alpha_gate.py`
- `docs/AGENT_RUN_REPORT.md`
- `docs/CODEX_HANDOFF.md`
- `docs/agent-runs/2026-07-21T141000Z-phase5-alpha-gate-direction.md`

## Verification Commands Run
- `python -m pytest tests/test_labels.py tests/test_alpha_gate.py -q`: **40 passed in 1.43s**
- `python -m ruff check ... (5 Phase 5 files)`: **All checks passed!**
- `python -m ruff format --check ... (5 Phase 5 files)`: **5 files already formatted**
- `python -m mypy src`: **Success (no issues found in 45 source files)**
- `python -m compileall -q src tests`: **Clean**
- `git diff --check`: **Clean**
- `python -m pytest -q`: **296 passed, 1 skipped**
