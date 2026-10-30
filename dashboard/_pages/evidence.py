"""
dashboard/_pages/evidence.py — foe_v1 前向執行結果證據儀表板

本頁所有評估規則皆於資料累積前預先固定（Pre-Registered Protocol foe_v1）。
禁止因目前結果好看或不好看而修改評估定義。修改需升版至 foe_v2。
"""

import logging

import pandas as pd
import streamlit as st

from src.presentation.evidence_presenter import EvidencePresenter
from src.engines.outcome_evaluation import (
    EXCL_NO_OVERNIGHT_DATA,
    EXEC_DATA_INSUFFICIENT,
    EXEC_EXECUTED,
    EXEC_EXPIRED_BEFORE_ENTRY,
    EXEC_INVALIDATED_BEFORE_ENTRY,
    EXEC_PENDING,
    FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS,
    FORWARD_OUTCOME_PROTOCOL_VERSION,
    ODQ_COMPLETE,
    OUTCOME_SAME_DAY_AMBIGUOUS,
    OUTCOME_STOP_FIRST,
    OUTCOME_T1_FIRST,
    PATH_AWARE,
    PATH_BASELINE,
)

logger = logging.getLogger(__name__)

_EVIDENCE_PRESENTER = EvidencePresenter()


def _warn_if_small(n: int, label: str = ""):
    ss = _EVIDENCE_PRESENTER.sample_strength(n)
    if ss.is_insufficient:
        st.warning(
            f"{'[' + label + '] ' if label else ''}樣本不足（N={n}），僅供觀察，不具統計意義。"
        )
    elif ss.is_initial:
        st.info(
            f"{'[' + label + '] ' if label else ''}初步觀察階段（N={n}），結論需謹慎。"
        )


# ── Data loading ──────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_all_rows() -> pd.DataFrame:
    try:
        from src.database import ForwardOutcomeEvaluation, get_session

        s = get_session()
        rows = s.query(ForwardOutcomeEvaluation).all()
        if not rows:
            return pd.DataFrame()
        records = []
        for r in rows:
            records.append(
                {
                    "id": r.id,
                    "forward_signal_id": r.forward_signal_id,
                    "stock_id": r.stock_id,
                    "signal_date": r.signal_date,
                    "path_type": r.path_type,
                    "overnight_rule_version": r.overnight_rule_version,
                    "overnight_risk_level": r.overnight_risk_level,
                    "entry_status": r.entry_status,
                    "entry_date": r.entry_date,
                    "entry_price": r.entry_price,
                    # 20D
                    "return_20d": r.return_20d,
                    "alpha_20d": r.alpha_20d,
                    "mae_20d": r.mae_20d,
                    "mfe_20d": r.mfe_20d,
                    "target_stop_outcome_20d": r.target_stop_outcome_20d,
                    "outcome_data_quality_20d": r.outcome_data_quality_20d,
                    "horizon_20d_matured_at": r.horizon_20d_matured_at,
                    # 60D
                    "return_60d": r.return_60d,
                    "alpha_60d": r.alpha_60d,
                    "mae_60d": r.mae_60d,
                    "mfe_60d": r.mfe_60d,
                    "target_stop_outcome_60d": r.target_stop_outcome_60d,
                    "outcome_data_quality_60d": r.outcome_data_quality_60d,
                    "horizon_60d_matured_at": r.horizon_60d_matured_at,
                    # exclusion
                    "exclusion_reason": r.exclusion_reason,
                }
            )
        return pd.DataFrame(records)
    except Exception as e:
        logger.warning(f"[evidence] load failed: {e}")
        return pd.DataFrame()


def _versions() -> dict:
    try:
        from src.engines.overnight_risk import OVERNIGHT_RULE_VERSION
    except Exception:
        OVERNIGHT_RULE_VERSION = "—"
    try:
        from src.engines.live_decision import LIVE_RULE_VERSION
    except Exception:
        LIVE_RULE_VERSION = "—"
    return {
        "outcome_protocol": FORWARD_OUTCOME_PROTOCOL_VERSION,
        "overnight_rule": OVERNIGHT_RULE_VERSION,
        "live_rule": LIVE_RULE_VERSION,
        "aware_window": FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS,
    }


# ── Formal eligibility (single source of truth) ───────────────────────────────


def _formal_eligible(df: pd.DataFrame) -> pd.DataFrame:
    """
    P1: Formal overnight cohort requires exclusion_reason IS NULL.

    Rows with exclusion_reason = NO_OVERNIGHT_DATA (legacy signals) or any other
    exclusion must NOT appear in formal overnight evidence sections (B / C).
    Section D (Sample Health) still shows all rows including excluded ones.

    SQL note: NULL != 'X' evaluates to NULL (not TRUE), so a != filter would
    accidentally exclude eligible rows. Only IS NULL is correct here.
    """
    return df[df["exclusion_reason"].isna()].copy()


