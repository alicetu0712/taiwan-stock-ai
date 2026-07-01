"""
run_and_sync.py — 分析 + 同步一鍵完成

用法：
  python3 run_and_sync.py
"""

import sys
import subprocess
from pathlib import Path

NEON_URL = (
    "postgresql://neondb_owner:npg_JFIrfHWh56Ka"
    "@ep-raspy-paper-aozvpvba-pooler.c-2.ap-southeast-1.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
)

base = Path(__file__).parent

print("=" * 50)
print("Step 1/2  執行今日分析...")
print("=" * 50)
r1 = subprocess.run([sys.executable, str(base / "main.py")], cwd=base)

if r1.returncode != 0:
    print("\n❌ 分析失敗，中止同步。")
    sys.exit(1)

print("\n" + "=" * 50)
print("Step 2/2  同步至 Neon（手機版）...")
print("=" * 50)
subprocess.run([
    sys.executable,
    str(base / "scripts" / "sync_to_neon.py"),
    "--db-url", NEON_URL,
], cwd=base)

print("\n✅ 完成！手機重整 dashboard 即可查看。")
