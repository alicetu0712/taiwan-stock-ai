# Historical Baseline Recovery — Session 55

**Verdict**: HISTORICAL_BASELINE_UNRECOVERABLE

## S55 Provenance Search (New Evidence)

6 sources searched systematically:

| Source | Type | Finding |
|--------|------|---------|
| `git log --all -S "2c8b2475"` | git_log | **NO COMMITS FOUND** — all S44 docs are untracked |
| `docs/research_reproducibility_session44.md` | doc_file | Claims dp_max="2026-11-05" → 2c8b2475. **CONTRADICTION confirmed** |
| `docs/session44_final_verdict.md Q8` | doc_file | Claims short-key payload + dp_max=Nov05 → 2c8b2475. No v8_buy (0–2999) matches |
| `docs/expanded_5d_comparison_session47.md` | doc_file | Claims change occurred after Nov04/05 backfill. Pre-backfill dates also don't match |
| `src/research/reproducibility_manifest_s44.py` (commit 19c685c) | module_code | Adversarial commit; current code produces f48aa7f3ea673d7c |
| S55 exhaustive search | brute_force | 3 payloads × 15+ dp_max × v8_buy 0–2999 × 7 strict_fds = NO MATCH |

## Critical New Finding (S55)

**Git archaeology** revealed that ALL Session 44–54 documentation files are **UNTRACKED** (git status shows `??`). They were created dynamically by Claude Code sessions and never committed to git. This means:
- No git diff is available to recover the original payload state
- `git log -S "2c8b2475"` returns empty — the string was always generated dynamically
- The "source" listed in prior session docs cannot be verified against git history

**Self-contradicting S44 doc**: `docs/research_reproducibility_session44.md` claims dp_max="2026-11-05" produces `2c8b2475c8fdc457`, but actual computation with dp_max="2026-11-05" produces:
- Short keys: `f48aa7f3ea673d7c`
- Canonical keys: `09c04e8c4059d87e`

Neither is `2c8b2475c8fdc457`.

## Difference Classification

| Cause | Evidence |
|-------|---------|
| `HISTORICAL_PAYLOAD_MISSING` | Docs are untracked; original payload not recoverable from git |
| `UNEXPLAINED_DIFFERENCE` | No parameter combination produces 2c8b2475c8fdc457 |
| `SERIALIZATION_DIFFERENCE` | 3 modules use different JSON key names (confirmed S54) |

## Why Metrics Are Still Valid

The metrics (+0.81pp, n=3, Oct13/14/16, SIGNIFICANCE_INCONCLUSIVE) are confirmed by:
- Multiple independent untracked docs (S44, S45, S47)
- Current DB query (confirmed by S44–S55 each session)
- Canonical Baseline V2 (new, independently verifiable)

The fingerprint discrepancy is a documentation integrity issue, not a data integrity issue.

## Limitation

UNRECOVERABLE is based on exhaustive search of all known provenance sources. If a future source (e.g., a session artifact, a different git branch, an external backup) is found that contains the original payload, this verdict could be revised. All search evidence is documented in `src/research/canonical_baseline_v2_s55.py`.
