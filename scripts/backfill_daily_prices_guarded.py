"""
backfill_daily_prices_guarded.py — Safe DailyPrice backfill with S71M entry guard

Entry guard (S71M): --execute requires authorized context (lock-based check).
See BackfillEntryGuard.check_original_entry() in scheduler_safety_guards.py.

SAFETY CONSTRAINTS (enforced at startup):
  1. Only writes to local SQLite (data/platform.db) — NEVER to production Neon.
  2. Verifies target file is SQLite before any write.
  3. Dry-run is DEFAULT — requires --execute to actually write.
  4. Idempotent: INSERT OR IGNORE skips existing (stock_id, date) rows.
  5. Quality gate must pass before any date is committed.

Data sources (read-only):
  - TWSE: https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date=YYYYMMDD
  - TPEx: https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes?d=RRRMMDD
           where RRR = ROC year (民國年), e.g. 2026 → 115

Usage:
  # Dry-run (default) — shows what would be written, no DB changes
  python scripts/backfill_daily_prices.py

  # Specific date range, dry-run
  python scripts/backfill_daily_prices.py --start 2026-10-29 --end 2026-11-05

  # Actually write (requires explicit flag)
  python scripts/backfill_daily_prices.py --start 2026-10-29 --end 2026-11-05 --execute

  # Single date
  python scripts/backfill_daily_prices.py --start 2026-11-05 --end 2026-11-05 --execute
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import date, timedelta
from typing import List, Optional, Tuple

from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH
from scripts.scheduler_safety_guards import BackfillEntryGuard
from src.core.trading_calendar import TaiwanTradingCalendar
from src.research.dailyprice_quality_gate import run_quality_gate

# ── Constants ─────────────────────────────────────────────────────────────────

TWSE_HIST_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date={yyyymmdd}"
TWSE_LATEST_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_HIST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes?d={roc_date}"
TPEX_LATEST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockResearch/6.0 Backfill)"}
HTTP_TIMEOUT = 30
HTTP_RETRY = 3
HTTP_PAUSE = 2.0  # seconds between requests (rate limiting)

EXCLUDE_KEYWORDS = [
    "ETF", "ETN", "REIT", "REITs", "特別股", "受益憑證",
    "DR", "DEPOSITARY", "WARRANT", "WARRANTS",
]
_CALENDAR = TaiwanTradingCalendar()

# Production lock file path (must match hybrid_shadow_cron.py's LOCK_FILE)
_DEFAULT_LOCK_FILE = Path(DB_PATH).parent / ".cron.lock"


def _get_cron_lock_path(db_path=None, _override=None):
    """Derive .cron.lock path. _override and BACKFILL_LOCK_PATH are for test isolation only."""
    if _override:
        return Path(_override)
    env_override = os.environ.get("BACKFILL_LOCK_PATH")
    if env_override:
        return Path(env_override)
    if db_path and db_path != ":memory:":
        return Path(db_path).parent / ".cron.lock"
    return _DEFAULT_LOCK_FILE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_roc_date(d: date) -> str:
    """Convert Gregorian date to ROC date string RRR/MM/DD (e.g. 2026-10-29 → 115/10/29)."""
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def _to_roc_param(d: date) -> str:
    """RRRMMDD format for TPEx API query param (e.g. 2026-10-29 → 1151029)."""
    return f"{d.year - 1911}{d.month:02d}{d.day:02d}"


def _strip_num(s: str) -> Optional[float]:
    """Parse comma-formatted number string; return None if '--' or empty."""
    if not s:
        return None
    s = s.strip()
    if s in ("--", "-", "N/A", ""):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _is_excluded(name: str, stock_id: str) -> bool:
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4:
        return True
    return False


def _get(url: str) -> Optional[object]:
    for attempt in range(HTTP_RETRY):
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, verify=False)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  [attempt {attempt+1}/{HTTP_RETRY}] GET {url} → {e}")
            if attempt < HTTP_RETRY - 1:
                time.sleep(2 ** attempt)
    return None


# ── TWSE historical fetch ─────────────────────────────────────────────────────

def _parse_twse_openapi_list(data: list, fallback_date: date) -> Tuple[pd.DataFrame, Optional[date]]:
    """Parse TWSE OpenAPI v1 list-of-dicts response (STOCK_DAY_ALL new format)."""
    api_date: Optional[date] = None
    records = []
    for row in data:
        sid = str(row.get("Code", "")).strip()
        name = str(row.get("Name", "")).strip()
        if not sid or _is_excluded(name, sid):
            continue
        # Date field is ROC format: "1151104"
        if api_date is None:
            roc_str = str(row.get("Date", "")).strip()
            if len(roc_str) == 7:
                try:
                    api_date = date(int(roc_str[:3]) + 1911, int(roc_str[3:5]), int(roc_str[5:7]))
                except Exception:
                    pass
        try:
            vol_raw = _strip_num(str(row.get("TradeVolume", "")))
            amt_raw = _strip_num(str(row.get("TradeValue", "")))
            o = _strip_num(str(row.get("OpeningPrice", "")))
            h = _strip_num(str(row.get("HighestPrice", "")))
            lo = _strip_num(str(row.get("LowestPrice", "")))
            c = _strip_num(str(row.get("ClosingPrice", "")))
        except Exception:
            continue
        if o is None and h is None and lo is None and c is None:
            continue
        records.append({
            "stock_id": sid,
            "name": name,
            "date": api_date or fallback_date,
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": (vol_raw / 1_000) if vol_raw is not None else None,
            "amount": (amt_raw / 1_000_000) if amt_raw is not None else None,
            "change_pct": None,
        })
    df = pd.DataFrame(records)
    return df, api_date


def fetch_twse_historical(d: date) -> Tuple[pd.DataFrame, Optional[date]]:
    """
    Fetch all TWSE listed stocks for date d.
    Strategy:
      1. Try classic TWSE URL (supports historical dates in some cases)
      2. Fall back to TWSE OpenAPI v1 (always returns most recent day)
    If the api_date in the response != d, the QG-5 check will block the write.
    Returns (DataFrame, actual_api_date).
    volume in 千股, amount in 百萬元.
    """
    # Try classic historical URL first
    url = TWSE_HIST_URL.format(yyyymmdd=d.strftime("%Y%m%d"))
    print(f"  TWSE historical: GET {url}")
    data = _get(url)
    if not data:
        # Fallback: try TWSE OpenAPI v1 (returns most recent day, date may differ from d)
        print(f"  TWSE old API failed for {d} — falling back to TWSE OpenAPI v1")
        fallback_data = _get(TWSE_LATEST_URL)
        if not fallback_data or not isinstance(fallback_data, list):
            print(f"  TWSE: both old URL and OpenAPI failed for {d}")
            return pd.DataFrame(), None
        df, api_date = _parse_twse_openapi_list(fallback_data, d)
        print(f"  TWSE OpenAPI fallback: {len(df)} stocks parsed (api_date={api_date})")
        return df, api_date

    # Old API returns {"stat": "OK", "date": "YYYYMMDD", "fields": [...], "data": [[...], ...]}
    if isinstance(data, dict):
        stat = data.get("stat", "")
        if stat not in ("OK", "ok"):
            print(f"  TWSE: stat={stat!r} — market closed or no data for {d}")
            return pd.DataFrame(), None
        rows = data.get("data", [])
        raw_date_str = data.get("date", "")
        try:
            api_date = date(int(raw_date_str[:4]), int(raw_date_str[4:6]), int(raw_date_str[6:8]))
        except Exception:
            api_date = None
    elif isinstance(data, list):
        # New OpenAPI v1 format (list of dicts)
        df, api_date = _parse_twse_openapi_list(data, d)
        print(f"  TWSE OpenAPI format: {len(df)} stocks parsed (api_date={api_date})")
        return df, api_date

    # Parse old API dict format
    # Field order (typical): [0]=code, [1]=name, [2]=volume, [3]=txn, [4]=amount,
    #                         [5]=open, [6]=high, [7]=low, [8]=close, [9]=dir, [10]=change
    records = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 9:
            continue
        sid = str(row[0]).strip()
        name = str(row[1]).strip()
        if not sid or _is_excluded(name, sid):
            continue
        try:
            vol_raw = _strip_num(row[2])  # shares
            amt_raw = _strip_num(row[4])  # TWD
            o = _strip_num(row[5])
            h = _strip_num(row[6])
            lo = _strip_num(row[7])
            c = _strip_num(row[8])
            # Compute change_pct from change_amount (row[10]) and reference price
            change_amt = _strip_num(row[10]) if len(row) > 10 else None
            prev_close = (c - change_amt) if (c is not None and change_amt is not None) else None
            chg_pct = (change_amt / prev_close * 100) if (prev_close and prev_close != 0) else None
        except Exception:
            continue
        if o is None and h is None and lo is None and c is None:
            continue
        records.append({
            "stock_id": sid,
            "name": name,
            "date": api_date or d,
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": (vol_raw / 1_000) if vol_raw is not None else None,  # 千股
            "amount": (amt_raw / 1_000_000) if amt_raw is not None else None,  # 百萬元
            "change_pct": chg_pct,
        })

    df = pd.DataFrame(records)
    print(f"  TWSE: {len(df)} stocks parsed (api_date={api_date})")
    return df, api_date


# ── TPEx historical fetch ─────────────────────────────────────────────────────

def fetch_tpex_historical(d: date) -> Tuple[pd.DataFrame, Optional[date]]:
    """
    Fetch all TPEx listed stocks for date d using TPEx OpenAPI v1 with ROC date param.
    Returns (DataFrame, actual_api_date).
    """
    roc_param = _to_roc_param(d)
    url = TPEX_HIST_URL.format(roc_date=roc_param)
    print(f"  TPEx historical: GET {url}")
    data = _get(url)
    if not data:
        print(f"  TPEx: no response for {d}")
        return pd.DataFrame(), None

    if not isinstance(data, list) or len(data) == 0:
        print(f"  TPEx: unexpected response type {type(data)} for {d}")
        return pd.DataFrame(), None

    records = []
    api_date: Optional[date] = None
    for row in data:
        sid = str(row.get("SecuritiesCompanyCode", "")).strip()
        name = str(row.get("CompanyName", "")).strip()
        if not sid or _is_excluded(name, sid):
            continue
        # Parse ROC date from row if available (e.g. "1151029")
        if api_date is None:
            roc_str = str(row.get("Date", "")).strip()
            if len(roc_str) == 7:
                try:
                    api_date = date(int(roc_str[:3]) + 1911, int(roc_str[3:5]), int(roc_str[5:7]))
                except Exception:
                    pass
        try:
            vol_raw = _strip_num(str(row.get("TradeVolume", "")))
            amt_raw = _strip_num(str(row.get("TradeValue", "")))
            o = _strip_num(str(row.get("Open", "")))
            h = _strip_num(str(row.get("High", "")))
            lo = _strip_num(str(row.get("Low", "")))
            c = _strip_num(str(row.get("Close", "")))
            chg_pct = _strip_num(str(row.get("Change", "")))
        except Exception:
            continue
        if o is None and h is None and lo is None and c is None:
            continue
        records.append({
            "stock_id": sid,
            "name": name,
            "date": api_date or d,
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": (vol_raw / 1_000) if vol_raw is not None else None,
            "amount": (amt_raw / 1_000_000) if amt_raw is not None else None,
            "change_pct": chg_pct,
        })

    df = pd.DataFrame(records)
    print(f"  TPEx: {len(df)} stocks parsed (api_date={api_date})")
    return df, api_date


# ── Safety checks ──────────────────────────────────────────────────────────────

def _verify_sqlite(db_path: str) -> None:
    """Abort if db_path is not a local SQLite file."""
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"DB not found: {db_path}")
    with open(db_path, "rb") as f:
        header = f.read(16)
    if not header.startswith(b"SQLite format 3"):
        raise ValueError(f"SAFETY: {db_path} is not a SQLite file — aborting")
    # Also check it's not a URL to PostgreSQL
    abs_path = os.path.abspath(db_path)
    if "neon" in abs_path.lower() or "postgresql" in abs_path.lower():
        raise ValueError(f"SAFETY: db_path looks like PostgreSQL reference: {abs_path}")
    print(f"[safety] Verified SQLite: {os.path.basename(db_path)} ✓")


def _find_missing_dates(
    conn: sqlite3.Connection,
    start: date,
    end: date,
    min_covered_stocks: Optional[int] = None,
) -> List[date]:
    """Return trading days in [start, end] that need a full-universe fetch.

    A date needs fetching if:
      - 0050 has no data (completely missing), OR
      - 0050 is present but fewer than min_covered_stocks non-0050 stocks have data
        (indicates 0050 was manually recovered while full universe was not fetched).

    min_covered_stocks: override threshold (default: _MIN_COVERED_STOCKS = 1,000).
                        Pass 0 or None-like to disable coverage check (0050-only mode).
    """
    threshold = _MIN_COVERED_STOCKS if min_covered_stocks is None else min_covered_stocks

    existing_0050 = {
        r[0] for r in conn.execute(
            "SELECT date FROM daily_prices WHERE stock_id='0050' AND date >= ? AND date <= ?",
            (str(start), str(end)),
        ).fetchall()
    }

    # For dates where 0050 exists, check whether full-universe coverage meets threshold
    covered_dates: set = set()
    if existing_0050 and threshold > 0:
        rows = conn.execute(
            """
            SELECT date, COUNT(DISTINCT stock_id) AS cnt
            FROM daily_prices
            WHERE stock_id != '0050' AND date >= ? AND date <= ?
              AND date IN ({})
            GROUP BY date
            HAVING cnt >= ?
            """.format(",".join("?" * len(existing_0050))),
            [str(start), str(end)] + list(existing_0050) + [threshold],
        ).fetchall()
        covered_dates = {r[0] for r in rows}
    elif existing_0050 and threshold == 0:
        # Legacy mode: 0050 presence is sufficient
        covered_dates = existing_0050

    missing = []
    d = start
    while d <= end:
        if _CALENDAR.is_trading_day(d) and str(d) not in covered_dates:
            missing.append(d)
        d += timedelta(days=1)
    return missing


# ── Write helpers ──────────────────────────────────────────────────────────────

def _write_df_to_sqlite(conn: sqlite3.Connection, df: pd.DataFrame) -> Tuple[int, int]:
    """
    INSERT OR IGNORE rows from df into daily_prices.
    Returns (inserted, skipped).
    """
    inserted = 0
    skipped = 0
    for _, row in df.iterrows():
        result = conn.execute(
            """
            INSERT OR IGNORE INTO daily_prices
                (stock_id, date, open, high, low, close, volume, amount, change_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["stock_id"]),
                str(row["date"]),
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row.get("volume"),
                row.get("amount"),
                row.get("change_pct"),
            ),
        )
        if result.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


