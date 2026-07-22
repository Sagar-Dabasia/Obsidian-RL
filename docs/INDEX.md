# Obsidian-RL Documentation Index

This index provides a centralized navigation directory for all Obsidian-RL documentation, divided cleanly between our active research (`cycle_02/`) and our preserved historical archive (`archive/cycle_01/`).

---

## Documentation Layout & Principles
Obsidian-RL documentation is structured around scientific research cycles. Every cycle's architectural plans, data contracts, and empirical experiment reports are isolated into their respective directories:
- `cycle_02/`: Active specifications, designs, and research logs for our Cross-Asset Multi-Engine Platform.
- `archive/cycle_01/`: Preserved historical reports, audit logs, and experimental records from our retired single-asset 15-minute PPO and Alpha Gate research.
- Root (`docs/`): General repository-level guides (`INDEX.md`, `development.md`, and `DOCUMENT_ARCHIVE_MANIFEST.md`).

> **CRITICAL ARCHIVAL CONFIRMATION & SAFETY WARNING**
> - **Preserved, Not Deleted**: Archiving in Obsidian-RL means **100% preservation** via Git history (`git mv`). No historical report, audit finding, or experimental dataset has been deleted or rewritten.
> - **No Silent Re-Running of Failed Hypotheses**: All hypotheses preserved under `archive/cycle_01/` (including single-policy 15-minute BTCUSDT PPO, PPO median ensembles, and standalone LightGBM Alpha Gate models) have been rigorously evaluated and **permanently retired**. **Archived failed hypotheses must not be silently re-tuned, re-tested with modified hyperparameters, or re-run on identical historical periods.**

---

## Active Documentation — Research Cycle 02 (`docs/cycle_02/`)

Research Cycle 02 tests a cross-asset, multi-engine quantitative platform operating on institutional timeframes (`1H`, `4H`, `1D`) and integrating auxiliary economic and market information layers.

### Architecture (`docs/cycle_02/architecture/`)
- [CROSS_ASSET_ARCHITECTURE.md](cycle_02/architecture/CROSS_ASSET_ARCHITECTURE.md): Comprehensive system blueprint detailing the 11 core engines, separation of concerns across Python/TradingView/n8n, LLM boundary conditions, canonical contracts (`MarketBar`, `EventNewsItem`), and default-deny risk interlocks.

### Decisions (`docs/cycle_02/decisions/`)
- [DATA_SOURCE_REGISTER.md](cycle_02/decisions/DATA_SOURCE_REGISTER.md): Official provider specifications across institutional Forex (OANDA), Cryptocurrency API adapters, central bank calendars, and public research fallbacks (`yfinance`), including strict SLAs and look-ahead prevention rules.

### Research (`docs/cycle_02/research/`)
- [CYCLE_02_RESEARCH_REGISTER.md](cycle_02/research/CYCLE_02_RESEARCH_REGISTER.md): Formal research hypothesis definition, four-tier experimental data window freezing protocols (`DEV_TRAIN`, `OUTER_VAL`, `CONFIRMATION`, `FINAL_HOLDOUT`), and Cycle 01 retirement records.

### Reports (`docs/cycle_02/reports/`)
- [CYCLE_02_MASTER_PLAN.md](cycle_02/reports/CYCLE_02_MASTER_PLAN.md): Master engineering roadmap specifying the 12 fixed implementation phases, objectives, dependencies, test requirements, pass/fail gates, and estimated build durations.

---

## Preserved Historical Archive — Research Cycle 01 (`docs/archive/cycle_01/`)

The complete historical record of Obsidian-RL Research Cycle 01 (and initial repository rebuilding phases 0 through 12) is preserved in full under `archive/cycle_01/`.

### Archive Access
- **Main Archive Directory**: [docs/archive/cycle_01/](archive/cycle_01/)
- **Move & Classification Manifest**: [DOCUMENT_ARCHIVE_MANIFEST.md](DOCUMENT_ARCHIVE_MANIFEST.md) (Detailed table mapping original file paths to their new archival locations with formal classification rationale).

### Key Historical Reports (`docs/archive/cycle_01/reports/`)
- [HISTORICAL_PILOT_01.md](archive/cycle_01/reports/HISTORICAL_PILOT_01.md): Historical pilot experiment report across 2020–2022 folds.
- [PPO_PILOT_01.md](archive/cycle_01/reports/PPO_PILOT_01.md): Initial PPO walk-forward screening report.
- [PPO_SEED_STABILITY_01.md](archive/cycle_01/reports/PPO_SEED_STABILITY_01.md): Multi-seed stability evaluation.
- [PPO_SEED_DIAGNOSTIC_01.md](archive/cycle_01/reports/PPO_SEED_DIAGNOSTIC_01.md): Comprehensive diagnostic analysis across five seeds.
- [PPO_TURNOVER_SCREEN_01.md](archive/cycle_01/reports/PPO_TURNOVER_SCREEN_01.md): Turnover regularization parameter screen.
- [PPO_SEED_ENSEMBLE_01.md](archive/cycle_01/reports/PPO_SEED_ENSEMBLE_01.md): Five-seed median ensemble screening report.
- [PPO_REPLICATION_2020_2022.md](archive/cycle_01/reports/PPO_REPLICATION_2020_2022.md): Frozen PPO replication study across 2020–2022.
- [ALPHA_GATE_PILOT_01.md](archive/cycle_01/reports/ALPHA_GATE_PILOT_01.md): Alpha Gate supervised net-edge pilot evaluation.
- [VALIDATION_REPORT.md](archive/cycle_01/reports/VALIDATION_REPORT.md): Phase 8 walk-forward validation summary.
- [FINAL_SYSTEM_AUDIT.md](archive/cycle_01/reports/FINAL_SYSTEM_AUDIT.md): Comprehensive rebuild audit across phases 0–12.
- [REVIEW.md](archive/cycle_01/reports/REVIEW.md): Multi-agent adversarial correctness review finding log.
- [AUDIT.md](archive/cycle_01/reports/AUDIT.md): Legacy intake and Q-learning defect audit.

### Historical Plans & Research (`docs/archive/cycle_01/plans/` & `research/`)
- [ROADMAP.md](archive/cycle_01/plans/ROADMAP.md): Cycle 01 Phase 0–12 completion checklist.
- [ARCHITECTURE.md](archive/cycle_01/research/ARCHITECTURE.md): Single-asset 15-minute PPO architecture notes.
- [DECISIONS.md](archive/cycle_01/research/DECISIONS.md): Cycle 01 Architecture Decision Records (ADR-001/002/003).
- [SESSION_HANDOFF.md](archive/cycle_01/research/SESSION_HANDOFF.md) & [CODEX_HANDOFF.md](archive/cycle_01/research/CODEX_HANDOFF.md): Historical research handoffs.

---

## Repository Setup & Tooling (`docs/`)
- [development.md](development.md): Reproducible development environment instructions (`python -m pip install -e .[dev,rl,gate,dashboard]`), test suite execution, and CI guidelines.
