"""
dashboard/_pages/evidence.py — foe_v1 前向執行結果證據儀表板

本頁所有評估規則皆於資料累積前預先固定（Pre-Registered Protocol foe_v1）。
禁止因目前結果好看或不好看而修改評估定義。修改需升版至 foe_v2。
"""

import logging

import pandas as pd
import streamlit as st

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


# ── Sample-size labels (pre-registered in PRD §46) ────────────────────────────
def _n_label(n: int) -> str:
    if n < 10:
        return "不足"
    if n < 30:
        return "初步觀察"
    if n < 100:
        return "有一定參考"
    return "可評估穩定性"


def _fmt_n(n: int) -> str:
    return f"N={n}（{_n_label(n)}）"


def _warn_if_small(n: int, label: str = ""):
    if n < 10:
        st.warning(
            f"{'[' + label + '] ' if label else ''}樣本不足（N={n}），僅供觀察，不具統計意義。"
        )
    elif n < 30:
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
    Section A (Sample Health) still shows all rows including excluded ones.

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


# ── Section A: Sample Health ──────────────────────────────────────────────────


def _section_sample_health(df: pd.DataFrame):
    st.subheader("A｜樣本健康狀況")

    total = len(df)
    if total == 0:
        st.info("尚無 foe_v1 評估記錄。請先執行 `run_daily.py` 累積資料。")
        return

    # Split by path
    baseline_df = df[df["path_type"] == PATH_BASELINE]
    aware_df = df[df["path_type"] == PATH_AWARE]

    col1, col2, col3 = st.columns(3)
    col1.metric("Baseline 路徑 (總)", len(baseline_df))
    col2.metric("Overnight-Aware 路徑 (總)", len(aware_df))
    col3.metric("已成熟 20D 記錄", int(df["horizon_20d_matured_at"].notna().sum()))

    # Baseline breakdown
    st.markdown("**Baseline 路徑 — 按 overnight_risk_level**")
    b_counts = (
        baseline_df.groupby("overnight_risk_level", dropna=False)
        .size()
        .reset_index(name="筆數")
        .sort_values("overnight_risk_level")
    )
    b_counts["overnight_risk_level"] = b_counts["overnight_risk_level"].fillna(
        "(無 Overnight 資料)"
    )
    b_counts["樣本評估"] = b_counts["筆數"].apply(_n_label)
    st.dataframe(b_counts, use_container_width=True, hide_index=True)

    # Exclusions
    excl = df[df["exclusion_reason"].notna()]
    if not excl.empty:
        st.markdown("**排除記錄 (exclusion_reason)**")
        excl_counts = excl.groupby("exclusion_reason").size().reset_index(name="筆數")
        st.dataframe(excl_counts, use_container_width=True, hide_index=True)

    # Pending / incomplete
    pending_b = int((baseline_df["entry_status"] == EXEC_PENDING).sum())
    pending_a = int((aware_df["entry_status"] == EXEC_PENDING).sum())
    if pending_b or pending_a:
        st.caption(f"尚在等待進場 (PENDING)：Baseline={pending_b}，Aware={pending_a}")

    no_overnight = int((df["exclusion_reason"] == EXCL_NO_OVERNIGHT_DATA).sum())
    if no_overnight:
        st.caption(
            f"overnight_v1 上線前的 Legacy 訊號：{no_overnight} 筆，"
            "已標記 NO_OVERNIGHT_DATA，不納入 overnight 分析。"
        )


# ── Section B: Overnight Risk Evidence ────────────────────────────────────────


