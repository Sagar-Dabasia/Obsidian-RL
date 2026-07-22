# Obsidian-RL Document Archive Manifest

This manifest records the formal reorganization and archiving of Obsidian-RL documentation into Research Cycle 01 (`archive/cycle_01/`) and Research Cycle 02 (`cycle_02/`) structures. Every move was executed via `git mv` to preserve complete Git history without deleting any file.

---

## Cycle 01 Archive (`docs/archive/cycle_01/`)

All completed Cycle 01 experiment reports, validation runs, architectural plans, and closeout registers have been archived under `docs/archive/cycle_01/`. **These documents represent historical evidence and retired hypotheses; they must not be silently re-tuned or re-run on identical historical periods.**

| Original Path | New Path | Classification | Reason for Classification |
|---|---|---|---|
| `docs/HISTORICAL_PILOT_01.md` | `docs/archive/cycle_01/reports/HISTORICAL_PILOT_01.md` | Cycle 1 | Historical pilot experiment report, protocol, and baseline evaluations. |
| `docs/PPO_PILOT_01.md` | `docs/archive/cycle_01/reports/PPO_PILOT_01.md` | Cycle 1 | PPO pilot experiment report, walk-forward results, and protocol specifications. |
| `docs/PPO_SEED_STABILITY_01.md` | `docs/archive/cycle_01/reports/PPO_SEED_STABILITY_01.md` | Cycle 1 | PPO seed stability pilot experiment evaluation report and protocol. |
| `docs/PPO_SEED_DIAGNOSTIC_01.md` | `docs/archive/cycle_01/reports/PPO_SEED_DIAGNOSTIC_01.md` | Cycle 1 | PPO seed stability diagnostic analysis across seeds 42, 7, 23, 101, and 202. |
| `docs/PPO_TURNOVER_SCREEN_01.md` | `docs/archive/cycle_01/reports/PPO_TURNOVER_SCREEN_01.md` | Cycle 1 | PPO turnover regularization parameter screen experiment report and protocol. |
| `docs/PPO_SEED_ENSEMBLE_01.md` | `docs/archive/cycle_01/reports/PPO_SEED_ENSEMBLE_01.md` | Cycle 1 | PPO five-seed deterministic median ensemble screen experiment report. |
| `docs/PPO_REPLICATION_2020_2022.md` | `docs/archive/cycle_01/reports/PPO_REPLICATION_2020_2022.md` | Cycle 1 | Frozen PPO historical replication across 2020-2022 and confirmation window. |
| `docs/ALPHA_GATE_PILOT_01.md` | `docs/archive/cycle_01/reports/ALPHA_GATE_PILOT_01.md` | Cycle 1 | Alpha Gate LightGBM directional net-edge historical pilot report. |
| `docs/AUDIT.md` | `docs/archive/cycle_01/reports/AUDIT.md` | Cycle 1 | Legacy Q-learning repository audit report from initial system intake. |
| `docs/FINAL_SYSTEM_AUDIT.md` | `docs/archive/cycle_01/reports/FINAL_SYSTEM_AUDIT.md` | Cycle 1 | Final system audit verification report across Cycle 01 phases 0 through 12. |
| `docs/VALIDATION_REPORT.md` | `docs/archive/cycle_01/reports/VALIDATION_REPORT.md` | Cycle 1 | Phase 8 walk-forward validation report and 5-fold sensitivity summary. |
| `docs/REVIEW.md` | `docs/archive/cycle_01/reports/REVIEW.md` | Cycle 1 | Multi-agent adversarial correctness review report and defect resolution log. |
| `docs/AGENT_RUN_REPORT.md` | `docs/archive/cycle_01/reports/AGENT_RUN_REPORT.md` | Cycle 1 | Readiness agent run verification and nested walk-forward protocol test report. |
| `docs/PHASE1_VERIFICATION_REPORT.md` | `docs/archive/cycle_01/reports/PHASE1_VERIFICATION_REPORT.md` | Cycle 1 | Phase 1 repository verification and audit findings report. |
| `docs/PHASE7_AUDIT_REPORT.md` | `docs/archive/cycle_01/reports/PHASE7_AUDIT_REPORT.md` | Cycle 1 | Phase 7 live accounting and parity verification report. |
| `docs/ROADMAP.md` | `docs/archive/cycle_01/plans/ROADMAP.md` | Cycle 1 | Phase 0 through 12 development roadmap and completion checklist. |
| `docs/ARCHITECTURE.md` | `docs/archive/cycle_01/research/ARCHITECTURE.md` | Cycle 1 | Single-asset BTCUSDT 15-minute PPO system architecture specification. |
| `docs/DECISIONS.md` | `docs/archive/cycle_01/research/DECISIONS.md` | Cycle 1 | Architecture Decision Records (ADR-001 through ADR-003) for Cycle 01. |
| `docs/CODEX_HANDOFF.md` | `docs/archive/cycle_01/research/CODEX_HANDOFF.md` | Cycle 1 | Codex research handoff register and readiness verification summary. |
| `docs/SESSION_HANDOFF.md` | `docs/archive/cycle_01/research/SESSION_HANDOFF.md` | Cycle 1 | Session handoff closeout register documenting Cycle 01 phase completions. |
| `docs/PHASE1_CODE_REVIEW.patch` | `docs/archive/cycle_01/research/PHASE1_CODE_REVIEW.patch` | Cycle 1 | Code review patch artifact generated during Cycle 01 Phase 1 verification. |

---

## Cycle 02 Active Documentation (`docs/cycle_02/`)

Active specifications, architectural blueprints, and research registers governing Obsidian-RL Research Cycle 02 (Cross-Asset Multi-Engine Platform) are organized under `docs/cycle_02/`.

| Original Path | New Path | Classification | Reason for Classification |
|---|---|---|---|
| `docs/CROSS_ASSET_ARCHITECTURE.md` | `docs/cycle_02/architecture/CROSS_ASSET_ARCHITECTURE.md` | Cycle 2 | Active cross-asset multi-engine system architecture specification (Phases 1-12). |
| `docs/DATA_SOURCE_REGISTER.md` | `docs/cycle_02/decisions/DATA_SOURCE_REGISTER.md` | Cycle 2 | Active data provider governance decisions, SLA rules, and contract policies. |
| `docs/CYCLE_02_RESEARCH_REGISTER.md` | `docs/cycle_02/research/CYCLE_02_RESEARCH_REGISTER.md` | Cycle 2 | Active research hypothesis definition, window freezing protocol, and retirements. |
| `docs/CYCLE_02_MASTER_PLAN.md` | `docs/cycle_02/reports/CYCLE_02_MASTER_PLAN.md` | Cycle 2 | Master implementation plan detailing the 12 fixed engineering phases. |

---

## Unmoved Repository Guide Files (`docs/`)

The following general repository documentation remains directly under `docs/` to maintain root references (`README.md`):
- `docs/development.md`: Clean-machine setup guide, CI test instructions, and packaging dependencies (`python -m pip install -e .[dev,rl,gate,dashboard]`).
