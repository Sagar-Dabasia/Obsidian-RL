# Cycle 02 Phase 1: Canonical Cross-Asset Data Contracts Report

**Date:** 2026-07-22  
**Status:** COMPLETE (PASSED COMPLIANCE AUDIT)  
**Branch:** `fix/cycle-02-data-contract-compliance`  
**Schema Version:** `SCHEMA_V2`  

---

## 1. Executive Summary

In accordance with [CYCLE_02_MASTER_PLAN.md](CYCLE_02_MASTER_PLAN.md) and [CROSS_ASSET_ARCHITECTURE.md](../architecture/CROSS_ASSET_ARCHITECTURE.md), Phase 1 establishes the canonical, immutable data contracts (`MarketBar` and `EventNewsItem`) that serve as the foundational data layer for all Cycle 02 cross-asset multi-engine workflows.

Following our strict compliance audit and refactoring, these contracts enforce strict Python string enums (`StrEnum`), separation between external content digests (`raw_content_hash`) and internal structured record digests (`record_hash`), explicit handling of missing quotes (`bid`/`ask`) and volume modes across asset classes, point-in-time timestamp discipline (`observed_at_utc`), deterministic look-ahead bias prevention (`validate_ingestion_time`), and complete rejection of non-finite (`NaN`/`Infinity`) or boolean values.

**Zero Paid Resources or Downloaded Data:**  
In strict adherence to project governance, all development and verification were performed locally using only standard libraries (`enum.StrEnum`, `dataclasses`, `hashlib`, `json`, `math`) and in-memory mock fixtures. No paid APIs, external services, datasets, or network data downloads were utilized or introduced.

---

## 2. Key Architectural Governance & Compliance Mechanisms

### 1. Raw Content Hash vs. Structured Record Hash
To ensure auditability and prevent collision or confusion between external unstructured data and internal canonical records, `EventNewsItem` strictly enforces two separate cryptographic digests:
- **`raw_content_hash` (External Content Digest):** A required 64-character lowercase hex SHA-256 string representing the exact immutable payload of the underlying news article, economic calendar release, or report received from the external provider.
- **`record_hash` (Canonical Structured Record Digest):** Automatically computed by `compute_event_news_hash(item)` over the structured `EventNewsItem` fields (including `raw_content_hash`, `source_reliability`, `sentiment_score`, revision tracking, etc., but excluding `record_hash` itself). This guarantees that any modification to external content *or* internal downstream enrichment (e.g., updated sentiment score or revised release values) alters `record_hash` deterministically while preserving audit traceability to the original external article via `raw_content_hash`.

### 2. Missing Quote & Volume Handling Across Asset Classes
Because institutional asset classes report market quotes and trading volume differently, `MarketBar` enforces strict enums and invariants (`QuoteStatus` and `VolumeType`) to eliminate ambiguity while rejecting invalid combinations:
- **`QuoteStatus.OBSERVED` / `DERIVED`:** Requires both `bid` and `ask` to be present (`float > 0.0`), strictly finite, and ordered such that `ask >= bid`.
- **`QuoteStatus.UNAVAILABLE`:** Requires both `bid` and `ask` to be exactly `None` (e.g., equity or crypto exchanges reporting only bar trade prices or historical feeds lacking top-of-book depth).
- **`VolumeType.NONE`:** Enforces `volume = None` (e.g., indices or bar-only feeds).
- **`VolumeType.BASE` / `QUOTE` / `TICK`:** Requires finite `float >= 0.0` (e.g., cryptocurrency reporting base/quote volume, or forex broker feeds reporting tick volume without share counts).

### 3. Deterministic Ingestion Validation (No Direct Wall-Clock Checks)
To preserve test determinism and allow historical backtesting, walk-forward evaluation, and paper trading without wall-clock skew failures or look-ahead leakage, `__post_init__` enforces structural invariants (`observed_at_utc >= timestamp_utc`, `first_observed_at >= original_published_at`, `updated_at >= first_observed_at`) without invoking `time.time()`. 

Look-ahead prevention is enforced via `validate_ingestion_time(contract, current_time_ms, max_clock_skew_ms)`:
- Checks `observed_at_utc <= current_time_ms + max_clock_skew_ms` for `MarketBar`.
- Checks `first_observed_at <= current_time_ms + max_clock_skew_ms` and `updated_at <= current_time_ms + max_clock_skew_ms` for `EventNewsItem`.
- Raises `RuntimeError` on future timestamp violations, ensuring that simulated historical backtests and live execution use identical, verifiable ingestion logic.

---

## 3. Implementation Scope & Deliverables

### Modules Created & Updated
1. **`src/obsidian_rl/data/contracts.py`**  
   - Implements strict string enums inheriting from `enum.StrEnum`: `AssetClass`, `Timeframe`, `QuoteStatus`, `VolumeType`, `EventType`, and `RevisionStatus`.
   - Implements `@dataclass(frozen=True)` contracts for `MarketBar` and `EventNewsItem` (`schema_version = SCHEMA_V2`).
   - Rejects boolean values where `int` or `float` is required (`isinstance(val, bool)` rejection).
   - Rejects `NaN` and `Infinity` (`math.isfinite()` checks).
   - Provides standalone helper methods `to_dict(contract)` and `from_dict(cls, data, verify_hash=True)` with exact boundary checking (rejecting unknown and missing keys) and tamper verification.

