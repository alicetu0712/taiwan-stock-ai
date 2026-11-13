# Session 71P — Artifact Manifest

**Session**: 71P  
**Verdict**: `ARTIFACT_SET_VERIFIED`

---

## Artifact 1 — Guarded Backfill (Replace)

| Property | Value |
|---|---|
| Candidate Path | `scripts/backfill_daily_prices_guarded.py` |
| Production Target | `scripts/backfill_daily_prices.py` |
| Action | REPLACE (atomic rename) |
| Candidate SHA256 | `202e2231b6d2b8b865e5a854254c04b4dabff2b408807bac8172bced3a194c42` |
| S71O Manifest Hash | `202e2231b6d2b8b865e5a854254c04b4dabff2b408807bac8172bced3a194c42` |
| Hash Match | ✓ MATCH |
| File Size | 26,513 bytes |
| Last Modified | 2026-11-12 21:21 |
| Import Check | IMPORT_OK (`from scripts.scheduler_safety_guards import BackfillEntryGuard`) |
| CLI --help | PASS (identical interface to production) |
| RC-2 Filter | PRESERVED (`EXCLUDE_KEYWORDS` AST-verified identical) |

---

## Artifact 2 — Safety Guard Module (Verify Only)

| Property | Value |
|---|---|
| Candidate Path | `scripts/scheduler_safety_guards.py` |
| Production Target | `scripts/scheduler_safety_guards.py` (same file) |
| Action | VERIFY ONLY — already in production at correct hash |
| Candidate SHA256 | `f6929a7c7cf2734ca597dda06bdc1014d67f74990c29dff3f5f825284783765b` |
| S71O Manifest Hash | `f6929a7c7cf2734ca597dda06bdc1014d67f74990c29dff3f5f825284783765b` |
| Hash Match | ✓ MATCH |
| File Size | 28,342 bytes |
| Last Modified | 2026-11-12 21:20 |
| Deployment Action | NONE (not overwritten — hash matches, unnecessary overwrite prohibited) |

---

## RC-2 Filter AST Verification

```
PROD EXCLUDE_KEYWORDS: ['ETF', 'ETN', 'REIT', 'REITs', '特別股', '受益憑證', 'DR', 'DEPOSITARY', 'WARRANT', 'WARRANTS']
CAND EXCLUDE_KEYWORDS: ['ETF', 'ETN', 'REIT', 'REITs', '特別股', '受益憑證', 'DR', 'DEPOSITARY', 'WARRANT', 'WARRANTS']
RC2_MATCH: True
```

---

## Dependency Audit

| Import | Source | Reviewed |
|---|---|---|
| `BackfillEntryGuard` from `scripts.scheduler_safety_guards` | Same deployment (File 2, already in place) | ✓ |
| `fcntl` | Python stdlib | ✓ |
| `sqlite3` | Python stdlib | ✓ |
| `argparse` | Python stdlib | ✓ |
| `pytz` | 3rd party (pytz 2026.2) | ✓ |
| `sqlalchemy` | 3rd party (sqlalchemy 2.0.51) | ✓ |

No unreviewed dependencies.

---

## Wrapper Compatibility

| Check | Evidence | Status |
|---|---|---|
| Original wrapper holds lock | `fcntl.flock(LOCK_EX)` during entire run | ✓ |
| Guard detects lock via `LOCK_NB` attempt | `BlockingIOError` → AUTHORIZED | ✓ |
| Cross-process proof | N-lock-01 test (S71N compatibility_matrix.md) | ✓ VERIFIED |
| No `CALLED_FROM_WRAPPER=1` needed | Lock-based detection is sufficient | ✓ |
| CLI interface unchanged | `--help` output identical | ✓ |
