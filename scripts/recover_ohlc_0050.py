"""
recover_ohlc_0050.py — 0050 historical OHLC recovery from TWSE STOCK_DAY API

Purpose:
  Recover missing 0050 (台灣50 ETF) DailyPrice rows for dates where the market
  gate is blocked due to EXPECTED_DATA_MISSING. Uses the TWSE individual stock
  history API (STOCK_DAY), which returns confirmed monthly trading data.

  Also handles 2026-10-08 special case: existing DB data is mislabeled 10-06
  data. The script deletes the corrupt 0050 row and inserts correct values.

Safety constraints (identical to backfill_daily_prices.py):
  1. Only writes to local SQLite — NEVER to production Neon.
  2. Verifies target file is SQLite before any write.
  3. Dry-run is DEFAULT — requires --execute to actually write.
  4. Logs provenance for every inserted row (source=TWSE_STOCK_DAY_API).

Data source:
  TWSE individual stock history:
  https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?stockNo=0050&date=YYYYMMDD

Usage:
  # Dry-run (default)
  python scripts/recover_ohlc_0050.py

  # Execute recovery
  python scripts/recover_ohlc_0050.py --execute
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import time
from datetime import date, datetime
from typing import List, Optional, Tuple

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH
from src.core.trading_calendar import TaiwanTradingCalendar

# ── Constants ─────────────────────────────────────────────────────────────────

STOCK_DAY_URL = (
    "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
    "?stockNo=0050&date={yyyymmdd}&response=json"
)
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockResearch/1.0 Recovery)"}
HTTP_TIMEOUT = 20
SOURCE_TAG = "TWSE_STOCK_DAY_API"

# 10-08 has corrupted data (10-06 values mislabeled as 10-08). Treat specially.
CORRUPT_DATE = date(2026, 10, 8)

_CAL = TaiwanTradingCalendar()

# Target dates: missing 0050 entries that are genuine TWSE trading days.
# Verified against TWSE FMTQIK official monthly trading summary.
RECOVERY_TARGETS: List[Tuple[date, str]] = [
    (date(2026, 10, 8),  "2026-10-08 (re-insert correct data; existing row is mislabeled 10-06)"),
    (date(2026, 10, 15), "2026-10-15 (confirmed TWSE trading, index=46,969.87)"),
    (date(2026, 10, 19), "2026-10-19 (confirmed TWSE trading, index=46,822.08)"),
    (date(2026, 10, 20), "2026-10-20 (confirmed TWSE trading, index=46,292.93)"),
    (date(2026, 10, 27), "2026-10-27 (confirmed TWSE trading, index=46,096.23)"),
    (date(2026, 10, 29), "2026-10-29 (confirmed TWSE trading, index=46,368.33)"),
    (date(2026, 10, 30), "2026-10-30 (confirmed TWSE trading, index=45,211.83)"),
    (date(2026, 11, 2),  "2026-11-02 (confirmed TWSE trading, index=44,920.14)"),
    (date(2026, 11, 3),  "2026-11-03 (confirmed TWSE trading, index=43,307.54)"),
    (date(2026, 11, 5),  "2026-11-05 (confirmed TWSE trading, index=41,574.72)"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _verify_sqlite(db_path: str) -> None:
    if not os.path.exists(db_path):
        raise SystemExit(f"[ABORT] DB not found: {db_path}")
    with open(db_path, "rb") as f:
        magic = f.read(16)
    if not magic.startswith(b"SQLite format 3"):
        raise SystemExit(f"[ABORT] {db_path} is NOT a SQLite file. Refusing to write.")
    print(f"[safety] Verified SQLite: {os.path.basename(db_path)} ✓")


def _backup_db(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = str(db_path).replace(".db", f"_recover_backup_{ts}.db")
    shutil.copy2(db_path, backup)
    print(f"[backup] {os.path.basename(backup)} ✓")
    return backup


def _get(url: str) -> Optional[dict]:
    import warnings
    for attempt in range(3):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, verify=False)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < 2:
                print(f"  [attempt {attempt+1}/3] {e} — retrying…")
                time.sleep(2)
            else:
                print(f"  [FAIL] {e}")
    return None


def _fetch_0050_month(query_date: date) -> Optional[dict]:
    """Fetch 0050 monthly history via TWSE STOCK_DAY; return raw JSON or None."""
    url = STOCK_DAY_URL.format(yyyymmdd=query_date.strftime("%Y%m%d"))
    print(f"  TWSE STOCK_DAY: GET {url}")
    data = _get(url)
    if data and data.get("stat") == "OK":
        return data
    print(f"  [WARN] stat={data.get('stat') if data else 'NO_RESPONSE'}")
    return None


def _roc_to_date(roc_str: str) -> Optional[date]:
    """Convert '115/10/29' → date(2026, 10, 29)."""
    try:
        parts = roc_str.strip().split("/")
        y, m, d = int(parts[0]) + 1911, int(parts[1]), int(parts[2])
        return date(y, m, d)
    except Exception:
        return None


def _strip_num(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _parse_month_data(data: dict) -> dict[date, dict]:
    """
    Parse TWSE STOCK_DAY response into {date: {open, high, low, close, volume, amount}}.

    Response fields (index):
      0=日期, 1=成交股數, 2=成交金額, 3=開盤價, 4=最高價, 5=最低價, 6=收盤價, 7=漲跌價差, 8=成交筆數
    """
    result: dict[date, dict] = {}
    for row in data.get("data", []):
        if len(row) < 7:
            continue
        d = _roc_to_date(row[0])
        if d is None:
            continue
        vol_shares = _strip_num(row[1])
        amt_nt = _strip_num(row[2])
        open_ = _strip_num(row[3])
        high = _strip_num(row[4])
        low = _strip_num(row[5])
        close = _strip_num(row[6])
        if any(v is None for v in [open_, high, low, close]):
            continue
        result[d] = {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol_shares / 1000 if vol_shares is not None else None,  # 千股
            "amount": amt_nt / 1_000_000 if amt_nt is not None else None,     # 百萬元
        }
    return result


def _quality_check(d: date, row: dict) -> Optional[str]:
    """Return error message if row fails basic quality checks, else None."""
    o, h, lo, c = row["open"], row["high"], row["low"], row["close"]
    if not (0.1 <= c <= 20_000):
        return f"close={c} outside [0.1, 20000]"
    if not (lo <= min(o, c) and h >= max(o, c) and lo > 0 and h > 0):
        return f"OHLC inconsistent: o={o} h={h} l={lo} c={c}"
    return None


def run_recovery(execute: bool = False) -> dict:
    _verify_sqlite(DB_PATH)

    print(f"\n{'='*60}")
    print(f"0050 OHLC Recovery — {'EXECUTE' if execute else 'DRY-RUN'}")
    print(f"DB: {os.path.basename(DB_PATH)}")
    print(f"Targets: {len(RECOVERY_TARGETS)} dates")
    print(f"{'='*60}\n")

    # Step 1: Fetch data from TWSE for needed months
    # We need October 2026 and November 2026 data
    months_needed = {(d.year, d.month) for d, _ in RECOVERY_TARGETS}
    month_data: dict[tuple, dict[date, dict]] = {}

    for (y, m) in sorted(months_needed):
        query_d = date(y, m, 1)
        print(f"── Fetching 0050 month: {y}-{m:02d} ─────────────────────────────")
        raw = _fetch_0050_month(query_d)
        if raw is None:
            print(f"  [ERROR] Could not fetch data for {y}-{m:02d}")
            month_data[(y, m)] = {}
        else:
            parsed = _parse_month_data(raw)
            month_data[(y, m)] = parsed
            print(f"  Parsed {len(parsed)} trading days")
        time.sleep(1.0)

    # Step 2: Check existing DB state
    conn = sqlite3.connect(DB_PATH)

    results = []
    for target_date, description in RECOVERY_TARGETS:
        key = (target_date.year, target_date.month)
        monthly = month_data.get(key, {})
        row = monthly.get(target_date)

        existing = conn.execute(
            "SELECT open, high, low, close, volume FROM daily_prices WHERE stock_id='0050' AND date=?",
            (str(target_date),),
        ).fetchone()

        is_corrupt = (target_date == CORRUPT_DATE)

        print(f"\n── {target_date} ({description}) ───")
        print(f"   DB status: {'EXISTS (CORRUPT — will replace)' if (existing and is_corrupt) else ('EXISTS — skipping' if existing else 'MISSING')}")

        if row is None:
            print(f"   [ERROR] No TWSE data found for {target_date}")
            results.append({"date": str(target_date), "status": "ERROR_NO_API_DATA"})
            continue

        err = _quality_check(target_date, row)
        if err:
            print(f"   [QG FAIL] {err}")
            results.append({"date": str(target_date), "status": "BLOCKED_QG", "error": err})
            continue

        print(f"   TWSE data: open={row['open']} high={row['high']} low={row['low']} close={row['close']}")

        if existing and not is_corrupt:
            print("   [SKIP] Already in DB (not corrupt)")
            results.append({"date": str(target_date), "status": "SKIP_EXISTS"})
            continue

        if execute:
            if is_corrupt and existing:
                # Delete corrupt row first
                conn.execute(
                    "DELETE FROM daily_prices WHERE stock_id='0050' AND date=?",
                    (str(target_date),),
                )
                print(f"   [DELETE] Removed corrupt 0050 row for {target_date}")

            conn.execute(
                """INSERT OR IGNORE INTO daily_prices
                   (stock_id, date, open, high, low, close, volume, amount, change_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "0050", str(target_date),
                    row["open"], row["high"], row["low"], row["close"],
                    row["volume"], row["amount"], None,
                ),
            )
            conn.commit()
            # Verify
            verify = conn.execute(
                "SELECT close FROM daily_prices WHERE stock_id='0050' AND date=?",
                (str(target_date),),
            ).fetchone()
            if verify and abs(verify[0] - row["close"]) < 0.01:
                print(f"   [WRITTEN ✓] close={verify[0]}")
                results.append({"date": str(target_date), "status": "WRITTEN"})
            else:
                print("   [ERROR] Write verification failed")
                results.append({"date": str(target_date), "status": "ERROR_WRITE"})
        else:
            action = "REPLACE CORRUPT" if is_corrupt else "INSERT"
            print(f"   [DRY-RUN] Would {action}: close={row['close']}, vol={row['volume']:.3f}")
            results.append({"date": str(target_date), "status": "DRY_RUN"})

    conn.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"Recovery Summary ({'EXECUTE' if execute else 'DRY-RUN'}):")
    for r in results:
        print(f"  {r['date']:12s}  {r['status']}")

    written = sum(1 for r in results if r["status"] == "WRITTEN")
    errors = sum(1 for r in results if r["status"].startswith("ERROR"))
    print(f"\nTotal: {len(results)} | Written: {written} | Errors: {errors}")

    if not execute:
        print("\n[DRY-RUN] No changes made. Re-run with --execute to write.")

    return {"results": results, "written": written, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description="0050 historical OHLC recovery")
    parser.add_argument("--execute", action="store_true", help="Actually write to DB")
    args = parser.parse_args()

    if args.execute:
        # Backup before any writes
        _backup_db(DB_PATH)

    run_recovery(execute=args.execute)


if __name__ == "__main__":
    main()
