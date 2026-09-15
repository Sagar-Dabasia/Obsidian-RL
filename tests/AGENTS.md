# Tests AGENTS.md
These rules apply ONLY within tests/.
Root AGENTS.md invariants remain absolute; this file adds domain-specific constraints.

## Never Weaken Tests
- Removing or weakening assertions to make tests pass is prohibited.
- Test changes cannot silently change production semantics.
- Regression tests must exercise real behavior, not print-only proofs.

## Deterministic Fixtures
- Fixtures must be deterministic and reproducible.
- No external network/market access in unit tests.
- Seeded RNG only; no time-dependent assertions.

## Real Behavior Only
- Mocks only for external services; production code paths must be exercised.
- Patch gate verifies test-weakening attempts fail.
- No test-only bypasses for financial invariants.