# ── Helper: matured rows subset ────────────────────────────────────────────────


def _matured_20d(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["horizon_20d_matured_at"].notna()].copy()


def _matured_60d(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["horizon_60d_matured_at"].notna()].copy()


def _resolved_stop_t1(df: pd.DataFrame, suffix: str) -> pd.DataFrame:
    col = f"target_stop_outcome_{suffix}"
    return df[df[col].isin([OUTCOME_T1_FIRST, OUTCOME_STOP_FIRST])].copy()


# ── Section A: 驗證進度白話摘要 ───────────────────────────────────────────────


def _section_progress_summary(df: pd.DataFrame):
    """A. 目前驗證進度與白話結論"""

    # Unique signals = unique forward_signal_id (baseline + aware share same signals)
    n_unique_signals = df["forward_signal_id"].nunique()

    # Baseline rows = canonical signal reference (one row per signal for baseline path)
    baseline_all = df[df["path_type"] == PATH_BASELINE]
    n_legacy = int((df["exclusion_reason"] == EXCL_NO_OVERNIGHT_DATA).sum() // 2
                   if (df["exclusion_reason"] == EXCL_NO_OVERNIGHT_DATA).sum() > 0
                   else 0)
    # More accurate: count unique signal_ids that are excluded
    n_legacy = df[df["exclusion_reason"] == EXCL_NO_OVERNIGHT_DATA]["forward_signal_id"].nunique()

    formal_baseline = _formal_eligible(baseline_all)
    n_formal = len(formal_baseline)
    n_pending = int((formal_baseline["entry_status"] == EXEC_PENDING).sum())
    n_matured_20d = int(formal_baseline["horizon_20d_matured_at"].notna().sum())
    n_matured_60d = int(formal_baseline["horizon_60d_matured_at"].notna().sum())

    # Determine overall readiness
    ss = _EVIDENCE_PRESENTER.sample_strength(n_matured_20d)

    # ── 頁面標題 ─────────────────────────────────────────────────────────────
    st.html(f"""
<div style="margin-bottom:16px">
  <div style="font-size:1.25rem;font-weight:800;color:#1a1a2e;margin-bottom:8px">
    🔒 選股驗證中心（Forward Evidence）
  </div>
  <div style="font-size:0.83rem;color:#37474f;line-height:1.75;background:#f0f4ff;
              border-left:4px solid #667eea;padding:11px 15px;border-radius:0 8px 8px 0">
    追蹤系統推薦的股票，後來表現如何？是否比 0050 更好？目前有沒有足夠證據支持策略？<br>
    <span style="font-size:0.78rem;color:#78909c">
      所有評估規則在資料累積前即已預先登記（Pre-Registered Protocol foe_v1），
      不因結果好壞而修改定義。
    </span>
  </div>
</div>""")

    st.markdown("### A. 目前驗證進度")

    # ── 進度指標 Grid ─────────────────────────────────────────────────────────
    st.html(f"""
<style>
@media (max-width: 640px) {{
  .ev-prog-grid {{ grid-template-columns: 1fr 1fr !important; }}
}}
</style>
<div class="ev-prog-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0 14px">
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">
      累積訊號數<br><span style="font-weight:400">（唯一訊號）</span>
    </div>
    <div style="font-size:1.3rem;font-weight:800;color:#1a1a2e">{n_unique_signals:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">
      每個訊號有兩條評估路徑
    </div>
  </div>
  <div style="background:#fff8e1;border-radius:10px;padding:14px 16px;text-align:center">
    <div style="font-size:0.7rem;color:#f57f17;font-weight:600;margin-bottom:4px">
      ⏳ 等待進場<br><span style="font-weight:400">（PENDING）</span>
    </div>
    <div style="font-size:1.3rem;font-weight:800;color:#e65100">{n_pending:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">
      進場窗口（3 交易日）尚未結束
    </div>
  </div>
  <div style="background:#e8f5e9;border-radius:10px;padding:14px 16px;text-align:center">
    <div style="font-size:0.7rem;color:#2e7d32;font-weight:600;margin-bottom:4px">
      ✅ 完成 20D 觀察<br><span style="font-weight:400">（成熟樣本）</span>
    </div>
    <div style="font-size:1.3rem;font-weight:800;color:{'#2e7d32' if n_matured_20d >= 10 else '#e65100'}">{n_matured_20d:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">
      可計算 20 個交易日後的報酬
    </div>
  </div>
  <div style="background:#e8f5e9;border-radius:10px;padding:14px 16px;text-align:center">
    <div style="font-size:0.7rem;color:#2e7d32;font-weight:600;margin-bottom:4px">
      ✅ 完成 60D 觀察<br><span style="font-weight:400">（成熟樣本）</span>
    </div>
    <div style="font-size:1.3rem;font-weight:800;color:{'#2e7d32' if n_matured_60d >= 10 else '#e65100'}">{n_matured_60d:,}</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">
      可計算 60 個交易日後的報酬
    </div>
  </div>
</div>""")

    # ── 白話結論 ─────────────────────────────────────────────────────────────
    if n_matured_20d == 0:
        st.warning(
            "⏳ **目前尚無完成觀察期的紀錄。**  \n"
            "無法判斷策略的實際勝率與超額報酬。"
            f"累積了 {n_formal} 個有效訊號，但尚無任何一筆在進場後經過完整的 20 個交易日。  \n"
            "請繼續每日執行 `run_daily.py`，等待觀察期陸續完成。"
        )
    elif ss.is_insufficient:
        st.warning(
            f"📊 **初步累積中（{n_matured_20d} 筆已完成 20D 觀察）。**  \n"
            "目前樣本太少，任何績效數字都不具統計意義，僅供觀察參考。  \n"
            "**目前不能得出結論：** 無法判定策略是否有效或無效。"
        )
    elif ss.is_initial:
        st.info(
            f"📊 **初步觀察階段（{n_matured_20d} 筆已完成 20D 觀察）。**  \n"
            "已有初步數據，但樣本尚不足以得出穩健結論，請謹慎解讀。"
        )
    else:
        st.success(
            f"✅ **已有 {n_matured_20d} 筆完成 20D 觀察，{n_matured_60d} 筆完成 60D 觀察。**  \n"
            "可開始進行初步統計評估，詳見下方 B 節績效摘要。"
        )

    if n_legacy > 0:
        st.caption(
            f"📌 注意：{n_legacy} 個訊號為 overnight_v1 上線前的舊紀錄（Legacy），"
            "因缺乏隔夜風險資料已標記排除，不納入正式評估，但仍顯示於 D 節。"
        )


