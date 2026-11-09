"""
PART C (P2): Canonical Research Data Contract — Session 44.

Formal definitions for all date, version, sample, performance, and statistical
fields used in Taiwan Stock AI research. This is a schema contract, not a DB migration.

Purpose: prevent label mixing, ensure reproducibility, unify vocabulary across
Sessions 38-44 and all future sessions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FieldType(str, Enum):
    DATE = "DATE"
    DATETIME = "DATETIME"
    STRING = "STRING"
    FLOAT = "FLOAT"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    HASH = "HASH"


class NullableRule(str, Enum):
    NOT_NULL = "NOT_NULL"
    NULLABLE_WHEN_NON_TD = "NULLABLE_WHEN_NON_TD"
    NULLABLE_WHEN_NO_PRICE = "NULLABLE_WHEN_NO_PRICE"
    NULLABLE_WHEN_IMMATURE = "NULLABLE_WHEN_IMMATURE"
    NULLABLE_WHEN_BACKTEST = "NULLABLE_WHEN_BACKTEST"
    NULLABLE = "NULLABLE"


class FieldCategory(str, Enum):
    DATE = "DATE"
    VERSION = "VERSION"
    SAMPLE = "SAMPLE"
    PERFORMANCE = "PERFORMANCE"
    STATISTICAL = "STATISTICAL"


@dataclass(frozen=True)
class FieldDefinition:
    field_name: str
    category: FieldCategory
    data_type: FieldType
    unit: str
    source: str
    definition: str
    nullable_rule: NullableRule
    validation_rule: str
    example_valid: str
    example_invalid: str
    mixing_forbidden_with: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class CanonicalResearchDataContract:
    session: int
    contract_version: str
    fields: tuple[FieldDefinition, ...]
    n_date_fields: int
    n_version_fields: int
    n_sample_fields: int
    n_performance_fields: int
    n_statistical_fields: int
    forbidden_mixings: tuple[tuple[str, str, str], ...]  # (field_a, field_b, reason)
    contract_notes: str


# ---------------------------------------------------------------------------
# Field Definitions
# ---------------------------------------------------------------------------

_DATE_FIELDS = [
    FieldDefinition(
        "signal_date", FieldCategory.DATE, FieldType.DATE, "YYYY-MM-DD",
        "forward_signals.trade_date",
        "Date the cron job assigned as the trading session for signal generation. "
        "UNRELIABLE as an execution date — may be a holiday (v6.0) or non-trading day.",
        NullableRule.NOT_NULL,
        "Must be YYYY-MM-DD format; must be >= 2026-10-01 for v8.0 signals",
        "2026-10-12", "2026-10-09 (holiday, v6.0)",
        ("execution_date", "fill_date"),
        "Same as trade_date in forward_signals. Use only for grouping by signal generation batch.",
    ),
    FieldDefinition(
        "execution_date", FieldCategory.DATE, FieldType.DATE, "YYYY-MM-DD",
        "forward_signals.execution_date",
        "First real trading day on which a stock had an available opening price >= day after signal_date. "
        "Computed by NEXT_OPEN pipeline. NULL for v6.0 non-trading-day signals.",
        NullableRule.NULLABLE_WHEN_NON_TD,
        "If not NULL: must be > signal_date; must exist in daily_prices for that stock",
        "2026-10-13 (for signal_date=2026-10-12)", "2026-10-13 (for signal_date=2026-10-09, should be NULL)",
        ("signal_date",),
        "This is the fill_date for a single stock. Use fill_date for cluster-level analysis.",
    ),
    FieldDefinition(
        "fill_date", FieldCategory.DATE, FieldType.DATE, "YYYY-MM-DD",
        "derived: MIN(execution_date) across stocks in a signal_date cluster",
        "The cluster-level execution date — the first trading day on which the majority of "
        "stocks in a signal_date batch had available opening prices. Used to form fill-date clusters.",
        NullableRule.NULLABLE_WHEN_NON_TD,
        "Must be > signal_date; must be a real trading day (≥50 stocks in daily_prices)",
        "2026-10-13 (cluster for signal_date=2026-10-12)", "2026-10-15 (thin day, only 0050)",
        ("signal_date", "outcome_start_date"),
        "fill_date = execution_date for signals where all stocks execute on same day.",
    ),
    FieldDefinition(
        "decision_date", FieldCategory.DATE, FieldType.DATE, "YYYY-MM-DD",
        "forward_signals.locked_at (date portion)",
        "Date the signal decision was finalized and written to DB. May differ from signal_date "
        "for pre-holiday signal generation (e.g., Oct 09 signal has decision_date=Oct 08).",
        NullableRule.NOT_NULL,
        "Must be <= signal_date + 1 day",
        "2026-10-08 (for signal_date=2026-10-09)", "2026-10-15 (for signal_date=2026-10-12, too far)",
        (),
        "Use locked_at to understand when analysis was actually run.",
    ),
    FieldDefinition(
        "outcome_start_date", FieldCategory.DATE, FieldType.DATE, "YYYY-MM-DD",
        "derived: execution_date (same as fill_date for single-stock outcomes)",
        "The date from which the holding period begins. Must be a real trading day. "
        "Used as the base for computing the Nth trading day exit.",
        NullableRule.NULLABLE_WHEN_NON_TD,
        "Must equal or follow execution_date; must be a real trading day",
        "2026-10-13", "2026-10-15 (thin day)",
        ("signal_date", "fill_date"),
        "5D outcome: outcome_start=fill_date; 20D outcome: same.",
    ),
    FieldDefinition(
        "outcome_end_date", FieldCategory.DATE, FieldType.DATE, "YYYY-MM-DD",
        "derived: Nth trading day after outcome_start_date in stock-specific daily_prices",
        "The exit date — the Nth stock-specific trading day after outcome_start_date. "
        "5D: 5th day. 20D: 20th day. Must have price data in daily_prices.",
        NullableRule.NULLABLE_WHEN_IMMATURE,
        "Must be > outcome_start_date; must exist in daily_prices for that stock",
        "2026-10-28 (5th TD after fill Oct 13 for TSMC)", "2026-11-01 (not in daily_prices)",
        ("outcome_start_date",),
        "If NULL: outcome is IMMATURE; do not use in comparison.",
    ),
]

_VERSION_FIELDS = [
    FieldDefinition(
        "strategy_version", FieldCategory.VERSION, FieldType.STRING, "string",
        "forward_signals, research config",
        "Human-readable strategy identifier: 'V1', 'V2', 'V3', 'A_direct', 'B_v1v2', 'C_hybrid'.",
        NullableRule.NOT_NULL,
        "Must be one of the registered strategy identifiers in strategy_version_registry",
        "V3", "v3 (lowercase — not canonical)",
        ("dataset_namespace",),
        "Strategy A/B/C labels (comparison groups) are DIFFERENT from strategy V1/V2/V3 (implementations).",
    ),
    FieldDefinition(
        "model_version", FieldCategory.VERSION, FieldType.STRING, "string",
        "forward_signals.model_version",
        "Model version used to generate the signal: 'v6.0' or 'v8.0'. "
        "v6.0 signals have calendar bugs (holiday/weekend generation). "
        "v8.0 is the production version from Oct 12 2026 onwards.",
        NullableRule.NOT_NULL,
        "Must be 'v6.0' or 'v8.0'",
        "v8.0", "v7.0 (non-existent)",
        (),
        "All v6.0 signals must be excluded from v8.0 production comparison.",
    ),
    FieldDefinition(
        "parameter_hash", FieldCategory.VERSION, FieldType.HASH, "hex string",
        "research.v3_backtest_engine.PARAMETER_HASH",
        "16-char hex hash of the V3 strategy parameters. Frozen at be43e8ca977d9fdd. "
        "Any change to V3 parameters would produce a different hash.",
        NullableRule.NOT_NULL,
        "Must equal 'be43e8ca977d9fdd' for frozen V3",
        "be43e8ca977d9fdd", "be43e8ca977d9fde (1 char different → V3 params changed!)",
        (),
        "FROZEN. Never change without explicit session authorization.",
    ),
    FieldDefinition(
        "comparison_opportunity_id", FieldCategory.VERSION, FieldType.STRING, "string",
        "derived: f'{fill_date}_{strategy_a}_{strategy_b}'",
        "Unique identifier for a paired comparison opportunity. Two strategies can only be compared "
        "on the same set of signals, same fill_date, same benchmark window.",
        NullableRule.NOT_NULL,
        "Must reference a valid fill_date and strategy pair",
        "2026-10-13_V3_A_direct", "2026-10-09_V3_A_direct (Oct 09 is excluded)",
        (),
        "Prevents comparing V3 Oct 2026 signals vs A_direct on a different date.",
    ),
]

_SAMPLE_FIELDS = [
    FieldDefinition(
        "stock_id", FieldCategory.SAMPLE, FieldType.STRING, "Taiwan stock code",
        "forward_signals.stock_id",
        "Stock identifier (Taiwan market code). '00'-prefix stocks are ETF-like.",
        NullableRule.NOT_NULL,
        "Must exist in stocks table; must not start with '00' for common-stock-only analysis",
        "2330 (TSMC)", "0050 (ETF — excluded from common-stock analysis)",
        (),
        "ETF contamination: ~1.8% of signals in Oct 2026 pool start with '00'.",
    ),
    FieldDefinition(
        "source_provenance", FieldCategory.SAMPLE, FieldType.ENUM, "PROSPECTIVE|RETROSPECTIVE|UNKNOWN",
        "forward_signals generation context",
        "Whether the signal was generated prospectively (before outcome known) or "
        "retrospectively (reconstructed from historical data). "
        "Only PROSPECTIVE signals are valid for unbiased strategy comparison.",
        NullableRule.NOT_NULL,
        "Must be PROSPECTIVE for all forward_signals in production DB",
        "PROSPECTIVE", "RETROSPECTIVE (not allowed in comparison pool)",
        (),
        "All forward_signals in platform.db are PROSPECTIVE (cron-generated).",
    ),
]

_PERFORMANCE_FIELDS = [
    FieldDefinition(
        "gross_return", FieldCategory.PERFORMANCE, FieldType.FLOAT, "decimal (0.05 = 5%)",
        "derived: (exit_price - fill_price) / fill_price",
        "Raw price return over the holding period. No fees, no benchmark adjustment.",
        NullableRule.NULLABLE_WHEN_IMMATURE,
        "If not NULL: must be in range [-1.0, +5.0]",
        "0.0276", "-1.5 (unrealistic; likely data error)",
        ("net_return", "alpha_vs_0050"),
        "Never compare gross_return to net_return or alpha.",
    ),
    FieldDefinition(
        "net_return", FieldCategory.PERFORMANCE, FieldType.FLOAT, "decimal (0.05 = 5%)",
        "derived: gross_return - FEES_PCT",
        "Return after transaction costs (FEES_PCT = 0.00585 = 0.585%). "
        "Used in all canonical comparisons.",
        NullableRule.NULLABLE_WHEN_IMMATURE,
        "net_return = gross_return - 0.00585",
        "0.0218", "0.0276 (gross_return; fees not subtracted)",
        ("gross_return", "alpha_vs_0050"),
        "FEES_PCT=0.00585 is a research assumption; not verified against live broker.",
    ),
    FieldDefinition(
        "benchmark_return", FieldCategory.PERFORMANCE, FieldType.FLOAT, "decimal",
        "derived: (0050_exit - 0050_fill) / 0050_fill - FEES_PCT",
        "0050 net return over the same fill/exit dates as the signals. "
        "Corrected in S42 (CR-B04: S40 used wrong dates).",
        NullableRule.NULLABLE_WHEN_NO_PRICE,
        "Must be computed from same date range as signal comparison",
        "-0.0216", "-0.0465 (S40 error — wrong benchmark dates)",
        ("alpha_vs_0050",),
        "S42 correction: S40 benchmark was -4.65%; corrected to -2.16%.",
    ),
    FieldDefinition(
        "alpha_vs_0050", FieldCategory.PERFORMANCE, FieldType.FLOAT, "percentage points",
        "derived: net_return - benchmark_return",
        "Excess return of the strategy vs 0050 benchmark. "
        "DIFFERENT from paired_delta_vs_baseline.",
        NullableRule.NULLABLE_WHEN_IMMATURE,
        "alpha = net_return - benchmark_return",
        "+2.3 pp", "paired_delta (different concept — do not mix)",
        ("paired_delta_vs_baseline",),
        "S41 correction: DIRECT_ENTRY alpha sign flipped: +2.86 → -0.56 pp (CR-B02).",
    ),
    FieldDefinition(
        "paired_delta_vs_baseline", FieldCategory.PERFORMANCE, FieldType.FLOAT, "percentage points",
        "derived: mean(V3 net_return) - mean(baseline net_return) for same fill_date cluster",
        "Paired comparison delta. Same stocks, same execution window, same benchmark. "
        "The canonical metric for V3 vs A_direct comparison.",
        NullableRule.NULLABLE_WHEN_IMMATURE,
        "Computed as cluster-level mean delta, not signal-level",
        "+0.81 pp (S43 strict, 3 clusters)", "signal-level delta (not cluster-level)",
        ("alpha_vs_0050",),
        "S43 strict: +0.81 pp (CI: [-1.4, +3.0] pp). NOT SIGNIFICANT.",
    ),
]

_STATISTICAL_FIELDS = [
    FieldDefinition(
        "cluster_count", FieldCategory.STATISTICAL, FieldType.INTEGER, "integer",
        "derived: count of unique fill_dates with complete outcome windows",
        "Number of independent fill-date clusters used in statistical inference. "
        "Should NOT be confused with signal count or unique stock count.",
        NullableRule.NOT_NULL,
        "Must be >= 1; for t-test inference: >= 10 recommended",
        "3 (S43 strict)", "128 (signal count — not cluster count)",
        ("raw_n",),
        "G03: cluster_count=3 is insufficient for reliable t-test (need ≥10).",
    ),
    FieldDefinition(
        "effective_n_status", FieldCategory.STATISTICAL, FieldType.ENUM,
        "SUFFICIENT|MARGINAL|INSUFFICIENT",
        "derived: based on cluster_count vs thresholds",
        "Classification of statistical effective sample size.",
        NullableRule.NOT_NULL,
        "SUFFICIENT: ≥10 clusters; MARGINAL: 5-9; INSUFFICIENT: <5",
        "INSUFFICIENT (3 clusters)", "SUFFICIENT (3 clusters — wrong classification)",
        (),
        "Current S43 state: INSUFFICIENT.",
    ),
    FieldDefinition(
        "statistical_verdict", FieldCategory.STATISTICAL, FieldType.ENUM,
        "SIGNIFICANT_POSITIVE|SIGNIFICANCE_INCONCLUSIVE|SIGNIFICANT_NEGATIVE|INSUFFICIENT_DATA",
        "derived: based on CI and p-value from cluster-level t-test",
        "Statistical verdict for a comparison. CI must exclude zero for SIGNIFICANT.",
        NullableRule.NOT_NULL,
        "Must match CI and p-value; SIGNIFICANT requires p < 0.05",
        "SIGNIFICANCE_INCONCLUSIVE (S43: p=0.37)", "SIGNIFICANT_POSITIVE (S40: retracted)",
        (),
        "S40 SIGNIFICANT_POSITIVE was retracted in S41. Current: SIGNIFICANCE_INCONCLUSIVE.",
    ),
]


def build_canonical_data_contract() -> CanonicalResearchDataContract:
    all_fields = tuple(
        _DATE_FIELDS + _VERSION_FIELDS + _SAMPLE_FIELDS + _PERFORMANCE_FIELDS + _STATISTICAL_FIELDS
    )
    return CanonicalResearchDataContract(
        session=44,
        contract_version="v1.0-s44",
        fields=all_fields,
        n_date_fields=len(_DATE_FIELDS),
        n_version_fields=len(_VERSION_FIELDS),
        n_sample_fields=len(_SAMPLE_FIELDS),
        n_performance_fields=len(_PERFORMANCE_FIELDS),
        n_statistical_fields=len(_STATISTICAL_FIELDS),
        forbidden_mixings=(
            ("signal_date", "execution_date", "They refer to different events; signal_date is not an execution date"),
            ("fill_date", "signal_date", "fill_date is AFTER signal_date; using signal_date as fill_date inflates returns"),
            ("alpha_vs_0050", "paired_delta_vs_baseline", "Alpha = raw vs benchmark; Delta = paired vs strategy; different denominators"),
            ("gross_return", "net_return", "Fees must always be subtracted before comparison"),
            ("cluster_count", "raw_n", "Statistical inference uses cluster means, not signal counts"),
            ("RETROSPECTIVE", "PROSPECTIVE", "Retrospective signals are NOT valid for unbiased comparison"),
            ("dataset_namespace", "strategy_namespace", "Dataset A/B/C is NOT the same as Strategy V1/V2/V3"),
        ),
        contract_notes=(
            "v1.0-s44: 20 fields defined. "
            "Key corrections encoded: S41 alpha sign flip (CR-B02), S42 benchmark date correction (CR-B04), "
            "S43 v6.0 exclusion. "
            "Any future session violating these definitions must document the deviation explicitly."
        ),
    )
