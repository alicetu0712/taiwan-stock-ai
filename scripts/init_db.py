"""
scripts/init_db.py — 初始化資料庫

執行：python scripts/init_db.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db

if __name__ == "__main__":
    # allow_ddl=True: 明確允許建立全部資料表（包含 Phase 1 trade lifecycle 新表）。
    # 此腳本為有意為之的 DDL 工具，不受生產保護限制。
    engine = init_db(allow_ddl=True)
    print("✅ 資料庫初始化成功。")