# ── Section B: 20D / 60D 真實後續績效 ────────────────────────────────────────


def _section_performance(df: pd.DataFrame):
    """B. 20D / 60D 真實後續績效（僅成熟 formal 樣本）"""

    st.markdown("### B. 20D / 60D 真實後續績效")

    formal_baseline = _formal_eligible(df[df["path_type"] == PATH_BASELINE])

    # 20D
    m20 = _matured_20d(formal_baseline)
    valid20 = m20[m20["outcome_data_quality_20d"] == ODQ_COMPLETE]
    n20 = len(valid20)

    # 60D
    m60 = _matured_60d(formal_baseline)
    valid60 = m60[m60["outcome_data_quality_60d"] == ODQ_COMPLETE]
    n60 = len(valid60)

    if n20 == 0 and n60 == 0:
        st.info(
            "📋 尚無完成觀察期且資料品質完整的記錄，無法計算績效。  \n"
            "等待訊號進場後 20 個交易日（約 1 個月）後才可計算 20D 績效。"
        )
        return

    st.caption(
        "以下績效基於 **Baseline（BASELINE_NEXT_OPEN）路徑**：訊號產生次日開盤進場，"
        "不考慮隔夜風險調整。只納入資料品質完整（ODQ_COMPLETE）且已過完觀察期的記錄。  \n"
        "Alpha = 超額報酬 = 股票報酬 − 0050 同期報酬，正值代表跑贏大盤。"
    )

    def _perf_card(label_period: str, valid: pd.DataFrame, n: int):
        if n == 0:
            return {
                "label": label_period,
                "n": 0,
                "avg_return": None,
                "avg_alpha": None,
                "win_rate": None,
                "avg_mae": None,
                "avg_mfe": None,
            }
        win_rate = (valid["alpha_20d" if "20" in label_period else "alpha_60d"] > 0).mean() * 100
        ret_col = "return_20d" if "20" in label_period else "return_60d"
        alp_col = "alpha_20d" if "20" in label_period else "alpha_60d"
        mae_col = "mae_20d" if "20" in label_period else "mae_60d"
        mfe_col = "mfe_20d" if "20" in label_period else "mfe_60d"
        return {
            "label": label_period,
            "n": n,
            "avg_return": valid[ret_col].mean(),
            "avg_alpha": valid[alp_col].mean(),
            "win_rate": win_rate,
            "avg_mae": valid[mae_col].mean(),
            "avg_mfe": valid[mfe_col].mean(),
        }

    p20 = _perf_card("20D", valid20, n20)
    p60 = _perf_card("60D", valid60, n60)

    def _color_val(v):
        if v is None:
            return "#888"
        return "#2e7d32" if v > 0 else "#c62828"

    def _fmt(v, suffix="%"):
        if v is None:
            return "—"
        return f"{v:+.2f}{suffix}"

    st.html(f"""
<style>
@media (max-width: 640px) {{
  .ev-perf-grid {{ grid-template-columns: 1fr !important; }}
  .ev-perf-inner {{ grid-template-columns: 1fr 1fr !important; }}
}}
</style>
<div class="ev-perf-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:8px 0 4px">

  <!-- 20D Card -->
  <div style="background:#f8f9fa;border-radius:12px;padding:16px 18px;border-left:4px solid #667eea">
    <div style="font-size:0.75rem;font-weight:700;color:#667eea;margin-bottom:10px;letter-spacing:.04em">
      20 個交易日後（約 1 個月）
      <span style="font-size:0.68rem;color:#90a4ae;font-weight:400">· N={n20} 筆{' · ' + _EVIDENCE_PRESENTER.sample_strength(n20).label if n20 > 0 else ''}</span>
    </div>
    <div class="ev-perf-inner" style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px">
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">平均報酬</div>
        <div style="font-size:1.1rem;font-weight:800;color:{_color_val(p20['avg_return'])}">{_fmt(p20['avg_return'])}</div>
      </div>
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">超額報酬（Alpha）</div>
        <div style="font-size:1.1rem;font-weight:800;color:{_color_val(p20['avg_alpha'])}">{_fmt(p20['avg_alpha'])}</div>
      </div>
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">勝率（Alpha &gt; 0）</div>
        <div style="font-size:1.1rem;font-weight:800;color:#1a1a2e">{f"{p20['win_rate']:.1f}%" if p20['win_rate'] is not None else "—"}</div>
      </div>
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">平均最大回撤（MAE）</div>
        <div style="font-size:1.1rem;font-weight:800;color:#c62828">{_fmt(p20['avg_mae'])}</div>
      </div>
    </div>
    {('<div style="font-size:0.72rem;color:#78909c;margin-top:8px;padding-top:8px;border-top:1px solid #e0e0e0">'
      + _EVIDENCE_PRESENTER.sample_strength(n20).label + '：' +
      ('初步數字供參考，尚不具統計意義。' if n20 < 30 else '已有一定樣本，但仍需繼續累積。')
      + '</div>' if n20 > 0 else '')}
  </div>

  <!-- 60D Card -->
  <div style="background:#f8f9fa;border-radius:12px;padding:16px 18px;border-left:4px solid #5c6bc0">
    <div style="font-size:0.75rem;font-weight:700;color:#5c6bc0;margin-bottom:10px;letter-spacing:.04em">
      60 個交易日後（約 3 個月）
      <span style="font-size:0.68rem;color:#90a4ae;font-weight:400">· N={n60} 筆{' · ' + _EVIDENCE_PRESENTER.sample_strength(n60).label if n60 > 0 else ''}</span>
    </div>
    <div class="ev-perf-inner" style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px">
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">平均報酬</div>
        <div style="font-size:1.1rem;font-weight:800;color:{_color_val(p60['avg_return'])}">{_fmt(p60['avg_return'])}</div>
      </div>
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">超額報酬（Alpha）</div>
        <div style="font-size:1.1rem;font-weight:800;color:{_color_val(p60['avg_alpha'])}">{_fmt(p60['avg_alpha'])}</div>
      </div>
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">勝率（Alpha &gt; 0）</div>
        <div style="font-size:1.1rem;font-weight:800;color:#1a1a2e">{f"{p60['win_rate']:.1f}%" if p60['win_rate'] is not None else "—"}</div>
      </div>
      <div style="text-align:center;padding:8px">
        <div style="font-size:0.68rem;color:#888;margin-bottom:3px">平均最大回撤（MAE）</div>
        <div style="font-size:1.1rem;font-weight:800;color:#c62828">{_fmt(p60['avg_mae'])}</div>
      </div>
    </div>
    {('<div style="font-size:0.72rem;color:#78909c;margin-top:8px;padding-top:8px;border-top:1px solid #e0e0e0">'
      + _EVIDENCE_PRESENTER.sample_strength(n60).label + '：' +
      ('初步數字供參考，尚不具統計意義。' if n60 < 30 else '已有一定樣本，但仍需繼續累積。')
      + '</div>' if n60 > 0 else '<div style="font-size:0.72rem;color:#90a4ae;margin-top:8px">尚無完成 60D 觀察的記錄。</div>')}
  </div>
</div>""")

    if n20 > 0:
        _warn_if_small(n20, "20D")


