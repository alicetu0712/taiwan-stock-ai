"""
run_and_sync.py — 分析 + 同步一鍵完成

用法：
  python3 run_and_sync.py
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

NEON_URL = os.getenv("NEON_URL") or os.getenv("DATABASE_URL")
if not NEON_URL:
    print("❌ 請設定 NEON_URL 環境變數（.env 檔案）")
    sys.exit(1)

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