# ── Main backfill logic ────────────────────────────────────────────────────────

def run_backfill(
    start: date,
    end: date,
    execute: bool = False,
    db_path: Optional[str] = None,
    _lock_path: Optional[str] = None,
) -> dict:
    """
    Backfill DailyPrice for missing trading days in [start, end].

    Parameters
    ----------
    execute    : if False (default), dry-run only — no DB writes.
    db_path    : override for the target SQLite file (default: config.DB_PATH).
    _lock_path : override lock file path for test isolation (not for production use).

    Returns summary dict. If guard blocks --execute, returns dict with guard_blocked=True.
    """
    if db_path is None:
        db_path = str(DB_PATH)

    # S71M Entry Guard (defense-in-depth; also checked in main())
    if execute:
        lock_path = _get_cron_lock_path(db_path, _lock_path)
        authorized, reason = BackfillEntryGuard.check_original_entry(
            is_execute=True, lock_path=lock_path
        )
        if not authorized:
            print(f"[BACKFILL_GUARD] BLOCKED: {reason}", file=sys.stderr)
            print("[BACKFILL_GUARD] No data was read or written.", file=sys.stderr)
            return {
                "dates_processed": 0, "total_inserted": 0, "total_skipped": 0,
                "errors": [f"GUARD_BLOCKED: {reason}"], "qg_results": [],
                "guard_blocked": True,
            }

    print(f"\n{'='*60}")
    print(f"DailyPrice Backfill — {'EXECUTE' if execute else 'DRY-RUN'}")
    print(f"Range: {start} → {end}")
    print(f"DB: {os.path.basename(db_path)}")
    print(f"{'='*60}\n")

    # Safety: verify SQLite
    _verify_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    try:
        missing_dates = _find_missing_dates(conn, start, end)
    finally:
        if not execute:
            conn.close()

    if not missing_dates:
        print("No missing trading days found — already up to date.")
        if execute:
            conn.close()
        return {"dates_processed": 0, "total_inserted": 0, "total_skipped": 0, "errors": []}

    print(f"Missing trading days ({len(missing_dates)}): {[str(d) for d in missing_dates]}\n")

    if not execute:
        print("[DRY-RUN] Would fetch the above dates. Re-run with --execute to write.\n")

    summary = {
        "dates_processed": 0,
        "total_inserted": 0,
        "total_skipped": 0,
        "errors": [],
        "qg_results": [],
    }

    for target_d in missing_dates:
        print(f"── {target_d} ─────────────────────────────")

        # Fetch TWSE
        twse_df, twse_api_date = fetch_twse_historical(target_d)
        time.sleep(HTTP_PAUSE)

        # Fetch TPEx
        tpex_df, tpex_api_date = fetch_tpex_historical(target_d)
        time.sleep(HTTP_PAUSE)

        # Validate API date matches target
        if twse_df.empty and tpex_df.empty:
            msg = f"{target_d}: both TWSE and TPEx returned empty — skipping"
            print(f"  [ERROR] {msg}")
            summary["errors"].append(msg)
            continue

        if twse_api_date and twse_api_date != target_d:
            msg = f"{target_d}: TWSE api_date={twse_api_date} != target — API returned wrong date"
            print(f"  [WARN] {msg}")
            summary["errors"].append(msg)
            # Don't abort — still run quality gate so it fails on QG-5

        if tpex_api_date and tpex_api_date != target_d:
            print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")

        # Run quality gate (TWSE requires 0050 benchmark; TPEx uses lower price bounds)
        qg_twse = run_quality_gate(twse_df, target_d, "TWSE", require_benchmark=True) if not twse_df.empty else None
        qg_tpex = run_quality_gate(tpex_df, target_d, "TPEx", require_benchmark=False) if not tpex_df.empty else None

        qg_ok = True
        for qg in [qg_twse, qg_tpex]:
            if qg is not None:
                print(f"  {qg.summary_str()}")
                summary["qg_results"].append(qg)
                if not qg.passed:
                    qg_ok = False
                    for issue in qg.issues:
                        if issue.severity == "error":
                            print(f"    [QG ERROR] {issue.check}: {issue.detail}")

        if not qg_ok:
            msg = f"{target_d}: quality gate FAILED — not writing to DB"
            print(f"  [BLOCKED] {msg}")
            summary["errors"].append(msg)
            continue

        summary["dates_processed"] += 1

        if not execute:
            twse_rows = len(twse_df)
            tpex_rows = len(tpex_df)
            print(f"  [DRY-RUN] Would insert ≤{twse_rows + tpex_rows} rows (after idempotency check)")
            continue

        # Write TWSE
        if not twse_df.empty:
            inserted_t, skipped_t = _write_df_to_sqlite(conn, twse_df)
            summary["total_inserted"] += inserted_t
            summary["total_skipped"] += skipped_t
            print(f"  TWSE: inserted={inserted_t}, skipped={skipped_t}")

        # Write TPEx
        if not tpex_df.empty:
            inserted_p, skipped_p = _write_df_to_sqlite(conn, tpex_df)
            summary["total_inserted"] += inserted_p
            summary["total_skipped"] += skipped_p
            print(f"  TPEx: inserted={inserted_p}, skipped={skipped_p}")

        conn.commit()
        print(f"  Committed {target_d} ✓")

    if execute:
        conn.close()

    print(f"\n{'='*60}")
    print(f"Backfill {'EXECUTE' if execute else 'DRY-RUN'} complete:")
    print(f"  dates_processed : {summary['dates_processed']}")
    if execute:
        print(f"  total_inserted  : {summary['total_inserted']}")
        print(f"  total_skipped   : {summary['total_skipped']}")
    print(f"  errors          : {len(summary['errors'])}")
    for e in summary["errors"]:
        print(f"    • {e}")
    print(f"{'='*60}\n")

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