# ── Section C: Baseline vs Overnight-Aware 比較 ───────────────────────────────


def _section_path_comparison(df: pd.DataFrame):
    st.markdown("### C. Baseline vs Overnight-Aware（RED 訊號同群組對比）")

    st.html("""
<div style="background:#f8f9fa;border-left:3px solid #546e7a;padding:10px 14px;
            border-radius:0 8px 8px 0;margin-bottom:12px;font-size:0.82rem;color:#37474f;line-height:1.7">
  <b>什麼是 Baseline vs Overnight-Aware？</b><br>
  同一個訊號，系統同時用兩種方式模擬進場：<br>
  <ul style="margin:4px 0 0 0;padding-left:18px">
    <li><b>Baseline</b>（基準路徑）：訊號產生次日開盤直接進場，不管隔夜有沒有異常風險。</li>
    <li><b>Overnight-Aware</b>（隔夜風險感知路徑）：先觀察隔夜風險（overnight_risk_level），
        若風險等級可接受，才在 3 個交易日窗口內確認進場。</li>
  </ul>
  這一節只比較隔夜風險評為 <b>RED（高風險）</b> 的訊號——
  也就是真正有差異的那群，看看等待確認究竟有沒有改善績效。
</div>""")

    formal = _formal_eligible(df)
    base_m = _matured_20d(
        formal[
            (formal["path_type"] == PATH_BASELINE)
            & (formal["overnight_risk_level"] == "RED")
        ]
    )
    aware_m = _matured_20d(
        formal[
            (formal["path_type"] == PATH_AWARE)
            & (formal["overnight_risk_level"] == "RED")
        ]
    )

    if base_m.empty or aware_m.empty:
        st.info(
            "尚無成熟的 RED overnight 20D 記錄。  \n"
            "需要同時有 Baseline 和 Overnight-Aware 兩條路徑都完成 20D 觀察，才能進行比較。"
        )
        return

    # Inner join on forward_signal_id
    merged = base_m.merge(
        aware_m,
        on="forward_signal_id",
        suffixes=("_base", "_aware"),
    )
    paired = merged[
        (merged["outcome_data_quality_20d_base"] == ODQ_COMPLETE)
        & (merged["outcome_data_quality_20d_aware"] == ODQ_COMPLETE)
    ]

    n = len(paired)
    st.markdown(f"**配對樣本：{_EVIDENCE_PRESENTER.sample_strength(n).formatted}**")

    if n < 3:
        st.info("配對樣本太少（< 3 筆），無法顯示有意義的比較。")
        return

    alpha_base_avg = paired["alpha_20d_base"].mean()
    alpha_aware_avg = paired["alpha_20d_aware"].mean()
    delta_alpha = alpha_aware_avg - alpha_base_avg
    delta_mae = (paired["mae_20d_aware"] - paired["mae_20d_base"]).mean()

    def _color(v):
        return "#2e7d32" if v >= 0 else "#c62828"

    st.html(f"""
<style>
@media (max-width: 640px) {{
  .ev-cmp-grid {{ grid-template-columns: 1fr !important; }}
}}
</style>
<div class="ev-cmp-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:8px 0 4px">
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">
      Baseline 20D Alpha<br><span style="font-weight:400">（直接進場）</span>
    </div>
    <div style="font-size:1.1rem;font-weight:800;color:{_color(alpha_base_avg)}">{alpha_base_avg:+.2f}%</div>
  </div>
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">
      Overnight-Aware 20D Alpha<br><span style="font-weight:400">（等待確認後進場）</span>
    </div>
    <div style="font-size:1.1rem;font-weight:800;color:{_color(alpha_aware_avg)}">{alpha_aware_avg:+.2f}%</div>
    <div style="font-size:0.68rem;color:{_color(delta_alpha)};margin-top:3px">
      vs Baseline {delta_alpha:+.2f}%
    </div>
  </div>
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px;text-align:center">
    <div style="font-size:0.7rem;color:#888;font-weight:600;margin-bottom:4px">
      Δ MAE（Aware − Baseline）<br><span style="font-weight:400">最大回撤差異</span>
    </div>
    <div style="font-size:1.1rem;font-weight:800;color:{_color(-delta_mae)}">{delta_mae:+.2f}%</div>
    <div style="font-size:0.68rem;color:#aaa;margin-top:3px">負值 = Aware 回撤較小（較佳）</div>
  </div>
</div>""")

    st.caption(
        f"這代表什麼？{'Δalpha > 0 表示等待 Overnight 確認後才進場，比直接進場的超額報酬更高。' if delta_alpha > 0 else 'Δalpha ≤ 0，目前數據顯示等待 Overnight 確認未帶來 Alpha 改善。'}"
        "PENDING / EXPIRED 不計入（需已進場且 20D 成熟）。"
    )

    _warn_if_small(n, "RED Paired")

    with st.expander("📊 RED Aware 執行結果分布", expanded=False):
        aware_red = formal[
            (formal["path_type"] == PATH_AWARE)
            & (formal["overnight_risk_level"] == "RED")
            & formal["entry_status"].notna()
        ]
        if not aware_red.empty:
            status_counts = aware_red.groupby("entry_status").size().reset_index(name="筆數")
            status_label = {
                EXEC_EXECUTED: "✅ EXECUTED（已進場）",
                EXEC_EXPIRED_BEFORE_ENTRY: "⏰ EXPIRED_BEFORE_ENTRY（超窗未觸發）",
                EXEC_INVALIDATED_BEFORE_ENTRY: "🚫 INVALIDATED_BEFORE_ENTRY（訊號失效）",
                EXEC_PENDING: "⏳ PENDING（窗口仍在計算中）",
                EXEC_DATA_INSUFFICIENT: "❓ DATA_INSUFFICIENT",
            }
            status_counts["說明"] = status_counts["entry_status"].map(status_label).fillna(
                status_counts["entry_status"]
            )
            st.dataframe(
                status_counts[["說明", "筆數"]], use_container_width=True, hide_index=True
            )

    with st.expander("⚠️ 方法限制（§51）", expanded=False):
        st.info(
            "**⚠️ 方法限制（§51）**：Aware 路徑使用 ENTRY_RECONFIRMED 當日盤中 current_price，"
            "進場日開盤至觸發前的 High/Low 不計入 MAE/MFE，"
            "與 Baseline 的起算點不完全對稱。"
        )


