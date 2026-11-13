# Session 72AB — Empty State Design

**Session**: 72AB  
**Verdict**: `VERIFIED`  
**Implementation**: `dashboard/components.py:empty_state()` (isolated copy only)

---

## 6 Standard Empty State Types

| Kind | Message | Trigger Condition | Page(s) |
|---|---|---|---|
| `no_signal` | 目前沒有符合條件的買進訊號。 | Recommendation list is empty for selected date | 今日決策→今日推薦 |
| `insufficient_sample` | 目前有效樣本數不足，暫時無法提供可靠的績效結論。 | ForwardSignal count < threshold, or outcomes not mature | 策略績效→績效總覽、前向驗證 |
| `stale_data` | 目前最新資料日期為 {detail}，資料可能尚未更新。 | MAX(daily_prices.date) < today - threshold | 任何顯示日期的頁面 |
| `source_unavailable` | 目前無法取得資料來源，請稍後再試。 | DB connection error, Neon timeout, OperationalError | 任何 get_session() 失敗時 |
| `feature_inactive` | 此功能目前尚未啟用，暫不影響正式交易建議。 | V2 Shadow / V3 / LiveCollector not activated | 進場研究、盤中監控 |
| `research_only` | 此結果僅供研究，不屬於正式交易訊號。 | Any page showing V2/V3/Shadow content | 進場時機研究 |

---

## Implementation

```python
# dashboard/components.py (isolated only)
def empty_state(kind: str, detail: str = "") -> None:
    messages = {
        "no_signal": "目前沒有符合條件的買進訊號。",
        "insufficient_sample": "目前有效樣本數不足，暫時無法提供可靠的績效結論。",
        "stale_data": f"目前最新資料日期為 {detail}，資料可能尚未更新。",
        "source_unavailable": "目前無法取得資料來源，請稍後再試。",
        "feature_inactive": "此功能目前尚未啟用，暫不影響正式交易建議。",
        "research_only": "此結果僅供研究，不屬於正式交易訊號。",
    }
    st.info(messages.get(kind, "暫無資料。"))
```

---

## Decision Tree: Which Empty State to Show

```
Is DB connection failing?
  └─ YES → source_unavailable

Is this a research/shadow page?
  └─ YES → research_only (always prepend this label)

Is feature not yet activated (no auto-write pipeline)?
  └─ YES → feature_inactive

Is data older than expected freshness window?
  └─ YES → stale_data (pass date string as detail)

Is result set empty after filters?
  └─ YES → no_signal (for trading signal pages)
           insufficient_sample (for performance/stats pages)
```

---

## Existing Pages Already Using Partial Empty States

| Page | Current Behavior | 72AB Improvement |
|---|---|---|
| entry_timing_research | Shows `__connection_error__` sentinel → custom st.error | research_only banner added above page |
| overview | Shows "今日無推薦" in page logic | Consistent with no_signal |
| evidence | Shows "樣本不足" message | Consistent with insufficient_sample |
| live_monitor | Shows "盤中監控資料尚未啟用" | Consistent with feature_inactive |

**No existing page logic was modified** — the new `empty_state()` is available for use but the existing pages continue to render their own messages via the unchanged page functions.
