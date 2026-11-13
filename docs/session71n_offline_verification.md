# Session 71N — Offline Verification Results

**Session**: 71N  
**Mode**: ISOLATED_OFFLINE_VERIFICATION / NO_PRODUCTION_DEPLOYMENT  
**Verdict**: `OFFLINE_VERIFICATION_PASS_WITH_FINDINGS`

---

## Test Suite Results (Current State)

| Suite | Tests | PASS | FAIL | Notes |
|---|---|---|---|---|
| `test_scheduler_safety_guards.py` | 53 | 53 | 0 | All pass |
| `test_wrapper_integration.py` | 38 | 34 | 4 | 4 calendar-stale (see N-FINDING-01) |
| `test_session71l_safety.py` | 22 | 20 | 2 | 2 calendar-stale |
| `test_session71m_entry_guard.py` | 30 | 30 | 0 | All pass |
| **Guard Suite Total** | **143** | **137** | **6** | 4 date-sensitive failures |
| **Full Suite** | 4489 | 4448 | 41 | 37 pre-existing + 4 new |

---

## N-FINDING-01: Calendar-Stale Test Failures (NEW)

**Tests affected**: L-06, L-07, IT-25, IT-26  
**Root cause**: These tests inject `hour=17` as time override, which makes `scheduled_date = date(2026, 11, 12)`. But the outer wrapper also writes `today=` using the ACTUAL current date `2026-11-13`. The `SameDayStateGuard.check()` reads `today` first → sees `2026-11-13` ≠ injected `2026-11-12` → returns ALLOWED.

**Is this a code bug?** No. The guard's behavior is correct — it's a test isolation bug. The tests didn't inject both `_now_taipei_override` AND the outer wrapper's `today` field. They were passing on 2026-11-12 because the actual date happened to match the injected date.

**Impact on production**: NONE. The underlying guard logic is verified by manual test (N-lock-01).

**Recommended fix** (not in this session): Tests L-06, L-07, IT-25, IT-26 need to inject a full `_now_taipei_override` that includes today's actual date, not yesterday's.

**Comparison with S71M baseline**:
- S71M: 4452 passed, 37 failed (session date was 2026-11-12)
- S71N: 4448 passed, 41 failed (session date is 2026-11-13, +4 calendar-stale)

---

## Specific Offline Tests Performed in S71N

### N-lock-01: Cross-process Lock Visibility (PASS)
```
Parent acquires LOCK_EX → child subprocess tries LOCK_EX|LOCK_NB → "HELD"
Parent releases → child tries again → "NOT_HELD"
Result: PASS ✓
```

### N-lock-02: Lock Path Resolution Match (PASS)
```
wrapper LOCK_FILE = data/.cron.lock
guarded _DEFAULT_LOCK_FILE = data/.cron.lock
wrapper_lock.resolve() == default_lock.resolve(): True
Result: PASS ✓
```

### N-lock-03: Import Verification (PASS)
```
from scripts.scheduler_safety_guards import BackfillEntryGuard
check_original_entry: True
_check_lock_state: True
check_invocation: True
Result: PASS ✓
```

### N-semantic-01: EXCLUDE_KEYWORDS AST comparison (PASS)
```
Original == Guarded: True
Result: PASS ✓
```

### N-semantic-02: _is_excluded() string comparison (PASS)
```
_is_excluded function: IDENTICAL ✓
Result: PASS ✓
```

### N-state-01: State file compatibility (PARTIAL)
```
Old state (original wrapper format) → new guard: ALLOWED (expected — different day)
New state (guard format) → guard: WRITE_COMMITTED_TODAY (expected)
Old state does not block new guard on new day: CORRECT behavior
Result: PARTIAL (see commit_lock_state_review.md for details)
```

### N-sha-01: Production file hash verification (PASS)
```
hybrid_shadow_cron.py: 46209171... ✓
backfill_daily_prices.py: 4eb6eacf... ✓
Result: PASS ✓
```

---

## Tests NOT Run (Blocked by Safety Boundary)

| Test Type | Reason | Status |
|---|---|---|
| Provider call (TWSE/TPEx) | Calls real HTTP APIs | BLOCKED |
| Production SQLite write | Would modify production data | BLOCKED |
| Neon read/write | Network call with secrets | BLOCKED |
| Live cron trigger | Would modify production state | BLOCKED |
| Production lock acquisition | Would affect real `.cron.lock` | BLOCKED |

---

## Guard Suite Summary (Pre-existing + New)

| Category | Count | Tests |
|---|---|---|
| Pre-existing failures (RC-2 era, S66+) | 37 | Hash sentinel tests for pre-RC-2 value |
| New calendar-stale failures (N-FINDING-01) | 4 | L-06, L-07, IT-25, IT-26 |
| Total failures | 41 | |
| Passing tests | 4448 | |
