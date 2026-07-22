# Agent Run Report — Phase 5: Alpha Gate Signed Directional Net Edge

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase5-alpha-gate-direction` |
| **Starting commit** | `f0418c5dc45bb7eff84bf42cfd1d02f411767d63` |
| **Task** | Phase 5 — Correct Alpha Gate directional target to `sign(gross) * max(abs(gross) - cost, 0)`, add gate schema v2, strict artifact validation, and signed prediction logic |

---

## Working-tree status

**Before**: clean on `wip/phase4-holdout-enforcement` at `f0418c5dc45bb7eff84bf42cfd1d02f411767d63`

**After** (Phase 5 source/test/docs):
```
M  src/obsidian_rl/features/labels.py
M  src/obsidian_rl/gate/alpha_gate.py
M  src/obsidian_rl/strategies/gated.py
M  tests/test_labels.py
M  tests/test_alpha_gate.py
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
A  docs/agent-runs/2026-07-21T141000Z-phase5-alpha-gate-direction.md
```

---

## Files modified

### Production
- `src/obsidian_rl/features/labels.py`
- `src/obsidian_rl/gate/alpha_gate.py`
- `src/obsidian_rl/strategies/gated.py`

### Tests
- `tests/test_labels.py`
- `tests/test_alpha_gate.py`

---

## Defect & Resolution

### Problem — Wrong directional target
The legacy label `log(exit/entry) - cost` treats all gross log-returns identically regardless of direction. A negative gross return (falling prices) subtracted by cost gives a more-negative number, which was interpreted as a profitable short signal — incorrect, because the short net return is `-gross - cost`, not `gross - cost`.

### Resolution

**`labels.py`** — added `signed_directional_net_edge(open_, horizon, round_trip_cost)`:
```
gross = log(open[t+1+h] / open[t+1])
label = sign(gross) * max(abs(gross) - round_trip_cost, 0)
```
- Rising prices: `+gross - cost` (long edge)
- Falling prices: `-(abs(gross) - cost)` (short edge)
- `|gross| <= cost`: exactly 0 (no tradeable edge either way)

Added strict validation: `horizon` must be non-bool `int >= 1`; `round_trip_cost` must be finite non-bool numeric `>= 0`; all prices must be finite and strictly positive. Legacy `forward_executable_net_return` retained for compatibility but not used for gate training.

**`alpha_gate.py`** — gate schema version bumped to `gate-schema-v2`:
- `save_gate` now persists: `gate_schema_version`, `target_name` (`signed-directional-net-edge-v1`), `feature_schema_version`, `features`, `horizon`, `round_trip_cost`, `artifact_sha256`.
- `load_gate` validates all 8 required metadata fields; rejects legacy `gate_schema_version`; rejects wrong `target_name`; validates `horizon`, `round_trip_cost`, reordered features, and SHA-256 checksum.
- `AlphaGate.predict_row` validates finite inputs and rejects non-finite predictions.
- `AlphaGate.decide(row, margin)` returns `+1`/`-1`/`0` with validated non-negative finite margin.
- `build_training_frame` now uses `signed_directional_net_edge` (not the legacy label).

**`gated.py`** — uses `gate.decide()` for consistent validated prediction-to-direction; margin validation moved to constructor for both `GatedStrategy` and `GateDirectStrategy`.

---

## Verification Results

### Focused Unit Tests (`tests/test_labels.py tests/test_alpha_gate.py`)
```
python -m pytest tests/test_labels.py tests/test_alpha_gate.py -q
........................................
40 passed in 1.43s
```

### Ruff Linter & Formatting
```
python -m ruff check ... (all 5 Phase 5 files)
All checks passed!

python -m ruff format --check ... (all 5 Phase 5 files)
5 files already formatted
```

### Mypy
```
python -m mypy src
Success: no issues found in 45 source files
```

### Compileall & git diff --check
```
python -m compileall -q src tests   → clean
git diff --check                    → clean (LF warnings only)
```

### Full Suite
```
python -m pytest -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
.....................................s.................................. [ 96%]
............                                                             [100%]
296 passed, 1 skipped in ~16s
```
