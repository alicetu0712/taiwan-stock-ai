# Session 63 — Offline Zero-network Proof (RC-2)

## Status: OFFLINE_ZERO_NETWORK_VERIFIED

---

## 1. What "Offline" Means

For RC-2 purposes, "offline" means:
- Zero HTTP calls during `_is_excluded()` execution
- Zero subprocess spawns during `_is_excluded()` execution
- Zero DB connections during `_is_excluded()` execution
- Module import does NOT trigger any of the above

This is distinct from zero-write (S62): offline addresses network/process isolation.

---

## 2. `_is_excluded()` Code Path Analysis

```python
def _is_excluded(name: str, stock_id: str) -> bool:
    name_up = str(name).upper()                        # str operation only
    if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):   # list comparison
        return True
    sid = str(stock_id).strip()                        # str operation only
    if len(sid) > 4 and not sid.isdigit():             # arithmetic + method call
        return True
    return False
```

After RC-2:
```python
    if len(sid) > 4:                                   # arithmetic only
```

**All operations are pure string/arithmetic — zero I/O.**

---

## 3. `EXCLUDE_KEYWORDS` — Module-level Constant

```python
EXCLUDE_KEYWORDS = ["ETF", "ETN", "REIT", "REITs", "特別股", "受益憑證",
                    "DR", "DEPOSITARY", "WARRANT", "WARRANTS"]
```

Defined at module level (line 61-64). It is a plain Python list — no DB query, no HTTP, no file read at access time.

---

## 4. Test Evidence — Network Blocking

Tests TC16–TC22 use `unittest.mock.patch` to replace `requests.get` with a sentinel that raises `RuntimeError("NETWORK_CALL_DETECTED")`.

| TC | Scenario | Network Blocked | Result |
|---|---|---|---|
| TC16 | `_is_excluded()` before RC-2 | YES | PASS (no HTTP) |
| TC17 | `_is_excluded_after()` (RC-2 sim) | YES | PASS (no HTTP) |
| TC18 | Warrant + ETF + ordinary | YES | PASS (no HTTP) |
| TC19 | Module import (re-import) | YES | PASS (mock.assert_not_called) |
| TC20 | Full 15-case matrix | YES | PASS (zero HTTP) |
| TC21 | Subprocess also blocked | YES | PASS (no subprocess) |
| TC22 | DB `sqlite3.connect` blocked | YES | PASS (no DB open) |

**All 7 offline tests PASS with network/subprocess/DB calls blocked.**

---

## 5. Module Import Side Effects — RC-2 Scope

The only module-level side effect in `backfill_daily_prices.py` is:
```python
_CALENDAR = TaiwanTradingCalendar()   # line 65 — pure Python, no I/O
```

RC-2 patch (`_is_excluded()` body change) adds ZERO new module-level code. No new imports, no new constants, no new module-level function calls.

---

## 6. Entry Points — Network Safety Scope

| Entry Point | Calls `_is_excluded()` | Network During `_is_excluded()` |
|---|---|---|
| EP-01: CLI dry-run | YES (at lines 125, 214, 273) | None — pure logic |
| EP-02: hybrid_shadow_cron.py | YES (via subprocess) | None — pure logic |
| EP-03: Python import | Possibly | None — pure logic |

All three entry points: `_is_excluded()` itself makes zero network calls regardless of caller.

---

## 7. What RC-2 Does NOT Change

| Concern | Status |
|---|---|
| `run_backfill()` network behavior | UNCHANGED — network calls are TWSE/TPEx fetch, unrelated to `_is_excluded()` |
| `_fetch_twse_data()` / `_fetch_tpex_data()` | UNCHANGED — RC-2 does not touch these functions |
| Number of HTTP calls in a full backfill | UNCHANGED — filtering happens after fetch |
| `_CALENDAR` initialization | UNCHANGED |

---

## 8. Verdict

```
OFFLINE_ZERO_NETWORK_VERIFIED
  _is_excluded() path  : ZERO I/O
  module import        : ZERO new side effects from RC-2
  network block tests  : 7/7 PASS
  subprocess block     : PASS
  DB open block        : PASS
```
