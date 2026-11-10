# Prospective Recorder Prototype — Session 51

**Analysis date**: 2026-11-10  
**Session**: S51  
**Module**: `src/research/prospective_recorder_s51.py` → `ProspectiveRecorderPrototype`

---

## Purpose

A research-only, append-only SQLite recorder for prospective decision evidence. It **never** writes to `platform.db` or any production system.

---

## Safety Constraints

- Constructor raises `ValueError` if `db_path` contains `"platform.db"`
- Default path: `tempfile.NamedTemporaryFile(suffix=".db", delete=False)` — deleted on `close()`
- Implements context manager (`__enter__`/`__exit__`) for safe resource cleanup
- Schema: `prospective_decisions` (append-only via `INSERT OR IGNORE`) + `recorder_meta`

---

## Schema

```sql
CREATE TABLE prospective_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fill_date TEXT NOT NULL,
    signal_id INTEGER NOT NULL,
    stock_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    trade_signal TEXT NOT NULL,
    v3_snapshot TEXT,
    classification TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    UNIQUE(fill_date, signal_id, stock_id, model_version)
);

CREATE TABLE recorder_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

---

## ImmutableDecisionPayload

Fields immutable for fingerprint:
- `fill_date`, `signal_id`, `stock_id`, `model_version`, `locked_at`, `trade_signal`, `classification`

`research_fingerprint` = SHA-256[:16] of these fields serialized as sorted JSON.  
`verify()` recomputes the fingerprint and returns `True` if it matches stored value.

---

## `register()` Idempotency

Uses `INSERT OR IGNORE` on a `UNIQUE(fill_date, signal_id, stock_id, model_version)` constraint.  
Returns `True` if newly inserted, `False` if duplicate (uses `cursor.rowcount == 1`, not `total_changes`).

---

## `verify_all()`

Iterates all stored records, calls `.verify()` on each, returns `(valid_count, invalid_count)`.  
Any `invalid_count > 0` indicates post-registration mutation — treat as integrity failure.

---

## Usage Pattern

```python
from src.research.prospective_recorder_s51 import (
    ProspectiveRecorderPrototype,
    ImmutableDecisionPayload,
    DecisionClassification,
)
from datetime import datetime, timezone

with ProspectiveRecorderPrototype() as recorder:
    payload = ImmutableDecisionPayload(
        fill_date="2026-11-15",
        signal_id=12345,
        stock_id="2330",
        model_version="v8.0",
        locked_at=datetime.now(timezone.utc).isoformat(),
        trade_signal="buy",
        v3_decision_snapshot=None,  # None until V3 activated
        classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
        registered_at=datetime.now(timezone.utc).isoformat(),
    )
    inserted = recorder.register(payload)
    valid, invalid = recorder.verify_all()
    assert invalid == 0
```

---

## Limitations

- Research prototype only; not connected to production pipeline
- V3_DECISION_PROSPECTIVE records require `v3_decision_snapshot` (not None) and V3 activation
- Temp file is deleted on `close()`; for persistent research snapshots, pass an explicit `db_path`