# ── Section D: 樣本健康狀況 ───────────────────────────────────────────────────


def _section_sample_health(df: pd.DataFrame):
    """D. 樣本健康狀況（含 Legacy、PENDING、排除原因）"""

    st.markdown("### D. 樣本健康狀況")

    total = len(df)
    if total == 0:
        st.info("尚無 foe_v1 評估記錄。請先執行 `run_daily.py` 累積資料。")
        return

    baseline_df = df[df["path_type"] == PATH_BASELINE]
    aware_df = df[df["path_type"] == PATH_AWARE]

    # PENDING explanation
    pending_b = int((baseline_df["entry_status"] == EXEC_PENDING).sum())
    pending_a = int((aware_df["entry_status"] == EXEC_PENDING).sum())
    no_overnight_signals = df[df["exclusion_reason"] == EXCL_NO_OVERNIGHT_DATA]["forward_signal_id"].nunique()
    no_overnight = no_overnight_signals  # unique signals (each has 2 path rows)

    st.html(f"""
<style>
@media (max-width: 640px) {{
  .ev-health-grid {{ grid-template-columns: 1fr !important; }}
}}
</style>
<div class="ev-health-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0 12px">
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px">
    <div style="font-size:0.72rem;font-weight:700;color:#546e7a;margin-bottom:8px">⏳ PENDING 是什麼？</div>
    <div style="font-size:0.82rem;color:#37474f;line-height:1.7">
      Baseline PENDING：<b>{pending_b}</b> 筆<br>
      Overnight-Aware PENDING：<b>{pending_a}</b> 筆<br>
      <span style="font-size:0.75rem;color:#78909c">
        PENDING 表示訊號已建立，但尚在 3 個交易日進場窗口內，
        系統還沒決定進場或放棄。不計入任何績效數字。
      </span>
    </div>
  </div>
  <div style="background:#f8f9fa;border-radius:10px;padding:14px 16px">
    <div style="font-size:0.72rem;font-weight:700;color:#546e7a;margin-bottom:8px">📦 Legacy 訊號是什麼？</div>
    <div style="font-size:0.82rem;color:#37474f;line-height:1.7">
      Legacy 訊號數：<b>{no_overnight}</b> 個唯一訊號（標記為 NO_OVERNIGHT_DATA）<br>
      <span style="font-size:0.75rem;color:#78909c">
        overnight_v1 功能上線前產生的舊訊號，當時沒有隔夜風險資料（overnight_risk_level），
        無法與新訊號在同一框架下比較，因此不納入 B / C 節的正式評估。
        統計上存在，但不算作前向驗證的有效樣本。
      </span>
    </div>
  </div>
</div>""")

    with st.expander("📊 Baseline 路徑 — 按 overnight_risk_level 分組", expanded=False):
        st.caption(
            "overnight_risk_level 由 overnight_v1 規則計算：GREEN = 隔夜風險低，"
            "YELLOW = 中等風險，RED = 高風險，UNKNOWN = 無法評估。"
        )
        b_counts = (
            baseline_df.groupby("overnight_risk_level", dropna=False)
            .size()
            .reset_index(name="筆數")
            .sort_values("overnight_risk_level")
        )
        b_counts["overnight_risk_level"] = b_counts["overnight_risk_level"].fillna(
            "(無 Overnight 資料／Legacy)"
        )
        b_counts["樣本評估"] = b_counts["筆數"].apply(
            lambda n: _EVIDENCE_PRESENTER.sample_strength(n).label
        )
        st.dataframe(b_counts, use_container_width=True, hide_index=True)

    with st.expander("🚫 排除記錄（exclusion_reason）", expanded=False):
        excl = df[df["exclusion_reason"].notna()]
        if excl.empty:
            st.caption("目前無排除記錄。")
        else:
            excl_label = {
                "NO_OVERNIGHT_DATA": "NO_OVERNIGHT_DATA — overnight_v1 上線前的 Legacy 訊號",
                "MISSING_VALID_NEXT_OPEN_ENTRY": "MISSING_VALID_NEXT_OPEN_ENTRY — 缺少有效次日開盤進場價",
                "RETROACTIVE_OVERNIGHT_CONTEXT": "RETROACTIVE_OVERNIGHT_CONTEXT — 事後補入的 overnight context",
            }
            excl_counts = excl.groupby("exclusion_reason").size().reset_index(name="筆數")
            excl_counts["說明"] = excl_counts["exclusion_reason"].map(excl_label).fillna(
                excl_counts["exclusion_reason"]
            )
            st.dataframe(
                excl_counts[["說明", "筆數"]], use_container_width=True, hide_index=True
            )


