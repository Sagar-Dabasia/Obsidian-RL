# Phase 4C Final Invalidation Report

## Executive Summary
**Final Classification:** `EXPERIMENT INVALID — NO STRATEGY CONCLUSION`

Phase 4C cross-market trend pilot has been permanently closed without evaluating the underlying trend strategy metrics. No results from this phase may be used to declare the strategy successful or failed.

## Issues Discovered
The experiment was invalidated due to a cascading series of critical structural failures:

1. **Warm-up Starvation Defect:** The initial dataset builder did not distinguish between evaluation data boundaries and warm-up requirements, incorrectly attempting to fulfill strategy warm-up periods from data that was either missing or fell into the evaluation horizon.
2. **Manifest/Database Mismatch:** Discrepancies were introduced when manual execution runs retrieved data ranges that conflicted with the tightly coupled immutable manifest fingerprints, breaking provenance.
3. **Altered-Cost Rerun:** Initial manual mitigation attempts incorrectly altered the rigid frozen execution configuration (e.g., fee tiers) rather than solving the data ingestion issue.
4. **Custom-Script Rerun:** Unofficial evaluation scripts were used to circumvent the canonical execution path, introducing untracked evaluation divergence and bypassing core invariants.
5. **Unsupported Holiday Registrations:** Forex data ingestion was blocked by mandatory gaps (OANDA holidays). The registry was updated based strictly on calendar inference, which is explicitly forbidden.
6. **Fabricated Empty-Response Hashes:** In the absence of an active `OANDA_API_TOKEN`, dummy `{"candles": []}` JSON payloads were constructed and hashed locally to pass rigorous tests. These cryptographic proofs were synthetically created rather than genuinely retrieved from the provider.
7. **Absence of Authentic OANDA Evidence:** The lack of authentic, exact historical API proofs of provider omissions meant that the gap logic could not legally bypass the strict missing-data rules. 

## Integrity Maintained
* **Confirmation/Final Holdout Untouched:** At no point were the final unseen evaluation sets accessed or compromised during this debugging phase.
* **Preservation of Artifacts:** All scripts, manifests, generated reports, and tests associated with Phase 4C have been preserved. No negative evidence was deleted.

Phase 4C is officially closed and cannot be rerun using the current unverifiable Forex data constraints. Future experiments must select alternative, proven markets or implement a strict new data-acquisition protocol.
