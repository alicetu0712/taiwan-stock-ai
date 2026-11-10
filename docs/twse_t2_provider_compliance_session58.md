# TWSE T2 Provider Compliance Gate — Session 58

**Verdict**: T2_COMPLIANCE_UNVERIFIED  
**Date**: 2026-11-10  
**Previous session**: S57 (3947 tests)

---

## Compliance Layers Assessed

| Layer | Description | Status |
|-------|-------------|--------|
| L1 | Technical connectivity | CONFIRMED — endpoint returns HTTP 200 |
| L2 | Date semantics correct | CONFIRMED — monthly response with individual dates |
| L3 | Full OHLCV available | CONFIRMED — all 5 pilot probes FULL_OHLCV_WITH_VOLUME |
| L4 | Rate limit policy known | UNVERIFIED — terms pages returned 404 |
| L5 | Automated access policy | UNVERIFIED — no formal policy text found |
| L6 | Commercial restriction | UNVERIFIED |
| L7 | Attribution required | UNVERIFIED |
| L8 | Bulk recovery authorized | NOT_AUTHORIZED — AUTH01 required |
| L9 | Historical accuracy | PARTIAL — pilot verified 5 stocks / 2 months |
| L10 | Pipeline integration ready | DESIGN_COMPLETE — not implemented |

**Key distinction**: "Technically accessible" (L1-L3 CONFIRMED) ≠ "Compliant for automated bulk access" (L4-L7 UNVERIFIED).

---

## URL Evidence

| URL | Method | Result |
|-----|--------|--------|
| `https://www.twse.com.tw/en/about/copyright.html` | WebFetch | 404 Not Found |
| `https://www.twse.com.tw/rwd/zh/copyright/index.html` | WebFetch | 404 Not Found |
| `https://openapi.twse.com.tw/` | WebFetch | Swagger UI only — no policy text |

All three official documentation/terms URLs failed to return usable policy text. The Swagger UI at openapi.twse.com.tw renders endpoint documentation but contains no terms of service, rate limits, or automated access policy.

---

## Verdict Derivation

**T2_COMPLIANCE_UNVERIFIED** (not BLOCKED, not VERIFIED):

- The endpoint is **functionally accessible** and returns valid structured data
- It is **widely used** by the Taiwan fintech ecosystem (inferred public endpoint)
- **No explicit restriction found** — but absence of restriction ≠ permission
- **Rate limit** cannot be confirmed → full-scale recovery at 2 req/sec may or may not violate policy
- **Legal/compliance risk** cannot be quantified without terms text

**Implication**: Full-scale recovery (1198 calls) cannot proceed under T2_COMPLIANCE_UNVERIFIED status. Pilot (5 probes) was justified as bounded research.

---

## Next Steps Before Full Recovery

1. Locate TWSE official API terms of use (contact TWSE market data team if URL-based search fails)
2. Confirm explicit rate limit value (or confirm no limit)
3. Confirm automated access is permitted for academic/research purposes
4. Obtain AUTH01 authorization from user
5. Verify crawl delay acceptable for chosen concurrency

**None of these steps have been completed. Full recovery remains BLOCKED.**
