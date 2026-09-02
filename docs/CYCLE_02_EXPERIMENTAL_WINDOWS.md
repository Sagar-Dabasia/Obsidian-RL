# Cycle 02 Experimental Windows — Preregistered Freeze

**Status**: FROZEN (do not modify after commitment)
**Branch**: `research/cycle-02-trend-pilot-02`
**Date**: 2026-09-01
**Context**: **This is the FIRST FORMAL Cycle 2 calendar freeze.** It occurred AFTER Phase 4C/4D data access/inspection; the original Phase-3 sequencing requirement (freeze before any Cycle 2 data access) was MISSED. Previous Phase 4 results remain classified under their existing reports; they are NOT retroactively claimed to be preregistered under these windows. Boundaries are prospectively immutable from this freeze onward.

---

## 1. Frozen Window Intervals (Half-Open, UTC)

| Window | Interval | Purpose |
|--------|----------|---------|
| **DEV_TRAIN** | `[2020-01-01T00:00:00Z, 2025-07-01T00:00:00Z)` | Engine design, indicator validation, Phase 9 ML cross-validation. Uses already-exposed history; no fresh-OOS claims. |
| **OUTER_VAL** | `[2025-07-01T00:00:00Z, 2026-03-01T00:00:00Z)` | Walk-forward fold evaluation, pass/fail per completed engine phase. Begins after known repository exposure through 2025-06-30. |
| **CONFIRMATION** | `[2026-03-01T00:00:00Z, 2026-07-01T00:00:00Z)` | One-time verification of finalized composite (Phase 8/9) before paper trading. Distinct and one-time. |
| **FINAL_HOLDOUT** | `[2026-07-01T00:00:00Z, 2027-01-01T00:00:00Z)` | Ultimate cross-cycle benchmark. **STRICTLY LOCKED** — no access during Cycle 02, including paper trading. |

**Boundaries may NEVER move after this preregistration.**
Any modification to this file after commit = protocol violation.

---

## 2. Rationale

| Window | Rationale |
|--------|-----------|
| **DEV_TRAIN** | Intentionally uses already-exposed history (Cycle 1: 2020–2022 replication; Cycle 1: 2023–2025 screening; Phase 4C/4D: 2020–2024 evaluation; 2025-05-27 to 2025-06-30 confirmation exposure). No fresh-OOS claims permitted. |
| **OUTER_VAL** | Starts at `2025-07-01T00:00:00Z`, immediately after the last known exposed date (`2025-06-30`). No overlap with previously inspected periods. |
| **CONFIRMATION** | Isolated 4-month window after OUTER_VAL. One-time use only. No partial-window peeking. |
| **FINAL_HOLDOUT** | 6-month fully inaccessible window. No script, tool, or person may load, query, plot, or evaluate during Cycle 02. Not used during Phase 11 paper trading. Cross-cycle reserved benchmark. |

---

## 3. Warm-Up / Historical Bars Before DEV_TRAIN

Historical bars before `2020-01-01T00:00:00Z` may be used **ONLY** for causal indicator initialization where required (e.g., EMA warm-up, volatility window seeding).

**Constraints**:
- Must never contribute scored returns, selection, or fitness evaluation.
- No future leakage (no look-ahead from post-DEV_TRAIN into warm-up).
- Known exposure: Phase 4C/4D used warm-up starting `2019-08-15T00:00:00Z` (721 bars required, 590 available after standard exclusions). This warm-up period is documented as already exposed and must not be treated as pristine.

---

## 4. Product / Market Model Rule (Phase 4D Invalidation Guard)

**Every experiment must preregister exactly ONE product type before any data is downloaded:**

| Product Type | Required Declaration |
|--------------|----------------------|
| **Binance Spot** | Signal data, execution model, costs, and funding MUST match spot market assumptions. No perpetual funding. |
| **Binance USD-M Perpetual** | Signal data, execution model, costs, and funding MUST match perpetual market assumptions. Funding is REQUIRED when applicable. |

**Forbidden**: Silent spot→perpetual substitution. No mixed-product evaluation within a single experiment. The Phase 4D invalidation (spot data run as perpetual+BIDIRECTIONAL) will be rejected by sentinel checks.

---

## 5. OUTER_VAL Access Protocol

