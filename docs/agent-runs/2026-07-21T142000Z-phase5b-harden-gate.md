# Agent Run Report — Phase 5b: Harden Alpha Gate Artifact Validation

## Meta

| Field | Value |
|---|---|
| **Model** | Antigravity |
| **Date (UTC)** | 2026-07-21 |
| **Branch** | `wip/phase5-alpha-gate-direction` |
| **Starting commit** | `18d7fb5a976b653bc49442f36e986ef1e28ae3c7` |
| **Task** | Phase 5b — Harden Alpha Gate artifact/input validation: predict_row shape/length/count checks; metadata JSON root, NaN/Inf, exact key set, created_utc_ms, SHA-256 format; save_gate pre-write validation |

---

## Working-tree status

**Before**: clean on `wip/phase5-alpha-gate-direction` at `18d7fb5`

**After**:
```
M  src/obsidian_rl/gate/alpha_gate.py
M  tests/test_alpha_gate.py
M  docs/AGENT_RUN_REPORT.md
M  docs/CODEX_HANDOFF.md
A  docs/agent-runs/2026-07-21T142000Z-phase5b-harden-gate.md
```

---

## Fixes

### 1. `AlphaGate.predict_row`
- Reject non-1D inputs: `"market_row must be 1-dimensional"`.
- Reject wrong feature count: `"exactly N values"`.
- Reject non-finite inputs (unchanged from Phase 5).
- Reject empty prediction arrays: `"empty"`.
- Reject multi-value predictions: `"N values.*exactly 1"`.

### 2. `_load_and_validate_meta`
- Reject malformed JSON → `GateCompatibilityError("malformed JSON: ...")`.
- Reject non-dict root (e.g. list) → `GateCompatibilityError("JSON object")`.
- Reject NaN/Infinity via `json.dumps(..., allow_nan=False)` → `"non-finite"`.
- Exact key set (`_REQUIRED_META_KEYS`) — any missing or extra → `"missing"` / `"extra"`.
- `created_utc_ms` must be non-bool `int >= 0`.
- `artifact_sha256` must be exactly 64 lowercase hex characters.

### 3. `save_gate`
- `_validate_gate_fields_for_save()` runs before writing: checks `horizon`, `round_trip_cost`, `schema_version`.
- Serialises with `allow_nan=False` to catch non-finite metadata.

---

## Verification Results

### Focused Tests (`tests/test_alpha_gate.py tests/test_labels.py`)
```
python -m pytest tests/test_alpha_gate.py tests/test_labels.py -q
..........................................................
58 passed in 1.89s
```

### Ruff
```
python -m ruff check src/obsidian_rl/gate/alpha_gate.py tests/test_alpha_gate.py
All checks passed!

python -m ruff format --check src/obsidian_rl/gate/alpha_gate.py tests/test_alpha_gate.py
2 files already formatted
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
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 67%]
.......................................................s................ [ 90%]
..............................                                           [100%]
314 passed, 1 skipped
```
