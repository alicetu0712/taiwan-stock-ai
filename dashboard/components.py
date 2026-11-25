"""
dashboard/components.py — Shared display-only UI components for data freshness labeling.

DESIGN CONSTRAINTS:
- Pure display: no DB queries, no HTTP requests, no session state mutations.
- date.today() is used ONLY to compute staleness gap — never to represent data currency.
- All functions are Unknown-safe: None inputs → "未確認" text, never raises.
- Do not import production modules at module level (lazy imports only where needed).
- Callers supply all data values; this module never fetches them independently.
"""

from __future__ import annotations

from datetime import date as _date

import streamlit as st

_CSS_INJECTED = False


def _inject_css() -> None:
    global _CSS_INJECTED
    if _CSS_INJECTED:
        return
    st.markdown(
        """<style>
.fr-anchor {
    display: inline-flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
    font-size: 0.72rem;
    color: #78909c;
    padding: 3px 10px;
    background: rgba(0,0,0,0.03);
    border-radius: 4px;
    margin: 2px 0 6px;
}
.fr-stale { color: #ff7043; font-weight: 600; }
.fr-current { color: #66bb6a; }
.fr-unknown { color: #9e9e9e; font-style: italic; }
.fr-warning-banner {
    background: rgba(255,112,67,0.08);
    border-left: 3px solid #ff7043;
    border-radius: 0 6px 6px 0;
    padding: 7px 12px;
    font-size: 0.8rem;
    color: #bf360c;
    margin: 4px 0 10px;
}
.fr-eod-badge {
    font-size: 0.65rem;
    color: #9e9e9e;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.research-banner {
    background: #fef2f2;
    border: 2px solid #dc2626;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 12px;
}
.research-banner-compact {
    background: #fff3e0;
    border-left: 3px solid #ff9800;
    border-radius: 0 4px 4px 0;
    padding: 5px 12px;
    margin-bottom: 8px;
    font-size: 0.8rem;
    color: #e65100;
}
.tsg-blocked {
    background: #fef2f2;
    border: 2px solid #dc2626;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 12px;
    font-size: 0.82rem;
    color: #7f1d1d;
}
.tsg-degraded {
    background: #fff3e0;
    border-left: 4px solid #f59e0b;
    border-radius: 0 6px 6px 0;
    padding: 8px 12px;
    margin-bottom: 10px;
    font-size: 0.82rem;
    color: #78350f;
}
.tsg-unknown {
    background: #f1f5f9;
    border-left: 4px solid #94a3b8;
    border-radius: 0 6px 6px 0;
    padding: 8px 12px;
    margin-bottom: 10px;
    font-size: 0.82rem;
    color: #475569;
}
</style>""",
        unsafe_allow_html=True,
    )
    _CSS_INJECTED = True


def _staleness_days(as_of) -> int:
    """
    Calendar-day gap between as_of and today.
    Returns -1 if as_of is None or cannot be parsed.
    NOTE: Returns calendar days, not trading days. Used for display only.
    """
    if as_of is None:
        return -1
    try:
        if isinstance(as_of, str):
            as_of = _date.fromisoformat(as_of[:10])
        elif hasattr(as_of, "date"):
            as_of = as_of.date()
        today = _date.today()
        if as_of >= today:
            return 0
        return (today - as_of).days
    except Exception:
        return -1


def data_freshness_banner(
    as_of_date,
    staleness_days: int = -1,
    source_label: str = "資料",
    *,
    compact: bool = False,
) -> None:
    """
    Render an inline data freshness indicator.

    Args:
        as_of_date: Latest date for which data is available. Pass None → "未確認".
        staleness_days: Pre-computed calendar-day lag. Pass -1 to auto-compute.
        source_label: Label prefix, e.g. "AI 訊號", "K 線", "股價".
        compact: If True, render as inline span without border/padding.
    """
    _inject_css()
    if staleness_days == -1:
        staleness_days = _staleness_days(as_of_date)

    if as_of_date is None or staleness_days == -1:
        html = (
            f'<span class="fr-anchor">'
            f'<span class="fr-unknown">{source_label}日期：未確認</span>'
            f"</span>"
        )
        st.markdown(html, unsafe_allow_html=True)
        return

    d_str = str(as_of_date)[:10]

    if staleness_days == 0:
        inner = f'<span class="fr-current">✓ {source_label}截至：{d_str}</span>'
        wrapper_class = "fr-anchor"
    elif staleness_days == 1:
        inner = (
            f'<span class="fr-stale">'
            f"⚠ {source_label}截至：{d_str}（前一交易日）"
            f"</span>"
        )
        wrapper_class = "fr-anchor"
    else:
        inner = (
            f'<span class="fr-stale">'
            f"⚠ {source_label}截至：{d_str}（落後 {staleness_days} 天）"
            f"</span>"
        )
        wrapper_class = "fr-warning-banner" if not compact else "fr-anchor"

    if wrapper_class == "fr-warning-banner":
        st.markdown(
            f'<div class="{wrapper_class}">{inner}'
            f' <span style="color:#9e9e9e;font-size:0.7rem">· 每日 16:00 後更新</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<span class="{wrapper_class}">{inner}</span>',
            unsafe_allow_html=True,
        )


