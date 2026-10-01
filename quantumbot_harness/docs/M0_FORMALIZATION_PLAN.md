# M0 preparation — approval draft, not a closure

Date: 2026-10-01. Status: SPEC APPROVED / FORMAL M0 BLOCKED / READY FOR INDEPENDENT REVIEW.
The receipt-status correction is implemented separately as harness maintenance.
This plan does not approve the draft, create a PASS gate, or advance M1.

## What is preserved and why

Historical gates, candidates, receipt indexes, ledgers, reports, the original V2
design, and prior evidence are useful for provenance, forensic reproduction,
and detecting drift. Preserve them unchanged. No deletion is proposed. The
prior source hashes describe earlier revisions; new evidence must link their
before/after hashes rather than overwrite those observations.

The original baseline remains GEN-6.11-PASSIVE-EXECUTION-001, research phase
6.11, formal hypotheses 20, LIVE blocked, and the recorded holdout access count
0. No real holdout data, credentials, or trading database contents are needed.

## Technical correction now in scope

The successor rejects every required receipt not exactly VERIFIED before gate
hashing. This includes PENDING, PENDING_MANIFEST, UNKNOWN, INVALID, SUPERSEDED,
missing/null/type-invalid status, missing receipts, and ambiguous duplicate
receipt identifiers. The legacy source and its receipts stay unchanged.

Gate evaluation uses the same checked gate/index snapshots, not a second index
read that could replace the approved state. This is a metadata snapshot, not a
filesystem-wide atomic lock or assurance that all source files remain frozen.
Source hashes and the existing candidate checks still verify their own inputs.

New regression tests reproduce the independent auditor's defect in memory,
exercise both gate and verify-all, check the CLI path, and retain a real VERIFIED
positive control. Canonical receipts are never downgraded or edited for tests.

## Proposed sequence after explicit approval

1. The user approved SPEC-HARNESS-M0-FORMALIZATION-001 in chat. The parent V2
   design remains untouched and the formal M0 gate remains blocked.
2. A separate versioned engineering M0 registry and deterministic verifier now
   exist under quantumbot_harness/milestones/M0 and core/. They are additive,
   read-only for governance, and cannot certify M0 or authorize M1. Avoid
   appending or rewriting canonical historical registries.
3. Resolve the evidence blockers before registering a PASS: individually assess
   all 14 inherited invariants and the remaining legacy entry-point surface.
   The human reviewer must assess whether mandatory successor use and the
   stated residual exposure satisfy M0 without pretending to implement all M2.
4. Obtain independently verified control, invariant, preservation,
   and audit receipts. Build the engineering gate only after the registry and
   verifier have been approved and tested. Every required receipt must be
   uniquely indexed, VERIFIED, and tied to actual evidence by SHA-256.
5. Have an auditor distinct from the implementer reconstruct the M0 gate.
   Leave it BLOCKED on any unknown/partial invariant or unresolved blocker.
   Even a genuine M0 PASS does not authorize M1, LIVE, or further research.

## The counters must not be invented

PROJECT_STATE has no historical bar/byte read measurements. Recording zeros
today would not establish what happened in the past. Prospective instrumentation
can measure an explicitly defined boundary from a recorded start time, but it
cannot retroactively certify global zero reads or weaken immutable invariants.

Before formal closure, require an externally reviewed evidence basis for the
full zero-read claim actually required by the original invariant. If that basis
cannot be established, M0 remains BLOCKED. This draft does not reinterpret
UNKNOWN as PASS or promise that adding instrumentation alone resolves history.

## Receipts planned, not yet registered

- RECEIPT-M0-AUTHORIZATION-001: approval of exact formalization scope.
- RECEIPT-M0-CONTROLS-001: current source hashes, negative tests, positive control.
- RECEIPT-M0-INVARIANTS-001: all 14 invariants and the counter/surface decisions.
- RECEIPT-M0-PRESERVATION-001: byte/hash preservation and registry isolation.
- RECEIPT-M0-INDEPENDENT-AUDIT-001: review by a different auditor.

These identifiers are proposed dependencies, not fabricated VERIFIED receipts.
No canonical task ledger entry, receipt index entry, or M0 PASS gate is created
by this plan or registry.

## Stop boundary

Deliver the status correction, its reproducible evidence, this plan, and the
DRAFT specification for review. Do not approve the draft on the user's behalf,
rewrite historical approval flags, fill unknown counters with zeros, or start
M1. Leave the existing DEMO session untouched and LIVE blocked.
