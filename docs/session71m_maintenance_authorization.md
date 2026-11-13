# Session 71M — Maintenance Authorization

**Session**: 71M  
**Verdict**: `MAINTENANCE_OVERRIDE_CONTROLLED` (best achievable on single-user macOS)

---

## Requirement

The spec requires maintenance override to:
- Explicitly distinguish scheduled execution from manual maintenance
- Not be accidentally activated by routine scheduled runs
- Have an auditable usage record
- Not rely on a single env var alone

---

## Implementation: Two-Key Override

```python
# BACKFILL_ALLOW_DIRECT=1       alone → MAINTENANCE_AUTHORIZATION_INCOMPLETE (blocked)
# BACKFILL_MAINTENANCE_REASON  alone → no effect
# BOTH set → AUTHORIZED_MAINTENANCE with reason logged

allow_direct = os.environ.get(cls.ALLOW_DIRECT_KEY) == "1"
maintenance_reason = os.environ.get(cls.MAINTENANCE_REASON_KEY, "").strip()
if allow_direct and maintenance_reason:
    return True, f"AUTHORIZED_MAINTENANCE: ... reason='{maintenance_reason[:100]}'"
if allow_direct and not maintenance_reason:
    return False, "MAINTENANCE_AUTHORIZATION_INCOMPLETE: ..."
```

**Key properties**:
1. Setting `BACKFILL_ALLOW_DIRECT=1` alone now FAILS (not just warns)
2. `BACKFILL_MAINTENANCE_REASON` requires a non-empty string (empty string = blocked)
3. Reason is logged prominently in the output
4. Requires deliberate action to set both env vars

---

## Why Not Stronger

| Approach | Why Not Used |
|---|---|
| sudo/PAM authentication | Requires OS-level config changes; outside project scope |
| Signed token file | Requires key management infrastructure |
| Time-limited OTP | Requires a secret shared between maintenance operator and system |
| SSH key proof | Requires SSH daemon and key infrastructure |

On a single-user macOS system with no multi-user enforcement, cryptographic authorization is not achievable within the project's constraints. The two-key approach provides:
- **Accident prevention**: Two deliberate actions required (not one)
- **Audit trail**: Reason string is logged
- **Semantic distinction**: Scheduled run never sets these env vars

---

## Usage Instructions (for future authorized maintenance)

```bash
# Step 1: Verify no wrapper is running
pgrep -f hybrid_shadow_cron.py && echo "WRAPPER RUNNING - ABORT" || echo "Safe to proceed"

# Step 2: Document the reason
export BACKFILL_ALLOW_DIRECT=1
export BACKFILL_MAINTENANCE_REASON="Manual recovery run 2026-11-12: gap from Oct 29-Nov 05"

# Step 3: Run with explicit date range
python3 scripts/backfill_daily_prices_guarded.py \
    --start 2026-10-29 --end 2026-11-05 --execute

# Step 4: Clear env vars after use
unset BACKFILL_ALLOW_DIRECT BACKFILL_MAINTENANCE_REASON
```

**NOT authorized in S71M** — this is a future procedure definition only.

---

## Test Coverage

- M-06: Single key → BLOCKED ✓
- M-07: Two-key → AUTHORIZED ✓
- M-07b: `check_original_entry()` two-key unit test ✓
