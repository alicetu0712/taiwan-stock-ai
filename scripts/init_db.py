"""
scripts/init_db.py — 初始化資料庫

執行：python scripts/init_db.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db

if __name__ == "__main__":
    engine = init_db()
    print(f"✅ 資料庫初始化成功。")
