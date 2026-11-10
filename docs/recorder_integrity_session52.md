# Recorder Integrity — Session 52

**Analysis date**: 2026-11-10  
**Session**: S52  
**Module**: `src/research/provenance_audit_s52.py` → `run_recorder_integrity_tests()`  
**Verdict**: RECORDER_INTEGRITY_VERIFIED

---

## RIT-01 through RIT-15 Results

| Test ID | Description | Result |
|---------|-------------|--------|
| RIT-01 | First registration returns True | PASS |
| RIT-02 | Duplicate registration returns False | PASS |
| RIT-03 | 3× repeated: first True, rest False | PASS |
| RIT-04 | Payload mutation detected | PASS |
| RIT-05 | Timestamp (locked_at) tampering detected | PASS |
| RIT-06 | Code hash mismatch detected | PASS |
| RIT-07 | Parameter hash mismatch detected | PASS |
| RIT-08 | Input snapshot field differs (observable) | PASS |
| RIT-09 | None signal_id: behavior documented | PASS |
| RIT-10 | Transaction rollback: 0 rows committed | PASS |
| RIT-11 | Post-registration UPDATE detected by verify() | PASS |
| RIT-12 | Restart persistence: data survives close/reopen | PASS |
| RIT-13 | Evidence read-back returns correct fields | PASS |
| RIT-14 | Fingerprint reproduction is deterministic | PASS |
| RIT-15 | Production write blocked (platform.db) | PASS |

**All 15 tests passed.**

---

## D1 Contract Compliance

`ExtendedDecisionPayload` (S52) adds the following fields beyond `ImmutableDecisionPayload`:

| Field | Description | In fingerprint? |
|-------|-------------|-----------------|
| code_commit_hash | Git commit SHA at decision time | ✓ |
| parameter_hash | V3 parameter hash | ✓ |
| input_cutoff | as_of_date for input data | ✓ |
| input_snapshot_fingerprint | SHA-256[:16] of input data | ✗ (separately stored) |

The `input_snapshot_fingerprint` is stored as a field but not included in the decision fingerprint — it must be verified separately against the original input data.

---

## D4 Security Limitations

1. **LOCAL_SQLITE_NOT_EXTERNALLY_IMMUTABLE**: Any process with file access can overwrite the SQLite file. `INSERT OR IGNORE` + fingerprint is a convention, not a hardware-enforced guarantee.

2. **HASH_NOT_TRUSTED_TIMESTAMP**: The fingerprint covers `registered_at` and `locked_at`. An adversary who controls the system clock can set any timestamp before computing the fingerprint. The fingerprint proves consistency, not wall-clock time.

3. **GIT_COMMIT_NOT_EXECUTION_PROOF**: `code_commit_hash` does not prove that exact version was running when the decision was made — only that it was recorded. No independent attestation.

4. **MOCK_RECORDER_NOT_PROSPECTIVE**: Records created in isolated test environments (temp SQLite) are research artifacts, not genuine prospective evidence.

5. **NO_STRONG_NON_REPUDIATION**: Without RFC 3161 TSA or independent custody chain, strong non-repudiation is not achievable.

---

## TC27 Regression

`register()` uses `cursor.rowcount == 1` (fixed in S51). Three consecutive registrations of the same payload return: `True, False, False`. Confirmed by RIT-02 and RIT-03.