2. **`src/obsidian_rl/data/fingerprint.py`**  
   - Provides `canonical_json(data)` with sorted keys, compact separators (`',', ':'`), enum value unwrapping, and `allow_nan=False`.
   - Provides `compute_canonical_sha256(data, exclude_keys)` which strips self-hash fields (`row_hash` for bars, `record_hash` for events) prior to computing deterministic SHA-256 digests.
   - Provides `compute_market_bar_hash`, `compute_event_news_hash`, and `verify_contract_hash`.

3. **`src/obsidian_rl/data/__init__.py`**  
   - Exports canonical contracts, strict enums, constants, and fingerprinting utilities cleanly for downstream engines and adapters.

4. **Unit Tests (`tests/data/`)**  
   - **`test_contracts.py`**: 16 comprehensive tests covering strict enum validation, crypto/forex/equity quote & volume modes, bool/NaN/Infinity rejection, structural ordering invariants, deterministic `validate_ingestion_time` checks, exact serialization round-trip, unknown/missing/tamper rejection, and hard-coded known SHA-256 digests (`3bdb80912e6...` for fixed bar, `22f74664005...` for fixed event).
   - **`test_fingerprint.py`**: 5 unit tests covering canonical JSON byte formatting, self-hash field exclusions, dict-vs-instance consistency, and `verify_contract_hash` validation.

---

## 4. Verification & Compliance Matrix

| Requirement | Rule / Constraint | Status | Verification Method |
| :--- | :--- | :--- | :--- |
| **Immutability** | `frozen=True` dataclasses; no mutation post-init | **PASS** | `dataclasses.FrozenInstanceError` asserted |
| **Strict Enums** | `StrEnum` instances; no silent string conversion | **PASS** | `isinstance(val, Enum)` explicitly asserted |
| **Type Governance** | Rejects `bool` where `int`/`float` required | **PASS** | Explicit `isinstance(val, bool)` rejection |
| **Data Integrity** | Rejects `NaN` and `Infinity` across all numericals | **PASS** | `math.isfinite()` + `allow_nan=False` |
| **Quote/Volume Rules** | Enforces `bid`/`ask` parity and `VolumeType` modes | **PASS** | Tested against `CRYPTO`, `FOREX`, `EQUITY` fixtures |
| **Hash Separation** | `raw_content_hash` vs `record_hash` distinct & verified | **PASS** | Tested modifying `raw_content_hash` updates `record_hash` |
| **Ingestion Validation** | Deterministic `validate_ingestion_time` raises `RuntimeError` | **PASS** | Tested against injected `current_time_ms` boundaries |
| **Serialization & Tamper** | `to_dict` / `from_dict` exact round-trip & rejection | **PASS** | Tested unknown keys, missing keys, and tampered values |
| **Known Digest Check** | Hard-coded SHA-256 exact match verification | **PASS** | `3bdb80912e...` & `22f7466400...` verified |
| **Additive Compatibility** | Zero regression in existing Cycle 01 suite | **PASS** | 443 tests total (442 passed, 1 skipped) |

---

## 5. Test Suite Execution & Linter Results

### Static Quality & Linter Checks
- **Ruff Lint**: `ruff check src/obsidian_rl/data tests/data` -> `All checks passed!`
- **Ruff Format**: `ruff format --check src/obsidian_rl/data tests/data` -> `12 files already formatted`
- **Mypy Type Check**: `mypy src/obsidian_rl/data tests/data` -> `Success: no issues found in 12 source files`

### Test Suite Execution
```text
$ .venv/Scripts/pytest.exe tests/data -v
tests/data/test_contracts.py ................                              [ 76%]
tests/data/test_fingerprint.py .....                                     [100%]
============================== 21 passed in 0.23s ==============================

$ .venv/Scripts/pytest.exe -q
........................................................................ [ 16%]
........................................................................ [ 32%]
........................................................................ [ 48%]
........................................................................ [ 65%]
..............................................................s......... [ 81%]
........................................................................ [ 97%]
...........                                                              [100%]
442 passed, 1 skipped in 18.29s
```

---

## 6. Next Steps (Phase 2 Readiness)

With strict canonical data contracts (`SCHEMA_V2`) compliant and locked, Cycle 02 Phase 2 (Forex and Crypto Provider Adapters) can proceed cleanly:
- Build `ProviderAdapter` interface in `src/obsidian_rl/data/adapters/base.py`.
- Implement OANDA practice/historical adapter mapping directly to `MarketBar` and `EventNewsItem` (`AssetClass.FOREX`, `QuoteStatus.UNAVAILABLE`/`OBSERVED`, `VolumeType.TICK`).
- Implement Crypto REST/WebSocket adapter mapping directly to `MarketBar` (`AssetClass.CRYPTO`, `QuoteStatus.OBSERVED`, `VolumeType.BASE`).
