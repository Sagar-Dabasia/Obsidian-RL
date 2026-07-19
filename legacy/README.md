# DEPRECATED — legacy Q-learning system

Quarantined 2026-07-19. Do not import from new code; do not run `live_trader.py` or the
trainers. Known correctness defects are cataloged in `docs/AUDIT.md` (label leakage,
fill-at-observation-price, duplicate position state, silent synthetic-data fallback,
unsafe pickle loads, no temporal splits). Legacy `*.pkl` artifacts are untrusted and
must never be loaded. Kept temporarily for reference; removal after the replacement
system passes its correctness gates.
