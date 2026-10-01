# M0 required-receipt correction and formalization preparation

Date: 2026-10-01. Technical correction: SCOPED_PASS after independent re-audit.
Formal M0: BLOCKED. Formalization specification: DRAFT. Certification effect: NONE.

## Implemented correction

The independent auditor reproduced an acceptance defect in the successor's
inherited gate evaluation: a required PENDING receipt with otherwise unchanged
data could produce VERIFIED_PASS. This revision fixes that successor path,
without editing the historical harness.py, canonical indexes, or old receipt
statuses.

The isolated gate wrapper now checks every required receipt before any gate
source hashing. Each identifier must have exactly one indexed receipt and its
verification_status must be exactly VERIFIED. Missing, duplicate, PENDING,
PENDING_MANIFEST, UNKNOWN, INVALID, SUPERSEDED, incorrectly cased, null,
type-invalid, and missing-status values block. Non-required historical receipts
are not globally reclassified or removed.

Evaluation uses the same deep-copied gate/index snapshots that passed preflight,
so a second metadata read cannot silently replace the checked receipt status.
The verified historical function body is retained with a snapshot-bound reader;
the shared imported harness module and historical source bytes stay unchanged.
This does not implement a filesystem-wide atomic lock or certify future M0.

## Verification

Before the fix, two focused PENDING/PENDING_MANIFEST gate regressions failed,
showing the inherited evaluator reached hashing. After the fix, the affected
suites, including draft-structure checks, passed **151 tests in 21.85s**.

The auditor /root/m0_independent_audit independently reproduced **151 passed
in 30.38s**. Its exact prior PENDING probe now returns 1/VERIFIED_FAIL with
NOT_VERIFIED and zero hash calls. Missing, duplicate, unsupported-status, and
duplicate-required-ID probes also block. The real VERIFIED positive control
still passes; the checked index is read once for gate evaluation.

Safe validate and safe verify-all FASE611 returned 0. The latter reconstructed
the existing FASE 6.11 gate as VERIFIED_PASS with zero drift. A fictitious
mixed-case holdout fingerprint returned the expected denial code 2.

```powershell
python -B -m pytest -q -p no:cacheprovider tests/test_harness_m0_safety_cli.py quantumbot_harness/tests/test_v2_invariants.py tests/test_v2_invariants.py tests/test_harness_v2_compatibility.py tests/test_current_harness_reconciliation.py tests/test_m0_formalization_draft.py
python -B scripts/run_harness_v2_safe.py validate
python -B scripts/run_harness_v2_safe.py verify-all GATE-FASE611-PASSIVE-EXECUTION-001
```

Current source hashes, versioned changes from the preceding revision, command
results, independent review outcome, and preserved snapshot hashes are recorded
in M0_RECEIPT_STATUS_CORRECTION_EVIDENCE.json. Prior evidence remains unchanged
as the record of earlier source revisions; it is not rewritten to match today.

## Prepared M0, not an approved M0

M0_FORMALIZATION_PLAN.md and SPEC-HARNESS-M0-FORMALIZATION-001.json prepare a
separate versioned engineering registry/verifier proposal, five evidence
receipts, explicit human approval, independent gate reconstruction, and an
invariant-by-invariant acceptance decision. The specification validates against
the existing schema with format checks and remains DRAFT. Its approval, closure,
and gate fields are null. No M0 registry, verifier, task, receipt, or gate is
created by preparing this proposal; the original V2 design remains unchanged.

Unmeasured historical bar/byte reads stay UNKNOWN. Prospective measurement
cannot establish retrospective global zero reads. Formal M0 remains blocked
unless evidence supports the immutable claim at its required scope; this plan
does not weaken the invariant or invent zeros. The remaining direct legacy
surface also needs an explicit external disposition. M1 is not authorized.

## Preservation and DEMO

Historical records remain useful for provenance, drift detection, and forensic
review. None were deleted. The 57 original baseline/reference/evidence files
and four preceding report/evidence snapshots were verified unchanged. Only the
two successor implementation/test sources changed deliberately; new preparation
and evidence artifacts are additive.

The existing DEMO/PAPER runner was observed healthy, RUNNING, PID 17892,
failure_count 0. No restart, order request, setting change, or kill-switch
change was performed. LIVE stays blocked. No actual holdout contents,
credentials, or trading database contents were opened for this work.
