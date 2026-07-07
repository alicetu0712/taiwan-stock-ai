"""
data_validator.py — 資料驗證層（PRD Chapter 2.4）

AI 不得直接分析未驗證資料。
本模組確認資料完整性、合理性後，才允許進入分析流程。
"""

import logging
from datetime import date
from typing import Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    pass


class DataValidator:
    """
    驗證資料是否符合品質標準。
    驗證項目：
      - 是否更新成功（非空）
      - 是否有缺漏
      - 是否有重複
      - 是否有異常值
    """

    PRICE_ABNORMAL_THRESHOLD = 1e9  # 成交量/金額異常門檻
    MIN_VALID_STOCKS = 100  # 最少需要幾檔股票資料才視為有效

    def validate_price_data(
        self, df: pd.DataFrame, trade_date: date
    ) -> Tuple[bool, str]:
        """
        驗證每日股價資料。
        回傳 (is_valid, message)
        """
        if df is None or df.empty:
            return False, "股價資料為空，今日資料尚未完整更新。"

        # 檢查必要欄位
        required = ["stock_id", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return False, f"股價資料缺少必要欄位: {missing}"

        # 檢查筆數
        n = len(df)
        if n < self.MIN_VALID_STOCKS:
            return False, f"股價資料筆數過少（{n} 筆），可能尚未完整更新。"

        # 檢查同一天重複的 (stock_id, date) 才是真正的重複
        if "date" in df.columns:
            dup_count = df.duplicated(subset=["stock_id", "date"]).sum()
            if dup_count > 0:
                logger.warning(
                    f"股價資料有 {dup_count} 筆重複 (stock_id, date)，已自動去重。"
                )
                df.drop_duplicates(subset=["stock_id", "date"], inplace=True)

        # 異常值偵測（成交量異常大）
        if "volume" in df.columns:
            abn_vol = df[df["volume"] > self.PRICE_ABNORMAL_THRESHOLD]
            if not abn_vol.empty:
                sids = abn_vol["stock_id"].tolist()[:5]
                logger.warning(f"偵測到成交量異常值，已排除: {sids}")
                df.drop(abn_vol.index, inplace=True)

        # 檢查收盤價合理性（不應為 0 或負數）
        invalid_close = df[(df["close"].isna()) | (df["close"] <= 0)]
        if len(invalid_close) > len(df) * 0.2:
            return (
                False,
                f"超過 20% 的股票收盤價異常（{len(invalid_close)} 筆），資料可能不完整。",
            )

        logger.info(f"股價資料驗證通過：{len(df)} 筆 | 日期：{trade_date}")
        return True, "OK"

    def validate_institutional_data(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        驗證三大法人資料。
        """
        if df is None or df.empty:
            logger.warning("今日法人資料尚未更新，籌碼分析將跳過。")
            return False, "今日法人資料尚未完整更新。"

        if len(df) < 50:
            return False, f"法人資料筆數過少（{len(df)} 筆）。"

        required = ["stock_id", "total_net"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return False, f"法人資料缺少欄位: {missing}"

        logger.info(f"法人資料驗證通過：{len(df)} 筆")
        return True, "OK"

    def validate_financial_data(
        self,
        stock_id: str,
        summary: dict,
    ) -> Tuple[bool, str]:
        """
        驗證個股財務資料。
        若 has_data = False，不得進行基本面分析。
        """
        if not summary.get("has_data", False):
            return False, f"{stock_id}：財務資料不足，跳過基本面分析。"

        eps_ttm = summary.get("eps_ttm")
        if eps_ttm is not None and abs(eps_ttm) > 1000:
            return False, f"{stock_id}：EPS 數值異常（{eps_ttm}），可能為資料錯誤。"

        return True, "OK"

    def validate_history_depth(
        self,
        df: pd.DataFrame,
        stock_id: str,
        min_days: int = 60,
    ) -> Tuple[bool, str]:
        """
        驗證歷史股價資料深度是否足夠進行技術分析。
        """
        stock_df = df[df["stock_id"] == stock_id]
        if len(stock_df) < min_days:
            return (
                False,
                f"{stock_id}：歷史資料不足 {min_days} 天（{len(stock_df)} 天），跳過技術分析。",
            )
        return True, "OK"

    def generate_data_quality_report(
        self,
        price_valid: bool,
        inst_valid: bool,
        n_financial_ok: int,
        n_total: int,
    ) -> dict:
        """
        生成資料品質摘要供 Dashboard 顯示。
        """
        return {
            "price_data": "✅ 正常" if price_valid else "❌ 異常",
            "institutional_data": "✅ 正常" if inst_valid else "⚠️ 缺漏",
            "financial_coverage": f"{n_financial_ok}/{n_total} 筆有財務資料",
            "overall_status": "完整" if (price_valid and inst_valid) else "部分缺漏",
        }
