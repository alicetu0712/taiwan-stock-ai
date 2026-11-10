# TWSE T2 Compliance Resolution — Session 59

**Date**: 2026-11-10  
**Verdict**: T2_COMPLIANCE_UNVERIFIED (unchanged from S58)

---

## Compliance Verdict

T2_COMPLIANCE_UNVERIFIED. No new compliance documentation was found in S59. All findings carry forward from S58 unchanged.

"Technically accessible" ≠ "Authorized for automated bulk access."  
HTTP 200 from a pilot probe does not constitute permission for 1,424 sequential API calls.

---

## Evidence Inventory

| Item | URL | HTTP Status | Evidence Level | Notes |
|------|-----|-------------|----------------|-------|
| TWSE copyright page (English) | `…/en/about/copyright.html` | 404 | UNVERIFIED | Tested S58 |
| TWSE copyright page (Chinese) | `…/rwd/zh/copyright/index.html` | 404 | UNVERIFIED | Tested S58 |
| TWSE OpenAPI Swagger UI | `https://openapi.twse.com.tw/` | 200 | UNVERIFIED | Swagger UI only, no policy text |
| TWSE single-stock endpoint | `…/exchangeReport/STOCK_DAY` | 200 | VERIFIED_BY_PRACTICE | Returns monthly OHLCV — feasible but not authorized |
| Rate limit policy | — | — | UNVERIFIED | No rate-limit headers observed in 5 pilot requests |
| Automated bulk access policy | — | — | UNVERIFIED | No policy text located anywhere |
| Alternative channels | — | — | UNVERIFIED | Not evaluated in S58/S59 |

---

## What Was Tried

**S58 URL probes (3 attempts)**:
1. `https://www.twse.com.tw/en/about/copyright.html` → HTTP 404
2. `https://www.twse.com.tw/rwd/zh/copyright/index.html` → HTTP 404
3. `https://openapi.twse.com.tw/` → HTTP 200 (Swagger UI, no terms of service text)

No terms of service, rate limit policy, or automated access policy was found at any tested URL.

---

## Pilot Feasibility vs Compliance

The T2 pilot (S58, 5/5 PASS) confirmed:
- The endpoint is reachable from the platform
- It returns full monthly OHLCV data in one request
- 5 tested stocks all returned complete data with volume

The pilot does **not** confirm:
- Permission to make 1,424 sequential automated requests
- Rate limit tolerance
- Policy compliance for commercial/research use

These are separate questions requiring official TWSE documentation.

---

## Rate Limit Uncertainty

5 pilot requests did not trigger rate-limit responses. This does not establish:
- That no rate limit exists
- What the rate limit threshold is
- Whether 1,424 sequential calls at 2s intervals would be permitted

Consequence: If a rate limit exists and is triggered mid-recovery, some stock-months may be missed. A partial recovery with unknown gaps is worse than a known gap.

---

## Recommended Next Steps

1. **Contact TWSE market data team directly** — ask about API terms for research/educational use.
2. **Search TWSE website** for `API使用規範`, `資料使用授權`, or `OpenAPI 授權`.
3. **Check TWSE OpenAPI documentation** for a "Terms of Use" or "License" link that may not be on the main Swagger UI page.
4. **Consider official alternatives** before proceeding with per-stock API calls.

Until compliance is confirmed, AUTH01 for full T2 recovery remains blocked.

---

## Alternative Acquisition Channels (Not Evaluated)

| Channel | Description | Compliance Risk |
|---------|-------------|-----------------|
| TWSE Market Information System (MIS) | Official bulk historical data download | Lower — official channel |
| Licensed data provider | Commercial data vendor with TWSE agreement | Lowest — licensed |
| TWSE Open Data Portal | Government open data (data.gov.tw) | Lower — open data license |
| Direct TWSE inquiry | Contact market data department | — |

These alternatives were not evaluated in S58 or S59. Any of them may offer better compliance guarantees and potentially simpler bulk access than 1,424 individual API calls.
