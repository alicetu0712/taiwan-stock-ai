# Hybrid Cron — Final Readiness & Go-Live

**Status:** READY (crontab installation pending user approval)  
**Script:** `scripts/hybrid_shadow_cron.py`  
**Tests:** HC01–HC25 (tests/test_hybrid_cron.py), CG01–CG25 (tests/test_ohlc_continuity_gate.py)

---

## Crontab Line (AWAITING APPROVAL)

```cron
# Taiwan stock AI — Hybrid forward shadow + backfill (fires 20:00 Taipei time = 12:00 UTC)
0 12 * * 1-5 cd /Users/alicetu/Desktop/Antigravity/stock_platform && python3 scripts/hybrid_shadow_cron.py >> logs/cron.log 2>&1
```

**To install:**
```bash
crontab -e
# Paste the line above
```

This line is NOT yet installed. User approval required before installation.

---

## Cron Pipeline Steps

| Step  | Action                           | Fail Behavior         |
|-------|----------------------------------|-----------------------|
| 1     | Acquire FileLock                 | Exit (another run active) |
| 2     | Load state from `cron_state.json` | Continue with defaults |
| 3     | Check if today is a trading day  | Write state, exit OK  |
| 4a    | Run backfill (`backfill_daily_prices.py --execute`) | Warn, continue |
| 4b    | Verify DB last_data_date == today | Warn if stale (gate is ultimate backstop) |
| 5     | Run shadow runner (`run_hybrid_forward_shadow.py`) | Record FAILED in state |
| 6     | OHLC gate check (inside runner)  | RunStatus BLOCKED_MISSING_OHLC |
| 7     | Write final state to `cron_state.json` | — |
| 8     | Rotate backups (`cron_backup_*.json`) keep last 7 | — |

---

## Fail-Closed Verification

Three independent layers prevent bad signals:

1. **INVALID_DATA guard** (classify_capture): If `input_data_as_of < trade_date`,
   decision is INVALID_DATA — excluded from OOS analysis.

2. **Stale data guard** (hybrid_forward_db): If last 0050 date > 7 days before
   trade_date → RunStatus.BLOCKED_STALE_DATA.

3. **OHLC continuity gate** (`OHLCContinuityGate.check_market`): If any of the
   last 30 expected trading days lacks 0050 data → RunStatus.BLOCKED_MISSING_OHLC.

The cron script's Step 4b (verify DB last_date == today after backfill) is an
**early warning** only. A backfill that returns exit_code=0 but writes no data
(e.g., QG-5 failure) will be caught by layer 2 or 3 at step 6.

---

## State File: `data/cron_state.json`

```json
{
  "last_run": "2026-11-05",
  "last_status": "BLOCKED_MISSING_OHLC",
  "consecutive_failures": 0,
  "run_count": 1,
  "steps": {
    "is_trading_day": true,
    "backfill": "OK",
    "data_freshness": "OK",
    "shadow_runner": "BLOCKED_MISSING_OHLC"
  }
}
```

`consecutive_failures` counts only RunStatus.FAILED (true errors), not
BLOCKED_* statuses (which are expected while gate accumulates clean data).

---

## Backup Policy

- Backup file: `data/cron_backup_{date}.json`
- Retention: 7 most recent backups (older ones rotated out)
- Contents: same as `cron_state.json` at time of run

---

## Log Location

```
logs/cron.log
```

Monitor with: `tail -f logs/cron.log`

---

## Health Checks

```bash
# Check last cron run status
python3 -c "import json; print(json.load(open('data/cron_state.json')))"

# Check OHLC gate manually
python3 -c "
import sqlite3; from datetime import date
from src.research.ohlc_continuity_gate import GateResult, OHLCContinuityGate
conn = sqlite3.connect('data/platform.db')
r = OHLCContinuityGate().check_market(conn, date.today())
print(r.gate_result, 'missing:', r.missing_sessions)
"

# Check DailyPrice last date
python3 -c "
import sqlite3; conn = sqlite3.connect('data/platform.db')
print(conn.execute(\"SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'\").fetchone())
"
```

---

## Expected Behavior During Accumulation Phase (Nov–Dec 2026)

While the OHLC gate is BLOCKED_MISSING_OHLC:
- Cron runs daily, backfills today's data, runs shadow runner
- Runner returns BLOCKED_MISSING_OHLC (not an error — expected)
- `consecutive_failures` stays at 0
- State file records BLOCKED_MISSING_OHLC for each day

Gate will transition to PASS once 30 consecutive expected trading days have
0050 data (~2026-12-28 if no further gaps).