_MIN_COVERED_STOCKS = 5_000  # minimum non-0050 stocks to consider a date fully covered
# Must stay in sync with full_market_freshness_gate.MIN_COVERED_STOCKS (also 5,000).
# A date with TWSE-only data (~1,976 stocks) stays in missing_dates → backfill retries TPEx.


def _default_start() -> date:
    """Default start: day after the last well-covered DailyPrice date.

    Uses the most recent date where >= _MIN_COVERED_STOCKS non-0050 stocks have data.
    This prevents 0050 (manually recovered) from masking gaps in the stock universe.
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        last_covered = conn.execute(
            """
            SELECT MAX(date) FROM (
                SELECT date FROM daily_prices
                WHERE stock_id != '0050'
                GROUP BY date
                HAVING COUNT(DISTINCT stock_id) >= ?
            )
            """,
            (_MIN_COVERED_STOCKS,),
        ).fetchone()[0]
        conn.close()
        if last_covered:
            return date.fromisoformat(last_covered) + timedelta(days=1)
    except Exception:
        pass
    return date.today()


def main() -> None:
    default_start = _default_start()
    parser = argparse.ArgumentParser(
        description="Backfill DailyPrice for local research SQLite. Dry-run by default."
    )
    parser.add_argument(
        "--start", default=str(default_start),
        help=f"Start date YYYY-MM-DD (default: day after last stored date = {default_start})"
    )
    parser.add_argument(
        "--end", default=str(date.today()),
        help=f"End date YYYY-MM-DD (default: today = {date.today()})"
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually write to DB. Without this flag, dry-run only."
    )
    parser.add_argument(
        "--db", default=None,
        help=f"Override DB path (default: {DB_PATH})"
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if start > end:
        print(f"[INFO] start={start} > end={end}: DB already current, nothing to backfill")
        sys.exit(0)

    # S71M Entry Guard at CLI (defense-in-depth: also checked in run_backfill)
    if args.execute:
        lock_path = _get_cron_lock_path(args.db)
        authorized, reason = BackfillEntryGuard.check_original_entry(
            is_execute=True, lock_path=lock_path
        )
        if not authorized:
            print(f"[BACKFILL_GUARD] BLOCKED: {reason}", file=sys.stderr)
            print("[BACKFILL_GUARD] No data was read or written.", file=sys.stderr)
            sys.exit(2)

    run_backfill(start=start, end=end, execute=args.execute, db_path=args.db)


if __name__ == "__main__":
    main()
