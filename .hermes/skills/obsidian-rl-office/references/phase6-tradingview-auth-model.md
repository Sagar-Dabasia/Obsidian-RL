# Phase 6 TradingView Webhook Authentication Model Correction

## Context
During Phase 6 implementation (TradingView Pine Signal Layer), the initial design included an HMAC fallback authentication path for development/testing. This was corrected after review against the official TradingView behavior.

## Official TradingView Behavior
- Webhook sends HTTP POST with valid JSON (`application/json`)
- TradingView presents HTTPS client certificate (mTLS)
- TradingView warns against credentials/secrets in webhook URL/body
- Pine alerts construct dynamic JSON messages
- Alerts should trigger on confirmed bars (`barstate.isconfirmed`) to prevent repaint

## Corrected Authentication Model

### PRODUCTION (Required)
```
TradingView → HTTPS (mTLS) → Reverse Proxy (nginx/Envoy) → Python Webhook Receiver
                          ↑
                 TradingView's client certificate
```
The Python receiver **only** accepts requests through a trusted reverse proxy that:
1. Terminates TLS with mutual authentication
2. Verifies TradingView's client certificate
3. Injects verified identity headers:
   - `X-Client-Cert-Verified: SUCCESS`
   - `X-Client-Cert-Subject: CN=TradingView Alerting...`

### DEVELOPMENT/TEST (Removed)
**NO HMAC fallback.** The `require_ingress_auth: bool = True` parameter with HMAC fallback when `False` was removed entirely.

Tests must mock trusted ingress state (headers) directly — no HMAC authentication feature exists in production code.

## Implementation Changes

### Removed from `src/obsidian_rl/interop/webhook_receiver.py`:
- `_verify_hmac_signature()` function
- `_constant_time_compare()` function (was only used for HMAC)
- `hmac_secret` parameter from `receive_webhook()`
- `require_ingress_auth` parameter from `receive_webhook()`
- HMAC fallback branch in `receive_webhook()`
- `hashlib` import (no longer needed)

### Updated in `tests/interop/test_webhook_receiver.py`:
- Removed `TestHMACVerification` class entirely
- Removed `test_hmac_fallback_works_when_ingress_disabled`
- Removed `test_hmac_fallback_rejects_invalid_signature`
- Removed `test_hmac_secret_not_in_logs` (no HMAC secret to log)
- Updated integration tests to call `receive_webhook(body, headers)` without HMAC params
- Tests now mock trusted ingress headers directly

## Key Principle
**Never implement a fake HMAC scheme. Never embed a shared secret in Pine. Never put credentials/tokens in webhook body or URL. Never invent custom TradingView headers that are not supported.**

The webhook receiver is INPUT VALIDATION / INFORMATIONAL PROPOSAL only. It must NOT:
- Create an order
- Bypass PortfolioEngine
- Bypass RiskEngine
- Mutate portfolio/accounting state
- Become a second strategy/state owner

## Verification
All 90 interop tests pass with the corrected model. Full verification suite passes.