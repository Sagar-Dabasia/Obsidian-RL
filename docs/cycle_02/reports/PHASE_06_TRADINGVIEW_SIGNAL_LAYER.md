# Phase 6: TradingView Pine Signal Layer

## Purpose

Phase 6 implements a **SECURE, INFORMATIONAL** TradingView signal layer that mirrors the authoritative Python trend calculations without becoming trading authority.

**Key Principle**: TradingView = visualization + alert proposal ONLY. Python remains authoritative for all quantitative decisions, risk gating, and execution.

## Architecture

### TradingView Layer (Pine Script)
- **File**: `pine/ObsidianMultiAssetTrend.pine`
- **Type**: `indicator()` only — NOT a `strategy()`
- **Capabilities**: Chart display, visual signals, alert generation via webhook
- **Prohibitions**: No `strategy.entry`, `strategy.order`, `strategy.exit`, `strategy.close`, no broker routing

### Python Webhook Receiver
- **File**: `src/obsidian_rl/interop/webhook_receiver.py`
- **Role**: Input validation / informational proposal ingestion ONLY
- **Prohibitions**:
  - Cannot import/call exchange order client
  - Cannot submit orders
  - Cannot directly mutate PortfolioEngine state
  - Cannot directly execute PaperTrader decisions

## Authentication Model

### Production: Trusted Reverse Proxy with Client Certificate Verification
```
TradingView → HTTPS (mTLS) → Reverse Proxy (nginx/Envoy) → Python Webhook Receiver
                ↑
         TradingView's client certificate
```

The Python receiver **only** accepts requests that arrive through a trusted reverse proxy that:
1. Terminates TLS with mutual authentication
2. Verifies TradingView's client certificate
3. Injects verified identity headers:
   - `X-Client-Cert-Verified: SUCCESS`
   - `X-Client-Cert-Subject: CN=TradingView Alerting...`

**Never trust arbitrary user-supplied headers claiming certificate verification.**

**Production authentication is exclusively trusted ingress with verified TradingView client certificate. No HMAC fallback exists in any environment.**

## Replay Protection

1. **Timestamp Freshness**: Maximum 60 seconds skew (configurable via `MAX_TIMESTAMP_SKEW_SECONDS`)
2. **Event ID Deduplication**: In-memory cache (production: Redis with TTL)
3. **Future Timestamp Rejection**: Timestamps beyond allowed skew rejected
4. **Stale Timestamp Rejection**: Timestamps older than allowed skew rejected

## Payload Schema

```json
{
  "schema_version": "1",
  "event_id": "BTCUSDT_240_1700000000000_LONG",
  "symbol": "BTCUSDT",
  "timeframe": "4h",
  "bar_timestamp_utc": 1700000000000,
  "signal": "LONG",
  "score": 1.0,
  "volatility_20d": 0.0234,
  "latest_close": 51234.56,
  "engine_version": "TrendEngineV1",
  "config_identity": "a1b2c3d4e5f6..."
}
```

**All fields required. No optional fields. No secrets.**

### Validation Rules
- `schema_version` must be "1"
- `event_id` non-empty, ≤256 chars, deterministic construction
- `symbol` alphanumeric + `_-.` only, ≤64 chars
- `timeframe` must be "4h", "1d", "240", or "D"
- `bar_timestamp_utc` positive integer, within 60s of receipt
- `signal` must be "LONG", "SHORT", or "FLAT"
- `score`, `volatility_20d`, `latest_close` must be finite numbers
- `engine_version` must contain "TrendEngineV1"
- `config_identity` must be 64-char lowercase hex SHA256
- **Zero unexpected fields allowed** — fail closed

## Pine/Python Parity

The Pine Script indicator mirrors the Python `TrendEngineV1` exactly:

| Parameter | Python Default | Pine Default |
|-----------|---------------|--------------|
| Short Horizon | 20 days | 20 days |
| Medium Horizon | 60 days | 60 days |
| Long Horizon | 120 days | 120 days |
| Timeframes | 4h, 1d | 240, D |
| Returns Calculation | (close - past) / past | Same |
| Volatility | StdDev of log returns | Same |
| Signal Logic | All 3 horizons same sign | Same |
| Score | 1.0 / -1.0 / avg signs | Same |

### Static Assertions (Pine)
- `indicator()` not `strategy()`
- No `strategy.entry/order/exit/close`
- Alerts only on `barstate.isconfirmed`
- No `lookahead_on` or `request.security` with lookahead
- No secret/token/password strings
- Deterministic calculations
- Deterministic `event_id` for duplicate detection

### Dynamic Parity Tests
`tests/interop/test_pine_parity.py` verifies:
- Flat/no-signal markets → FLAT
- Sustained uptrend → LONG (score=1.0)
- Sustained downtrend → SHORT (score=-1.0)
- Transition markets
- Insufficient warmup → InsufficientHistoryError
- Unsupported timeframes → DataQualityError
- Deterministic output
- Point-in-time filtering
- Data quality validation (mixed assets, out-of-order, duplicates, invalid prices)

**PINE_RUNTIME_VALIDATION = NOT_AVAILABLE_LOCAL** — Actual TradingView Pine compiler/runtime validation requires TradingView platform access and is not available in automated CI.

## Security Properties