def eod_disclaimer_badge() -> None:
    """
    Render a small 'EOD data — not real-time' badge.
    Use on pages showing historical price charts (T2 看盤, T7 個股).
    """
    _inject_css()
    st.markdown(
        '<span class="fr-eod-badge fr-anchor">'
        "📊 EOD 收盤資料 · 非即時 · 每日 16:00 後更新"
        "</span>",
        unsafe_allow_html=True,
    )


def research_only_banner(
    protocol_version: str = "",
    cutoff_date=None,
    *,
    compact: bool = False,
) -> None:
    """
    Render a prominent 'research only' banner.

    Args:
        protocol_version: e.g. MODEL_VERSION = "v8.0".
        cutoff_date: IS/OOS split date (RESEARCH_CUTOFF_DATE or its string form).
        compact: If True, render as narrow strip (for per-tab use).

    Usage:
        research_only_banner(protocol_version="v8.0", cutoff_date="2026-10-09")
    """
    _inject_css()
    version_str = f"模型版本：{protocol_version}" if protocol_version else ""
    cutoff_str = f"研究截止：{cutoff_date}" if cutoff_date else ""
    meta = "　".join(filter(None, [version_str, cutoff_str]))

    if compact:
        meta_html = (
            f' <span style="color:#9e9e9e;font-size:0.7rem">· {meta}</span>'
            if meta
            else ""
        )
        st.markdown(
            f'<div class="research-banner-compact">'
            f"🔬 <b>研究用途</b>｜非正式交易推薦{meta_html}"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        meta_html = (
            f' <span style="color:#9e9e9e;font-size:0.76rem">{meta}</span>'
            if meta
            else ""
        )
        st.markdown(
            f'<div class="research-banner">'
            f'<span style="color:#dc2626;font-weight:700;font-size:0.85rem">'
            f"🔬 研究用途｜非正式交易推薦</span>{meta_html}<br>"
            f'<span style="color:#7f1d1d;font-size:0.78rem">'
            f"此頁面為策略研究記錄，不代表當前 AI 交易建議，不構成買賣指令。"
            f"歷史回測結果不代表實際交易績效。Shadow 模式尚未啟用於正式決策。"
            f"</span></div>",
            unsafe_allow_html=True,
        )


def chart_freshness_header(
    chart_max_date,
    analysis_date=None,
) -> None:
    """
    Render freshness header for K-line charts.

    IMPORTANT:
        chart_max_date MUST come from the actual chart data
        (e.g. price_df["date"].max()), NOT from date.today() or a global DB query.
        This function computes staleness as the gap between chart_max_date and today.

    Args:
        chart_max_date: Latest date in the chart's price DataFrame.
                        May be a date, str, or None.
        analysis_date: Date of the most recent AnalysisResult for this stock.
                       May be a date, str, or None.
    """
    _inject_css()

    if chart_max_date is None:
        st.markdown(
            '<div class="fr-anchor">'
            '<span class="fr-unknown">K 線資料時間未確認</span>'
            ' <span class="fr-eod-badge">· EOD · 非即時</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        return

    d_str = str(chart_max_date)[:10]
    lag = _staleness_days(chart_max_date)

    if lag == 0:
        price_part = (
            f'<span class="fr-current">K 線資料截至：<b>{d_str}</b> 收盤</span>'
        )
        stale_msg = ""
    elif lag == 1:
        price_part = f'<span class="fr-stale">K 線資料截至：<b>{d_str}</b> 收盤</span>'
        stale_msg = ' · <span class="fr-stale">落後 1 天</span>'
    elif lag > 1:
        price_part = f'<span class="fr-stale">K 線資料截至：<b>{d_str}</b> 收盤</span>'
        stale_msg = f' · <span class="fr-stale">⚠ 落後 {lag} 天</span>'
    else:
        price_part = (
            f'<span class="fr-unknown">K 線資料截至：{d_str}（日期格式未確認）</span>'
        )
        stale_msg = ""

    analysis_part = ""
    if analysis_date is not None:
        a_str = str(analysis_date)[:10]
        analysis_part = f' · <span style="color:#78909c">技術分析：{a_str}</span>'

    st.markdown(
        f'<div class="fr-anchor">'
        f"{price_part}"
        f"{analysis_part}"
        f"{stale_msg}"
        f' · <span class="fr-eod-badge">EOD · 非即時</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def staleness_trading_days(as_of, reference_date=None) -> int:
    """
    Trading-day gap between as_of and reference_date (default: today).
    Returns -1 if as_of is None or cannot be parsed.
    Uses TaiwanTradingCalendar; falls back to calendar days on import error.
    """
    if as_of is None:
        return -1
    try:
        if isinstance(as_of, str):
            as_of = _date.fromisoformat(as_of[:10])
        elif hasattr(as_of, "date"):
            as_of = as_of.date()
        ref = reference_date or _date.today()
        if as_of >= ref:
            return 0
        try:
            from datetime import timedelta

            from src.core.trading_calendar import TaiwanTradingCalendar

            cal = TaiwanTradingCalendar()
            count = 0
            d = as_of + timedelta(days=1)
            while d <= ref:
                if cal.is_trading_day(d):
                    count += 1
                d += timedelta(days=1)
            return count
        except Exception:
            return (ref - as_of).days
    except Exception:
        return -1


def render_trading_safety_banner(gate_result=None) -> None:
    """
    Render the Trading Safety Gate status banner.

    Call at the top of any page that shows trading recommendations.
    If gate_result is None, compute_trading_gate() is called inline.

    Display rules:
      PASS    — no banner (gate passed; display is unimpeded)
      DEGRADED — compact amber strip (research-only reminder)
      BLOCKED  — prominent red box (trading recommendations suppressed)
      UNKNOWN  — compact grey strip (cannot verify status)
    """
    _inject_css()
    if gate_result is None:
        try:
            from dashboard.trading_safety import compute_trading_gate

            gate_result = compute_trading_gate()
        except Exception:
            st.markdown(
                '<div class="tsg-unknown">交易安全閘門：無法載入狀態（模組錯誤）</div>',
                unsafe_allow_html=True,
            )
            return

    from dashboard.trading_safety import TradingGateStatus

    status = gate_result.status
    label = gate_result.status_label_zh
    reasons = gate_result.reason_text_zh

    f = gate_result.freshness
    freshness_line = ""
    if f is not None:
        parts = []
        if f.latest_price_date:
            parts.append(
                f"股價截至 {f.latest_price_date}（落後 {f.price_lag_trading_days} 交易日）"
            )
        if f.latest_signal_date:
            parts.append(
                f"訊號截至 {f.latest_signal_date}（落後 {f.signal_lag_trading_days} 交易日）"
            )
        if parts:
            freshness_line = "；".join(parts)

    if status == TradingGateStatus.PASS:
        return  # no banner needed

    if status == TradingGateStatus.BLOCKED:
        body = f"<b>交易安全閘門：{label}</b>"
        if freshness_line:
            body += f"<br><span style='font-size:0.76rem'>{freshness_line}</span>"
        if reasons:
            body += (
                f"<br><span style='font-size:0.74rem;color:#991b1b'>{reasons}</span>"
            )
        body += "<br><span style='font-size:0.72rem;color:#b91c1c'>以下訊號為歷史研究記錄，不代表當前可執行交易建議。</span>"
        st.markdown(f'<div class="tsg-blocked">{body}</div>', unsafe_allow_html=True)

    elif status == TradingGateStatus.DEGRADED:
        body = f"⚠ 交易安全閘門：{label}"
        if freshness_line:
            body += f" · {freshness_line}"
        st.markdown(f'<div class="tsg-degraded">{body}</div>', unsafe_allow_html=True)

    else:  # UNKNOWN
        body = f"交易安全閘門：{label}"
        if reasons:
            body += f" · {reasons}"
        st.markdown(f'<div class="tsg-unknown">{body}</div>', unsafe_allow_html=True)
