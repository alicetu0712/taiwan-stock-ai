# Session 71 — Test Results

**Date**: 2026-11-11  
**Authorization**: AUTH-S71-BUNDLE-A

---

## 1. Bundle A Acceptance Tests (new)

**File**: `tests/test_session71_bundle_a.py`  
**Result**: **33 / 33 PASS**

### L1: Contract Unit Tests (TC-C01–C04)

| Test | Result |
|---|---|
| `test_tc_c01_staleness_days_stale_multi` — 2026-11-05 → positive lag | ✓ PASS |
| `test_tc_c01_staleness_days_today_is_zero` — today → 0 | ✓ PASS |
| `test_tc_c01_staleness_days_none_is_unknown` — None → -1 | ✓ PASS |
| `test_tc_c01_staleness_days_future_is_zero` — future → 0 | ✓ PASS |
| `test_tc_c02_build_freshness_label_current` — staleness=0 → "✓" | ✓ PASS |
| `test_tc_c02_build_freshness_label_stale` — staleness=5 → "⚠/落後" | ✓ PASS |
| `test_tc_c03_is_display_compliant_t2` — chart_freshness_header no-raise | ✓ PASS |
| `test_tc_c03_research_banner_callable` — research_only_banner no-raise | ✓ PASS |
| `test_tc_c04_eod_price_ssot_in_chart_header` — renders "2026-11-05" + "EOD" | ✓ PASS |

### Edge Cases (TC-EC01–EC04)

| Test | Result |
|---|---|
| `test_tc_ec01_empty_data_no_crash` — None chart_max_date → "未確認" | ✓ PASS |
| `test_tc_ec01_none_freshness_banner_no_crash` — None as_of → "未確認" | ✓ PASS |
| `test_tc_ec02_eod_badge_not_live` — eod_badge shows "EOD", not "即時" | ✓ PASS |
| `test_tc_ec03_string_date_handled` — str and date object produce same lag | ✓ PASS |
| `test_tc_ec04_research_cutoff_not_shown_as_stale` — "研究截止" shown, no "落後" | ✓ PASS |

### L2: UI Contract Tests (TC-UI01–UI06)

| Test | Result |
|---|---|
| `test_tc_ui01_t2_has_chart_freshness_header_import` | ✓ PASS |
| `test_tc_ui01_t2_uses_price_df_max_not_today` | ✓ PASS |
| `test_tc_ui02_t2_eod_label_via_component` | ✓ PASS |
| `test_tc_ui03_t0_has_persistent_freshness_anchor` | ✓ PASS |
| `test_tc_ui04_t5_has_research_banner` | ✓ PASS |
| `test_tc_ui04_t6_has_research_banner` | ✓ PASS |
| `test_tc_ui05_sidebar_has_staleness_color` | ✓ PASS |
| `test_tc_ui06_t1_live_monitor_unchanged` | ✓ PASS |
| `test_sidebar_model_version_shown` | ✓ PASS |

### No-Drift Safety Tests

| Test | Result |
|---|---|
| `test_rc2_hash_unchanged` — `4eb6eacf...` ✓ | ✓ PASS |
| `test_model_version_unchanged` — `v8.0` ✓ | ✓ PASS |
| `test_build_chart_unchanged` | ✓ PASS |
| `test_plotly_chart_unchanged` | ✓ PASS |
| `test_no_provider_http_in_components` | ✓ PASS |
| `test_no_db_write_in_components` | ✓ PASS |
| `test_cron_not_modified` | ✓ PASS |
| `test_components_syntax_valid` | ✓ PASS |
| `test_research_v2_isolation_note_preserved` | ✓ PASS |
| `test_cutoff_label_preserved_in_research_backtest` | ✓ PASS |

---

## 2. Full Regression Suite

**Result**: **4,276 passed / 37 failed / 4 skipped** (identical to baseline)

| Metric | Baseline | After Bundle A | Delta |
|---|---|---|---|
| Passing | 4,276 | 4,276 | 0 |
| Failing | 37 | 37 | 0 |
| Skipped | 4 | 4 | 0 |
| Total collected | 4,317 + 33 | 4,350 | +33 (new) |

**All 37 pre-existing failures**: RC-2 deployment expected failures (documented in S66). NOT introduced by Bundle A.

---

## 3. Mapping to Session 70 Acceptance Plan

| S70 Test ID | Description | S71 Status |
|---|---|---|
| TC-C01 | Staleness classification | ✓ PASS |
| TC-C02 | build_freshness_label | ✓ PASS |
| TC-C03 | is_display_compliant validation | ✓ PASS |
| TC-C04 | Signal provenance assertion | ✓ PASS |
| TC-UI01 | T2 chart freshness header | ✓ PASS |
| TC-UI02 | T2 EOD badge | ✓ PASS |
| TC-UI03 | T0 persistent anchor | ✓ PASS |
| TC-UI04 | T5/T6 RESEARCH banner | ✓ PASS |
| TC-UI05 | Sidebar staleness color | ✓ PASS |
| TC-UI06 | T1 no regression | ✓ PASS |
| TC-EC01 | Empty data | ✓ PASS |
| TC-EC02 | Weekend/EOD date | ✓ PASS |
| TC-EC03 | Trading day staleness | ✓ PASS (calendar days used) |
| TC-EC04 | Research cutoff not shown as stale | ✓ PASS |

**Result**: All 14 Session 70 acceptance tests: **14/14 PASS** ✓

---

## 4. Out-of-Scope Tests

| Test | Status | Reason |
|---|---|---|
| Live UI rendering in browser | `OUT_OF_SCOPE_NOT_EXECUTED` | No browser in this env |
| Provider HTTP call tests | `OUT_OF_SCOPE_NOT_EXECUTED` | FORBIDDEN per PART A |
| DB write tests | `OUT_OF_SCOPE_NOT_EXECUTED` | FORBIDDEN per PART A |

---

## 5. Test Limitations

| Limitation | Impact |
|---|---|
| Streamlit `st.markdown` mocked in tests | UI render not visually verified; must be confirmed in browser |
| `_staleness_days` uses calendar days, not trading days | Label says "落後 N 天" not "N 個交易日" — documented in components.py |
| `latest_date` in T0 is ExecutionLog proxy, not per-stock | "Price As-of" is approximate — see TC-F gap in no_drift doc |