| Property | Implementation |
|----------|----------------|
| No secret logging | Secrets never appear in log output |
| No credential logging | Cert details never logged |
| Fail-closed authentication | Missing/invalid ingress auth → 401 |
| Fail-closed payload | Any validation failure → 400 with detail |
| Bounded body size | 16KB max |
| Replay protection | Timestamp + event_id cache |
| No execution routes | Receiver imports zero execution modules |
| No portfolio mutation | Receiver has no PortfolioEngine/RiskEngine access |

## Files Added/Modified

### New Files
```
pine/ObsidianMultiAssetTrend.pine              # TradingView Pine Script indicator
src/obsidian_rl/interop/__init__.py            # Interop package init
src/obsidian_rl/interop/webhook_receiver.py    # Secure webhook receiver
tests/interop/test_webhook_receiver.py         # Webhook security tests
tests/interop/test_pine_parity.py              # Pine/Python parity tests
docs/cycle_02/reports/PHASE_06_TRADINGVIEW_SIGNAL_LAYER.md  # This document
```

### Modified Files
```
docs/cycle_02/reports/CYCLE_02_MASTER_PLAN.md  # Phase 6 auth model correction only
pyproject.toml                                  # Updated package metadata for interop module
```

## Verification Commands

```bash
# Focused interop tests
python -m pytest tests/interop -q

# Linting
python -m ruff check src/obsidian_rl/interop tests/interop
python -m ruff format --check src/obsidian_rl/interop tests/interop

# Type checking
python -m mypy src/obsidian_rl/interop

# Full suite (after focused gates pass)
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
python -m compileall -q src tests
python -m pip check
python -m build
git diff --check
```

## Test Coverage

### `test_webhook_receiver.py`
- Trusted ingress authentication (valid/invalid/missing cert)
- Timestamp validation (valid/stale/future)
- Event ID replay protection (first/duplicate)
- Payload schema validation (all required fields, types, bounds)
- Unexpected field rejection
- Non-finite numeric rejection
- Signal-specific validation (LONG/SHORT need non-zero, FLAT near zero)
- Oversized payload rejection
- Malformed JSON rejection
- Integration: valid webhook accepted, invalid rejected
- No execution routes in receiver code
- No portfolio mutation in receiver code
- No secret logging
- Rate limit framework (placeholder)
- Exception hierarchy
- Cache management

### `test_pine_parity.py`
- Flat market → FLAT
- Long market → LONG (score=1.0)
- Short market → SHORT (score=-1.0)
- Transition market
- Insufficient warmup
- Timeframe validation (4h, 1d accepted; 15m rejected)
- Deterministic output
- Config identity determinism
- Point-in-time filtering
- Data quality rejections (mixed assets, out-of-order, duplicates, invalid prices)
- Row hash validation
- Edge cases (zero volatility, minimal variation, score rounding, volatility formula)
- Static Pine assertions (indicator, no strategy orders, confirmed bars, no lookahead, no secrets, deterministic, event_id, payload structure)
- Python/Pine constant alignment

## Red Team Review Scope

After implementation, Financial + Red-Team + Data/Leakage reviewers independently attack:

1. **Spoofed webhook origin** — Fake headers without trusted ingress
2. **Replay attacks** — Duplicate event_id, stale/future timestamps
3. **Malformed payloads** — Non-finite numerics, missing fields, unexpected fields
4. **Pine/Python signal disagreement** — Mismatch detection
5. **Intrabar/repaint behavior** — Confirmed bar enforcement
6. **Future leakage** — Point-in-time validation
7. **Execution bypass** — Attempt to turn proposal into order
8. **Portfolio state mutation** — Direct engine access
9. **Risk engine bypass** — Skip RiskEngine evaluation
10. **Secret leakage** — Config in payload

## Integration Boundary

```
TradingView Alert (JSON)
    → Webhook Receiver (validate, deduplicate)
    → ValidatedSignal (informational proposal)
    → [Future: Queue for Python TrendEngine verification]
    → [Future: RiskEngine evaluation]
    → [Future: PortfolioEngine execution]
```

**Current Phase 6 stops at ValidatedSignal production.** The proposal is logged and available for downstream consumption but does not automatically trigger any trading action.

## Safety Invariants

- Paper trading only — no live/Testnet/private order capability
- No holdout access
- No synthetic market data substitution
- No future data in features/labels/normalization
- All financial invariants from Phase 5 preserved
- PortfolioEngine remains sole owner of financial state
- RiskEngine remains read-only gate

## Conclusion

Phase 6 delivers a secure, informational TradingView signal ingestion layer with:
- Production-grade authentication via trusted reverse proxy + mTLS
- Strict replay protection (timestamp + event_id)
- Comprehensive payload validation (fail-closed)
- Exact Pine/Python mathematical parity
- Zero execution capability in receiver
- Zero portfolio mutation capability
- No secret/credential leakage
- Full test coverage for security and parity properties

**Verification Result**: All local gates PASS
- Focused interop tests: PASS
- Full pytest suite: PASS
- Ruff check: PASS
- Ruff format: PASS
- MyPy: PASS
- compileall: PASS
- pip check: PASS
- build: PASS
- 15/15 office adjudication: PASS
- PINE_RUNTIME_VALIDATION: NOT_AVAILABLE_LOCAL