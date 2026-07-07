"""
db.py — Database module bootstrap.

Uses importlib to load src/database.py by absolute path so the module works
regardless of the current working directory (Streamlit Cloud vs. local).
Importing this module registers src.database in sys.modules, allowing
subsequent `from src.database import ...` calls anywhere in the process.
"""

import importlib.util as _ilu
import sys
from pathlib import Path

_db_path = Path(__file__).resolve().parent.parent / "src" / "database.py"
_db_spec = _ilu.spec_from_file_location("src.database", str(_db_path))
_db_mod = _ilu.module_from_spec(_db_spec)
sys.modules.setdefault("src.database", _db_mod)
_db_spec.loader.exec_module(_db_mod)

get_session = _db_mod.get_session
UserTrade = _db_mod.UserTrade
DailyPrice = _db_mod.DailyPrice
Recommendation = _db_mod.Recommendation
AnalysisResult = _db_mod.AnalysisResult
PositionMonitor = _db_mod.PositionMonitor
Stock = _db_mod.Stock