def _section_overnight_evidence(df: pd.DataFrame):
    st.subheader("B｜Overnight 風險分組證據（Baseline 路徑）")
    st.caption(
        "依 overnight_risk_level（GREEN / YELLOW / RED / UNKNOWN）分組，"
        "比較 20D return / alpha / MAE / MFE / T1達成率。"
        "所有指標皆為 Baseline Next-Open 路徑（不含 Overnight-Aware 調整）。"
    )

    # P1: formal overnight cohort — exclusion_reason IS NULL only
    formal_baseline = _formal_eligible(df[df["path_type"] == PATH_BASELINE])
    baseline_m = _matured_20d(formal_baseline)

    if baseline_m.empty:
        st.info("尚無成熟的 20D Baseline 記錄（Formal Overnight Cohort）。")
        return

    valid = baseline_m[baseline_m["outcome_data_quality_20d"] == ODQ_COMPLETE]

    if valid.empty:
        st.info("尚無品質完整的 20D 記錄（ODQ_COMPLETE）。")
        return

    # Only formal overnight risk levels — no legacy "(無資料)" group
    groups = []
    for level in ["GREEN", "YELLOW", "RED", "UNKNOWN"]:
        sub = valid[valid["overnight_risk_level"] == level]
        label = level

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

        groups.append(
            {
                "overnight_risk": label,
                "N": n,
                "樣本評估": _n_label(n),
                "20D Return (avg %)": (
                    round(sub["return_20d"].mean(), 2) if n >= 5 else "—"
                ),
                "20D Alpha (avg %)": (
                    round(sub["alpha_20d"].mean(), 2) if n >= 5 else "—"
                ),
                "20D MAE (avg %)": round(sub["mae_20d"].mean(), 2) if n >= 5 else "—",
                "20D MFE (avg %)": round(sub["mfe_20d"].mean(), 2) if n >= 5 else "—",
                "T1達成率 (解決案件)": (
                    f"{t1_rate:.1f}%" if t1_rate is not None and n >= 5 else "—"
                ),
                "SAME_DAY_AMBIGUOUS": int(ambig),
            }
        )

    if not groups:
        st.info("分組後無可顯示資料。")
        return

    result_df = pd.DataFrame(groups)
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    for g in groups:
        if isinstance(g["N"], int):
            _warn_if_small(g["N"], g["overnight_risk"])

    if any(g["SAME_DAY_AMBIGUOUS"] > 0 for g in groups):
        st.caption(
            "T1達成率 = T1_FIRST / (T1_FIRST + STOP_FIRST)，分母不含 SAME_DAY_AMBIGUOUS（§24 預先登記）。"
        )


# ── Section C: Baseline vs Overnight-Aware ────────────────────────────────────


def _section_path_comparison(df: pd.DataFrame):
    st.subheader("C｜Baseline vs Overnight-Aware（RED 同群組對比）")
    st.caption(
        "僅限 overnight_risk_level = RED 的訊號，同一 forward_signal_id "
        "同時有 Baseline 與 Aware 兩條路徑記錄時才納入比較。"
    )
    st.info(
        "**⚠️ 方法限制（§51）**：Aware 路徑使用 ENTRY_RECONFIRMED 當日盤中 current_price，"
        "進場日開盤至觸發前的 High/Low 不計入 MAE/MFE，"
        "與 Baseline 的起算點不完全對稱。"
    )

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
        st.info("尚無成熟的 RED overnight 20D 記錄（Baseline 或 Aware 路徑）。")
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
    _warn_if_small(n, "RED Paired")
    st.markdown(f"**配對樣本：{_fmt_n(n)}**")

    if n < 3:
        st.info("配對樣本太少，無法顯示有意義的比較。")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Baseline 20D Alpha (avg)",
        f"{paired['alpha_20d_base'].mean():.2f}%",
    )
    col2.metric(
        "Aware 20D Alpha (avg)",
        f"{paired['alpha_20d_aware'].mean():.2f}%",
        delta=f"{(paired['alpha_20d_aware'] - paired['alpha_20d_base']).mean():.2f}% vs Baseline",
    )
    col3.metric(
        "Δ MAE (Aware - Baseline, avg)",
        f"{(paired['mae_20d_aware'] - paired['mae_20d_base']).mean():.2f}%",
    )

    st.caption(
        "Δalpha > 0 表示等待 Overnight-Aware 確認後才進場，alpha 優於直接 Next-Open 進場。"
        "PENDING / EXPIRED 不計入（需已進場且 20D 成熟）。"
    )

    # Execution outcome breakdown for aware
    if "entry_status" in aware_m.columns:
        st.markdown("**RED 訊號 Aware 路徑執行結果分布**")
        aware_red = formal[
            (formal["path_type"] == PATH_AWARE)
            & (formal["overnight_risk_level"] == "RED")
            & formal["entry_status"].notna()
        ]
        if not aware_red.empty:
            status_counts = (
                aware_red.groupby("entry_status").size().reset_index(name="筆數")
            )
            st.dataframe(status_counts, use_container_width=True, hide_index=True)


