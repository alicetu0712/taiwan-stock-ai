# Security Classification Audit — Session 38

**Date:** 2026-11-08  
**Session:** 38 — Security Classification & Research Universe Validation  
**Mode:** Research-only / Official-source verification / Production frozen  
**Version:** session38_v1

---

## 1. Classification Framework

### Design Principle (Session 38 Requirement)

> "不得只依靠股票代號長度或前綴，直接認定證券類型。必須以可靠的證券主檔與官方分類為優先依據。"
>
> Classification MUST use official TWSE/TPEx OpenAPI data as primary source.
> Code-length heuristics are only applied as fallback with explicit uncertainty labels.

### SecurityType Hierarchy

| Type | Source | Confidence | Description |
|---|---|---|---|
| `TWSE_COMMON_ACTIVE` | Official TWSE API | HIGH | In TWSE 上市公司基本資料, in platform master |
| `TPEX_COMMON_ACTIVE` | Official TPEx API | HIGH | In TPEx 上櫃公司基本資料, in platform master |
| `ETF_OFFICIAL` | Official API + name | HIGH | 0-prefix, NOT in common lists, name-verified ETF |
| `ETF_PROBABLE` | Heuristic fallback | MEDIUM | 0-prefix 5/6-digit, NOT in common lists |
| `TWSE_COMMON_DELISTED_PROBABLE` | Heuristic fallback | MEDIUM | 4-digit, NOT in current TWSE/TPEx active lists |
| `ORPHAN_TWSE_COMMON` | Official TWSE API | HIGH | In TWSE list, NOT in platform master |
| `ORPHAN_TPEX_COMMON` | Official TPEx API | HIGH | In TPEx list, NOT in platform master |
| `UNKNOWN` | None | LOW | No applicable classification |

---

## 2. Official Data Sources

| Source | URL | Count | Date |
|---|---|---|---|
| TWSE common stocks (上市公司) | `openapi.twse.com.tw/v1/opendata/t187ap03_L` | 1,099 | 2026-11-08 |
| TPEx common stocks (上櫃公司) | `tpex.org.tw/openapi/v1/mopsfin_t187ap03_O` | 897 | 2026-11-08 |
| **Total official common** | — | **1,996** | — |

---

## 3. Platform Stocks Master Classification (826 entries)

| Classification | Count | % | Note |
|---|---|---|---|
| `TWSE_COMMON_ACTIVE` | 715 | 86.6% | In current TWSE common list |
| `TPEX_COMMON_ACTIVE` | 1 | 0.1% | Stock 6423 (億而得-創); in both TWSE master and TPEx API |
| `ETF_OFFICIAL` | 11 | 1.3% | 0-prefix, name-verified: 0050, 0051, 0052, 0053, 0055, 0056, 0057, 0060, 0061, 0080, 0081 |
| `TWSE_COMMON_DELISTED_PROBABLE` | 99 | 12.0% | 4-digit, NOT in current TWSE API → probable delistings |
| **Total** | **826** | **100%** | — |

### Key Finding: 99 Probable Delistings in Master

Of the 99 probable delisted stocks:
- **96 have zero daily_prices records** — delisted before Jul 2024 backtest start
- **3 have price data through mid-2026** (2867, 6806, 6288) — delisted DURING backtest era
- **0 appear in ForwardSignals v8.0** — no contamination of current signals

The 11 ETFs in master are NOT classified as errors — they serve as benchmark instruments. However, they should be excluded from common-stock strategy signal generation.

---

## 4. TWSE Completeness Gap

| Metric | Value |
|---|---|
| TWSE common stocks (official) | 1,099 |
| TWSE common in master | 715 |
| **Missing from master** | **384** (35.0%) |
| Listed after Jul 2024 (new IPOs) | 70 |
| Listed before Jul 2024 (pre-existing gap) | 314 |
| Present as orphans in daily_prices | 377 of 384 |

**314 pre-existing TWSE stocks are absent from master.** These stocks existed during the backtest era but were never loaded. This is a selection bias in the training universe — the model learned from 65% of the TWSE market.

---

## 5. Orphan Stock Classification in daily_prices

The daily_prices table contains 15,046 distinct stock_ids. 14,319 are orphans (not in stocks master).

| Classification | Count | Detail |
|---|---|---|
| `ORPHAN_TWSE_COMMON` | 377 | TWSE common stocks present in prices, absent from master |
| `ORPHAN_TPEX_COMMON` | 895 | TPEx common stocks present in prices, absent from master |
| ETF/Leveraged ETF (unknown) | ~13,047 | 0-prefix 5/6-digit codes; ETFs and leveraged products |
| Total orphans | 14,319 | — |

---

## 6. Session 37 → Session 38 Reclassification

Session 37 used length-based heuristics and estimated:
- "787 orphan 4-digit" in FS v8.0 → described as "unknown type (TPEx?)"
- "192 ETF-like 5/6-digit" = 8.6% contamination

Session 38 official-source verification corrects this:
- The 787 orphan 4-digit signals → **verified TWSE common stocks** (in TWSE API, not in master)
- ETF contamination is now **officially verified at 9.52%** (213 signals, 42 stock_ids)
- The delta (9.52% vs 8.6%) = 21 extra signals from 4-digit ETFs (0050, 0052, 0056)
  which the length-based heuristic missed because they are 4-digit codes

| Metric | Session 37 (heuristic) | Session 38 (official) |
|---|---|---|
| ETF contamination | 8.6% (192/2236) | **9.52% (213/2236)** |
| ETF stock_ids | ~24 (length-based) | **42 (official-verified)** |
| "Unknown 4-digit" orphans | "likely TPEx" | Verified TWSE common (all in TWSE API) |
| TPEx in FS v8.0 | Unknown | 0 (zero) |

---

## 7. Verdict

| Check | Verdict |
|---|---|
| Official classification coverage (410/410 FS stocks) | COMPLETE |
| ETF contamination officially quantified | 9.52% — MODERATE |
| TPEx in ForwardSignals | 0% — ABSENT |
| Master stock completeness | 65% TWSE only — PARTIAL |
| Session 37 heuristics corrected | YES — official numbers supersede estimates |
| `SecurityClassificationService` implemented | DONE (src/research/security_classification.py) |

**CLASSIFICATION_VERDICT: `OFFICIAL_VERIFIED`** — All 410 FS v8.0 unique stock_ids classified by official source; 9.52% ETF contamination confirmed.
