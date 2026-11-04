# Hybrid Forward Shadow — Deployment Runbook

**Rule version:** hybrid_v1 | **Freeze date:** 2026-11-05 | **Freeze commit:** 6602c3b

---

## Scope

This runbook covers the **research SQLite pipeline only**. It does NOT cover:
- Production Neon PostgreSQL (never written by this pipeline)
- MODEL_VERSION v8.0 decisions
- ACTUAL or PAPER trade accounting
- Phase 1B migration or production deployment

---

## Pre-conditions

| Check | Command | Expected |
|-------|---------|---------|
| Research DB exists | `ls data/platform.db` | File present |
| DailyPrice populated | `python3 -c "import sqlite3; c=sqlite3.connect('data/platform.db'); print(c.execute('SELECT MAX(date) FROM daily_prices').fetchone())"` | Date ≤ 7 days ago |
| Tests pass | `python3 -m pytest tests/test_hybrid_forward_shadow.py -q` | 56 passed |
| Lint clean | `ruff check src/research/hybrid_forward_db.py src/research/hybrid_trading_calendar.py scripts/run_hybrid_forward_shadow.py` | All checks passed |

---

## Daily Operation (Local Cron — Option D)

### Cron schedule (Taiwan time 15:35, Mon–Fri)

```cron
35 15 * * 1-5 cd /path/to/stock_platform && python3 scripts/run_hybrid_forward_shadow.py >> logs/hybrid_shadow.log 2>&1
```

Replace `/path/to/stock_platform` with the absolute project root.

### Manual run

```bash
# Today's decisions (auto-detects date)
python3 scripts/run_hybrid_forward_shadow.py

# Specific date
python3 scripts/run_hybrid_forward_shadow.py --date 2026-11-05

# Backfill matured outcomes only (no new decisions)
python3 scripts/run_hybrid_forward_shadow.py --backfill-outcomes-only

# Force run even if DailyPrice is stale (testing only — produces LATE_CAPTURE)
python3 scripts/run_hybrid_forward_shadow.py --date 2026-11-05 --force-stale
```

### Expected output on success

```
2026-11-05 Hybrid Forward Shadow run
  status=SUCCESS
  inserted=12
  skipped=0
  conflicts=0
  errors=0
  outcome_filled=0
```

---

## Verifying a Run

```bash
python3 - <<'EOF'
import sqlite3
from src.research.hybrid_forward_db import get_operational_summary
conn = sqlite3.connect("data/platform.db")
import json
print(json.dumps(get_operational_summary(conn), indent=2, default=str))
conn.close()
EOF
```

Key fields to verify:
- `latest_run.status` = `SUCCESS`
- `latest_run.conflict_count` = 0
- `prospective_decisions` incrementing daily
- `consecutive_failures` = 0

---

## Incident Response

### ConflictError / status=CONFLICT

A conflict means the same stock+date+rule_version produced a different decision on re-run.
This should not happen unless:
1. Rule logic was changed after freeze (FORBIDDEN — check hybrid_entry_strategy.py git diff)
2. Input data was retroactively modified (check DailyPrice for the affected date)

**Action:**
1. Do NOT force-reinsert. The original record is correct.
2. Run `python3 scripts/run_hybrid_forward_shadow.py --date YYYY-MM-DD` and examine the error_summary in run_log.
3. If confirmed as a data issue, document in a separate correction note — never overwrite the original row.

### status=BLOCKED_STALE_DATA

DailyPrice is > 7 calendar days old relative to trade_date.

**Action:**
1. Run the DailyPrice collector: `python3 scripts/collect_daily_prices.py`
2. Re-run shadow after price data is updated.
3. If running more than 1 trading day late, the resulting records will be tagged `LATE_CAPTURE`,
   not `PROSPECTIVE`. This is correct — do not use `--force-stale` to try to relabel them.

### status=BLOCKED_MISSING_SIGNALS

ForwardSignal entries for the requested date are missing in production.

**Action:**
1. Check production ForwardSignal pipeline in Neon.
2. If signals are generated later that day, re-run shadow after they appear.
3. If signals remain missing, that trading day's PROSPECTIVE record is permanently lost —
   this is by design (no retrospective recovery for PROSPECTIVE classification).

### status=SKIPPED_NON_TRADING_DAY

Trade_date is not a Taiwan trading day (weekend or holiday per 0050 proxy calendar).

**Action:** No action needed. This is expected behavior.

### Consecutive failures ≥ 3

Dashboard will show 3+ consecutive failures in G1.

**Action:**
1. Check `hybrid_forward_run_log` for `error_summary` on each failed run.
2. Check if DailyPrice collector is running.
3. Check if production ForwardSignal pipeline is healthy.
4. Alert the research team if failures extend beyond 1 week.

---

## GitHub Actions (Future — DEPLOYMENT BLOCKED)

The workflow `.github/workflows/hybrid_forward_shadow.yml` exists but the schedule is commented out.

To enable it, you must first choose a persistence backend (see `hybrid_forward_operational_validation.md`
Section E) and obtain human approval. Steps:

1. Choose Option A, B, or C from the workflow comments.
2. Add the persistence download step (before the shadow run step).
3. Add the persistence upload step (after the shadow run step).
4. Uncomment the `schedule:` block.
5. Test with a manual `workflow_dispatch` run with `confirm_persistence=YES`.
6. Verify that `data/platform.db` is restored correctly on a second manual run.

**Do NOT enable the schedule without completing the above steps.**

---

## Schema Reference

Tables written by this pipeline (all in `data/platform.db`):

| Table | Purpose | Mutability |
|-------|---------|-----------|
| `hybrid_forward_decision` | One row per stock per trade_date per rule_version | Append-only |
| `hybrid_forward_outcome` | Matured holding-period returns | Append-only |
| `hybrid_forward_run_log` | One row per execution, tracks status | Upsert (same run_id only) |

For full schema DDL see `src/research/hybrid_forward_db.py` → `SCHEMA_SQL`.

---

## Safety Checklist Before Any Schema Change

- [ ] No change to `MODEL_VERSION` v8.0
- [ ] No change to `foe_v1` thresholds
- [ ] No change to `BUY / STRONG BUY` score gates
- [ ] No write to production Neon PostgreSQL
- [ ] No modification of existing `hybrid_forward_decision` rows
- [ ] All existing tests still pass: `python3 -m pytest tests/ -q`
- [ ] Lint clean: `ruff check src/ scripts/ tests/`
- [ ] `RULE_VERSION` = "hybrid_v1" and `RULE_FREEZE_DATE` = 2026-11-05 unchanged

---

## Contacts / Escalation

- Research pipeline owner: Alice Tu
- Production deployment: requires explicit authorization (see Phase 1B runbook)
- Neon database: requires separate approval — this pipeline does NOT touch Neon