# ── Section D: Execution Rate ─────────────────────────────────────────────────


def _section_execution_rate(df: pd.DataFrame):
    st.subheader("D｜Aware 路徑執行率（Not Executed 分析）")
    st.caption(
        "Aware 路徑統計：有多少比例訊號在 3 個交易日內實際 ENTRY_RECONFIRMED。"
        "NOT_EXECUTED 不視為 0% 報酬。"
    )

    aware_df = df[df["path_type"] == PATH_AWARE].copy()
    if aware_df.empty:
        st.info("尚無 Overnight-Aware 路徑記錄。")
        return

    n_total = len(aware_df)
    counts = aware_df["entry_status"].value_counts().reset_index()
    counts.columns = ["entry_status", "筆數"]
    counts["比例"] = (counts["筆數"] / n_total * 100).round(1).astype(str) + "%"

    status_label = {
        EXEC_EXECUTED: "✅ EXECUTED（進場）",
        EXEC_EXPIRED_BEFORE_ENTRY: "⏰ EXPIRED_BEFORE_ENTRY（超窗未觸發）",
        EXEC_INVALIDATED_BEFORE_ENTRY: "🚫 INVALIDATED_BEFORE_ENTRY（訊號失效）",
        EXEC_PENDING: "⏳ PENDING（仍在窗口內）",
        EXEC_DATA_INSUFFICIENT: "❓ DATA_INSUFFICIENT",
    }
    counts["說明"] = (
        counts["entry_status"].map(status_label).fillna(counts["entry_status"])
    )

    st.dataframe(
        counts[["說明", "筆數", "比例"]], use_container_width=True, hide_index=True
    )
    st.caption(
        f"進場窗口：{FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS} 個交易日（Day1=execution_date, Day2, Day3）。"
        "EXPIRED_BEFORE_ENTRY 不代表策略失敗，代表 overnight 情況未轉 GREEN 而未進場。"
    )

    # Breakdown by overnight_risk_level
    st.markdown("**Aware 執行率 × overnight_risk_level**")
    cross = (
        aware_df.groupby(["overnight_risk_level", "entry_status"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    if not cross.empty:
        cross["overnight_risk_level"] = cross["overnight_risk_level"].fillna("(無資料)")
        st.dataframe(cross, use_container_width=True, hide_index=True)


# ── Main page ─────────────────────────────────────────────────────────────────


def page_evidence():
    st.title("🔒 前向執行結果證據")

    # Protocol header
    vers = _versions()
    st.markdown(
        f"**評估規則版本：** `{vers['outcome_protocol']}` | "
        f"**Overnight 規則：** `{vers['overnight_rule']}` | "
        f"**Live 規則：** `{vers['live_rule']}` | "
        f"進場窗口：`{vers['aware_window']}` 個交易日"
    )

    # Pre-registration disclaimer
    with st.expander("📋 協議聲明（預先登記 Pre-Registered Protocol）", expanded=False):
        st.markdown("""
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

    # Load data
    df = _load_all_rows()

    if df.empty:
        st.info(
            "資料庫尚無 ForwardOutcomeEvaluation 記錄。請執行 `run_daily.py` 累積 foe_v1 資料。"
        )
        return

    st.divider()
    _section_sample_health(df)

    st.divider()
    _section_overnight_evidence(df)

    st.divider()
    _section_path_comparison(df)

    st.divider()
    _section_execution_rate(df)

    st.divider()
    st.caption(
        f"資料來源：`forward_outcome_evaluations` | "
        f"協議版本：`{FORWARD_OUTCOME_PROTOCOL_VERSION}` | "
        "每 5 分鐘快取。"
    )