# ── Section E: 進階技術資訊 ──────────────────────────────────────────────────


def _section_advanced(df: pd.DataFrame):
    """E. 進階技術資訊（收合於 expanders）"""

    st.markdown("### E. 進階技術資訊")

    # E1: Overnight risk groupings (existing _section_overnight_evidence logic)
    with st.expander("🔬 Overnight 風險分組績效（Baseline 路徑 × GREEN/YELLOW/RED）", expanded=False):
        st.caption(
            "依 overnight_risk_level 分組，比較 20D return / alpha / MAE / MFE / T1達成率。"
            "所有指標皆為 Baseline Next-Open 路徑（不含 Overnight-Aware 調整）。"
            "僅含 formal overnight cohort（exclusion_reason IS NULL）。"
        )

        formal_baseline = _formal_eligible(df[df["path_type"] == PATH_BASELINE])
        baseline_m = _matured_20d(formal_baseline)

        if baseline_m.empty:
            st.info("尚無成熟的 20D Baseline 記錄。")
        else:
            valid = baseline_m[baseline_m["outcome_data_quality_20d"] == ODQ_COMPLETE]
            if valid.empty:
                st.info("尚無品質完整的 20D 記錄（ODQ_COMPLETE）。")
            else:
                groups = []
                for level in ["GREEN", "YELLOW", "RED", "UNKNOWN"]:
                    sub = valid[valid["overnight_risk_level"] == level]
                    n = len(sub)
                    if n == 0:
                        continue
                    resolved = _resolved_stop_t1(sub, "20d")
                    t1_rate = (
                        (resolved["target_stop_outcome_20d"] == OUTCOME_T1_FIRST).sum()
                        / len(resolved)
                        * 100
                        if len(resolved) > 0
                        else None
                    )
                    ambig = (sub["target_stop_outcome_20d"] == OUTCOME_SAME_DAY_AMBIGUOUS).sum()
                    groups.append({
                        "overnight_risk": level,
                        "N": n,
                        "樣本評估": _EVIDENCE_PRESENTER.sample_strength(n).label,
                        "20D Return (avg %)": round(sub["return_20d"].mean(), 2) if n >= 5 else "—",
                        "20D Alpha (avg %)": round(sub["alpha_20d"].mean(), 2) if n >= 5 else "—",
                        "20D MAE (avg %)": round(sub["mae_20d"].mean(), 2) if n >= 5 else "—",
                        "20D MFE (avg %)": round(sub["mfe_20d"].mean(), 2) if n >= 5 else "—",
                        "T1達成率 (解決案件)": (
                            f"{t1_rate:.1f}%" if t1_rate is not None and n >= 5 else "—"
                        ),
                        "SAME_DAY_AMBIGUOUS": int(ambig),
                    })

                if groups:
                    green_g = next((g for g in groups if g["overnight_risk"] == "GREEN"), None)
                    red_g   = next((g for g in groups if g["overnight_risk"] == "RED"), None)
                    headline = _EVIDENCE_PRESENTER.overnight_group_headline_html(green_g, red_g)
                    if headline:
                        st.html(headline)
                    else:
                        st.caption("各組樣本尚不足 5 筆，暫無 Alpha 摘要。")
                    st.dataframe(pd.DataFrame(groups), use_container_width=True, hide_index=True)

                    has_ambig = any(g["SAME_DAY_AMBIGUOUS"] > 0 for g in groups)
                    small_groups = [g for g in groups if isinstance(g["N"], int) and g["N"] < 30]
                    for g in small_groups:
                        _warn_if_small(g["N"], g["overnight_risk"])
                    if has_ambig:
                        st.caption(
                            "T1達成率 = T1_FIRST / (T1_FIRST + STOP_FIRST)，"
                            "分母不含 SAME_DAY_AMBIGUOUS（§24 預先登記）。"
                        )
                else:
                    st.info("分組後無可顯示資料。")

    # E2: Execution rate (existing _section_execution_rate logic)
    with st.expander("📊 Aware 路徑執行率（PENDING / EXECUTED / EXPIRED 分布）", expanded=False):
        st.caption(
            "Overnight-Aware 路徑統計：有多少比例的訊號在 3 個交易日內實際 ENTRY_RECONFIRMED 進場。"
            f"進場窗口：{FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS} 個交易日（Day1=execution_date, Day2, Day3）。"
        )
        aware_df = df[df["path_type"] == PATH_AWARE].copy()
        if aware_df.empty:
            st.info("尚無 Overnight-Aware 路徑記錄。")
        else:
            n_total = len(aware_df)
            counts = aware_df["entry_status"].value_counts().reset_index()
            counts.columns = ["entry_status", "筆數"]
            counts["比例"] = (counts["筆數"] / n_total * 100).round(1).astype(str) + "%"
            status_label = {
                EXEC_EXECUTED: "✅ EXECUTED — 已進場",
                EXEC_EXPIRED_BEFORE_ENTRY: "⏰ EXPIRED — 超過 3 個交易日窗口，未觸發進場（不代表策略失敗）",
                EXEC_INVALIDATED_BEFORE_ENTRY: "🚫 INVALIDATED — 訊號在窗口內失效",
                EXEC_PENDING: "⏳ PENDING — 仍在窗口內等待",
                EXEC_DATA_INSUFFICIENT: "❓ DATA_INSUFFICIENT — 資料不足",
            }
            counts["說明"] = counts["entry_status"].map(status_label).fillna(counts["entry_status"])
            st.dataframe(
                counts[["說明", "筆數", "比例"]], use_container_width=True, hide_index=True
            )
            st.caption(
                "EXPIRED_BEFORE_ENTRY 不代表策略失敗，代表 overnight 情況在窗口內未轉 GREEN 而未進場。"
                "NOT_EXECUTED 不計入任何績效數字。"
            )

            cross = (
                aware_df.groupby(["overnight_risk_level", "entry_status"], dropna=False)
                .size()
                .unstack(fill_value=0)
                .reset_index()
            )
            if not cross.empty:
                cross["overnight_risk_level"] = cross["overnight_risk_level"].fillna("(無資料)")
                st.caption("執行率 × overnight_risk_level 明細：")
                st.dataframe(cross, use_container_width=True, hide_index=True)

    # E3: Protocol details
    with st.expander("📋 foe_v1 協議說明（Pre-Registered Protocol）", expanded=False):
        vers = _versions()
        st.markdown(f"""
**評估規則版本：** `{vers['outcome_protocol']}` | **Overnight 規則：** `{vers['overnight_rule']}` | **Live 規則：** `{vers['live_rule']}` | **進場窗口：** `{vers['aware_window']}` 個交易日

本頁使用 **預先固定** 的評估規則（`foe_v1`），所有評估定義（進場條件、horizon 長度、
MAE/MFE 計算、樣本納入標準）均於資料累積前登記。

**禁止行為：**
- 看到結果後，修改 entry definition、horizon、MAE/MFE 或 sample inclusion 以得到更漂亮的結果
- 把 UNKNOWN overnight 當 GREEN 處理
- 把 NOT_EXECUTED 當 0% return 計算
- 用 nearest-date 取代 exact-date 的 0050 benchmark
- 用 calendar day 取代 trading day 的 horizon 計算

**變更規則必須升版至 `foe_v2`，並重新從頭累積資料。**

---
**方法限制（§50）**：Aware 路徑 MAE/MFE 掃描從 entry_date 次一交易日開始，
不含 ENTRY_RECONFIRMED 當日開盤至觸發前的 H/L，與 Baseline 不完全對稱。

**方法限制（§51）**：Aware 路徑 0050 benchmark 採觸發日 Next-Open 作為近似值
（`benchmark_timing_approximation=True`），存在輕微時序偏差。
        """)


