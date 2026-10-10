"""
portfolio_risk_service.py — 組合風險分析

用途：
- 從 PositionMonitor 計算當前持倉的產業集中度
- 為 render_rec_card() 提供「組合角度」上下文
- 不改變任何推薦決策，純粹是資訊展示層

只在有 active 持倉時才有意義；持倉為空時回傳空 dict。
"""

import logging

logger = logging.getLogger(__name__)

CONCENTRATION_THRESHOLDS = {
    "high":   50,  # 同產業 >= 50% 總配置 → 警告
    "medium": 35,  # 同產業 >= 35% → 注意
}


def compute_portfolio_exposure(positions: list, session=None) -> dict:
    """
    Takes load_positions("active") output (list of dicts with stock_id, position_pct).
    Returns portfolio risk context dict. Empty dict if no active positions.

    Return structure:
    {
        industry_weights: {industry: pct_of_total_allocation},
        industry_alloc:   {industry: raw_position_pct_sum},
        top_industry: str,
        top_industry_pct: float,
        max_stock_id: str,
        max_stock_name: str,
        max_stock_pct: float,          # % of total allocation
        concentration_level: "high" | "medium" | "low",
        total_allocated: float,
        n_positions: int,
    }
    """
    if not positions:
        return {}

    try:
        from src.database import Stock, get_session

        s = session or get_session()
        stock_rows = (
            s.query(Stock.stock_id, Stock.name, Stock.industry)
            .filter(Stock.stock_id.in_([p["stock_id"] for p in positions]))
            .all()
        )
        if not session:
            s.close()

        industry_map = {r.stock_id: (r.industry or "其他") for r in stock_rows}
        name_map     = {r.stock_id: (r.name or r.stock_id)  for r in stock_rows}
    except Exception as e:
        logger.warning(f"compute_portfolio_exposure DB query failed: {e}")
        industry_map = {}
        name_map = {}

    total_alloc = sum(p.get("position_pct") or 0 for p in positions)
    if total_alloc <= 0:
        return {}

    industry_alloc: dict = {}
    for p in positions:
        ind = industry_map.get(p["stock_id"], "其他")
        industry_alloc[ind] = industry_alloc.get(ind, 0) + (p.get("position_pct") or 0)

    industry_weights = {k: round(v / total_alloc * 100, 1) for k, v in industry_alloc.items()}

    top_industry = max(industry_alloc, key=industry_alloc.get)
    top_pct = round(industry_alloc[top_industry] / total_alloc * 100, 1)

    max_pos = max(positions, key=lambda p: p.get("position_pct") or 0)
    max_stock_pct = round((max_pos.get("position_pct") or 0) / total_alloc * 100, 1)

    if top_pct >= CONCENTRATION_THRESHOLDS["high"]:
        level = "high"
    elif top_pct >= CONCENTRATION_THRESHOLDS["medium"]:
        level = "medium"
    else:
        level = "low"

    return {
        "industry_weights":   industry_weights,
        "industry_alloc":     industry_alloc,
        "top_industry":       top_industry,
        "top_industry_pct":   top_pct,
        "max_stock_id":       max_pos["stock_id"],
        "max_stock_name":     name_map.get(max_pos["stock_id"], max_pos["stock_id"]),
        "max_stock_pct":      max_stock_pct,
        "concentration_level": level,
        "total_allocated":    total_alloc,
        "n_positions":        len(positions),
    }


def portfolio_context_for_stock(stock_industry: str | None, exposure: dict) -> dict:
    """
    Returns risk context message for a specific stock relative to current portfolio.

    Return structure:
    {
        same_industry_pct: float,   # % of portfolio already in this industry
        message: str,
        should_warn: bool,
    }
    """
    if not stock_industry or not exposure:
        return {"same_industry_pct": 0.0, "message": "", "should_warn": False}

    total_alloc = exposure.get("total_allocated", 0)
    if total_alloc <= 0:
        return {"same_industry_pct": 0.0, "message": "目前無持倉", "should_warn": False}

    industry_alloc = exposure.get("industry_alloc", {})
    same_alloc = industry_alloc.get(stock_industry, 0)
    same_pct = round(same_alloc / total_alloc * 100, 1)
    should_warn = same_pct >= CONCENTRATION_THRESHOLDS["medium"]

    if same_pct == 0:
        msg = f"目前持倉中無其他 {stock_industry} 部位"
    elif same_pct >= CONCENTRATION_THRESHOLDS["high"]:
        msg = f"⚠️ {stock_industry} 已佔持倉 {same_pct:.0f}%，再加碼集中度偏高"
    elif same_pct >= CONCENTRATION_THRESHOLDS["medium"]:
        msg = f"注意：{stock_industry} 已佔持倉 {same_pct:.0f}%"
    else:
        msg = f"{stock_industry} 已佔持倉 {same_pct:.0f}%"

    return {"same_industry_pct": same_pct, "message": msg, "should_warn": should_warn}
