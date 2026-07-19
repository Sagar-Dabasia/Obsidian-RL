# Session handoff

Updated: 2026-07-19 · Branch: `rebuild/deep-rl-platform` · Base: 8c5cec9 (main, pushed)

## State
- Phase 0 in progress: .env untracked (local preserved), .gitignore rebuilt (was UTF-16),
  artifacts untracked, legacy quarantined in `legacy/`, pyproject + tooling installed.
- Audit complete: docs/AUDIT.md. ADRs: docs/DECISIONS.md.

## Blocking external action
- User must revoke the Binance API key from the `.env` pushed in 8c5cec9.

## Next
- Phase 1: verify Binance USD-M perp public endpoints, write ADR-003.
- Phase 2: data layer under `src/obsidian_rl/data/`.

## Conventions
- Interpreter: `.venv\Scripts\python.exe`. Gates: pytest, ruff check+format, mypy, compileall.
- Commit per phase; never push. Keep this file under 100 lines.