| Rule | Enforcement |
|------|-------------|
| Parameters/hypothesis frozen before first OUTER_VAL access | `CYCLE_02_EXPERIMENTAL_WINDOWS.md` must be committed before any OUTER_VAL download |
| No tuning from OUTER_VAL results | Sentinel checks task_scope for new parameter commits after OUTER_VAL access |
| One predetermined candidate per family enters OUTER_VAL | Research log must name candidate before OUTER_VAL run |
| Failed candidate cannot be retuned on OUTER_VAL under same hypothesis | `FAILED_CANDIDATE` status blocks re-entry without new hypothesis |
| Negative results preserved | All OUTER_VAL runs logged with full metrics; no deletion |

---

## 6. CONFIRMATION Protocol

| Rule | Enforcement |
|------|-------------|
| Do not access until required OUTER_VAL gates pass | `tools/task_scope_sentinel.py` blocks CONFIRMATION access if OUTER_VAL criteria unmet |
| Single finalized composite only | Only the exact configuration that passed OUTER_VAL may enter CONFIRMATION |
| No partial-window peeking | CONFIRMATION window accessed exactly once, in full, after all prior gates |

---

## 7. FINAL_HOLDOUT Access Block

| Rule | Enforcement |
|------|-------------|
| No script/tool/person may load, query, plot, or evaluate FINAL_HOLDOUT during Cycle 02 | Sentinel + data-layer guards block any `store.read` / query overlapping `[2026-07-01T00:00:00Z, 2027-01-01T00:00:00Z)` |
| Do not inspect currently accrued portion | Even as real time progresses into this window, no evaluation permitted |
| Do not use during Phase 11 paper trading | Phase 11 operates on live market time; FINAL_HOLDOUT remains the cross-cycle reserved benchmark |

---

## 8. Phase 11 Paper Trading Eligibility

Phase 11 paper trading eligibility requires:
1. Phases 7–10 complete.
2. Finalized system passes authorized OUTER_VAL gates.
3. One-time CONFIRMATION passes.
4. All governance gates (Financial + Red Team + Release) pass.

**FINAL_HOLDOUT remains completely sealed during Cycle 2 INCLUDING Phase 11 paper trading.** Its calendar end does NOT automatically authorize access. Any future FINAL_HOLDOUT opening requires separate explicit governance outside Cycle 2 development/paper trading.

---

## 9. Governance References

- `docs/cycle_02/research/CYCLE_02_RESEARCH_REGISTER.md` — Four-tier policy
- `docs/cycle_02/reports/STRATEGY_RESEARCH_PLAN.md` — Strategy research plan (updated to reference this document)
- `docs/cycle_02/reports/PHASE_04D_CRYPTO_TREND_ROBUSTNESS.md` — Phase 4D invalidation record
- `tools/task_scope_sentinel.py` — Window enforcement

---

## 10. Invariants (Non-Negotiable)

- Paper trading only — no live/Testnet/private order capability
- No synthetic/fabricated data
- No future leakage in features, labels, normalization, or selection
- No holdout peeking (CONFIRMATION and FINAL_HOLDOUT locked)
- No boundary shifting — these dates frozen by this preregistration
- Realistic market-specific costs (per product declaration)
- Next-bar/causal execution timing only
- Centralized accounting/state (PortfolioEngine owns all position state)
- RiskEngine remains read-only gate
- Preserve all negative evidence (failed candidates logged)
- No retired Cycle 1 revival (Alpha Gate, 15m PPO, seed ensembles)
- No trading/financial production changes

---

## 11. Sequencing Governance Note

**This is the FIRST FORMAL Cycle 2 calendar freeze.** It occurred AFTER Phase 4C/4D data access/inspection; the original Phase-3 sequencing requirement (freeze before any Cycle 2 data access) was MISSED. This is a confirmed sequencing/governance defect.

- Previous Phase 4 results remain classified under their existing reports; they are NOT retroactively claimed to be preregistered under these windows.
- Boundaries are prospectively immutable from this freeze onward.
- DEV_TRAIN is intentionally contaminated/exposed development history.
- OUTER_VAL/CONFIRMATION may be treated as fresh only to the extent repository evidence shows no prior value inspection.
- Prior Cycle 1 reservation of 2025-07+ is explicitly acknowledged.

---

**End of Preregistration** — This document is committed to version control. Any subsequent modification to window intervals is a protocol violation requiring full governance review.