# ── Main page ─────────────────────────────────────────────────────────────────


def page_evidence():
    # Load data
    df = _load_all_rows()

    if df.empty:
        st.html("""
<div style="margin-bottom:16px">
  <div style="font-size:1.25rem;font-weight:800;color:#1a1a2e;margin-bottom:8px">
    🔒 選股驗證中心（Forward Evidence）
  </div>
  <div style="font-size:0.83rem;color:#37474f;line-height:1.75;background:#f0f4ff;
              border-left:4px solid #667eea;padding:11px 15px;border-radius:0 8px 8px 0">
    追蹤系統推薦的股票，後來表現如何？是否比 0050 更好？目前有沒有足夠證據支持策略？
  </div>
</div>""")
        st.info(
            "⏳ **尚無 foe_v1 評估記錄。**  \n"
            "請執行 `run_daily.py` 開始累積前向執行結果評估資料。  \n"
            "每日執行後，系統會自動為當日的 Forward Signal 建立 Baseline 和 Overnight-Aware 兩條評估路徑。"
        )
        return

    _section_progress_summary(df)

    st.divider()
    _section_performance(df)

    st.divider()
    _section_path_comparison(df)

    st.divider()
    _section_sample_health(df)

    st.divider()
    _section_advanced(df)

    st.divider()
    st.caption(
        f"資料來源：`forward_outcome_evaluations` | "
        f"協議版本：`{FORWARD_OUTCOME_PROTOCOL_VERSION}` | "
        "每 5 分鐘快取。"
    )
