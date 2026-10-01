# HARNESS POLICY — QuantumBot Pro Harness v1
**Version**: 1.0.0  
**Effective Date**: 2026-09-15  
**Status**: ACTIVE  
**Supersedes**: None (first version)

---

## FUNDAMENTAL PRINCIPLE

> **NO EVIDENCE = NOT COMPLETED**

No task, phase, or modification may be declared COMPLETED without verifiable evidence.
Narrative alone — including code that ran without exception — is NOT evidence.

---

## CORE RULES

### RULE 1 — NO SPEC = NO CODE CHANGE

No file in the trading engine, research pipeline, or configuration may be modified
unless a formal SPEC exists in `quantumbot_harness/specs/` with status `APPROVED`.

**Applies to**: `main.py`, `runner.py`, `risk/`, `execution/`, `analytics/`,
`strategies/`, `database/db_manager.py`, `core/`, `backtesting/`, `machine_learning/`,
`config/settings.yaml`, `research/crypto_quant/holdout_vault.py`.

**Exception**: Files within `quantumbot_harness/` itself may be updated as part of
the harness maintenance process, provided no sealed artifacts are modified.

---

### RULE 2 — NO RECEIPT = NO CLOSE

A TASK may not transition to `CLOSED` status unless all `required_receipts` listed in
`TASK_LEDGER.json` are present in `receipts/index.json` with status `VERIFIED`.

A receipt must contain:
- A unique `receipt_id`
- A `sha256` hash of the evidence artifact
- A `created_at` timestamp
- A `producer` identifying what created it
- A `verification_status` of `VERIFIED` (not `PENDING` or `UNKNOWN`)

**UNKNOWN != VERIFIED**  
**PARTIAL != VERIFIED**

---

### RULE 3 — NO PASSING GATE = NO PROMOTION

A SPEC may not transition to `CLOSED` unless its associated GATE has status `PASS`.

A GATE may only be `PASS` when:
1. ALL required receipts are present and SHA-256 verified
2. ALL acceptance criteria are satisfied with documented evidence
3. ALL required tests have been executed and passed
4. NO forbidden files have been modified (verified by hash comparison)
5. The failure_reasons array is empty

**A GATE cannot be PASS by inference, narrative, or assumption.**

---

### RULE 4 — FINAL_HOLDOUT = SEALED UNTIL EXPLICIT AUTHORIZATION

The `FINAL_HOLDOUT` partition is sealed by policy and by code (`FINAL_HOLDOUT_LOCKED=True`).

It may NEVER be accessed for:
- Alpha research or hypothesis testing
- Hyperparameter optimization
- Model selection
- Any exploratory purpose

It may ONLY be accessed when:
- At least one hypothesis has reached `PROMISING_UNDER_DEVELOPMENT` status
- A formal SPEC explicitly authorizes FINAL_HOLDOUT access
- The SPEC has been approved in writing by a human reviewer
- The access is logged in `HoldoutVault.access_log`

**Current status**: `LOCKED / UNTOUCHED (0 accesses, 0 bars read)`

---

### RULE 5 — LIVE = DENY BY DEFAULT

`ALLOW_LIVE_TRADING` is `false` by default and is enforced by `core/entry_policy.py`.

Live trading may ONLY be enabled when:
- The trading system has passed forward testing with a validated hypothesis
- A formal SPEC authorizes live trading with explicit risk parameters
- The SPEC has been approved by a human reviewer
- The Forward Test Guard criteria are ALL satisfied

**Current status**: `BLOCKED`

---

### RULE 6 — SEALED ARTIFACTS = IMMUTABLE

The following artifacts are sealed and must never be modified:

| Artifact | Reason |
|----------|--------|
| `reports/FASE*` | Historical phase closure reports |
| `reports/MULTIPLE_TESTING_LEDGER_V2.json` | Institutional testing ledger |
| `reports/FASE63_HYPOTHESIS_REGISTRY.json` | Canonical hypothesis manifest |
| `reports/FASE63A_METRICS_ACCOUNTING_CLOSURE.md` | Certified closure of FASE 6.3a |
| `docs/ENGINEERING_HARNESS.md` | Canonical architecture and partition definition |
| `data/raw/bybit/` | Canonical dataset with known SHA-256 fingerprint |
| `.env` | Credentials — never read, never modified by agents |
| `database/quantumbot.db` | Production database — never directly modified by agents |

Modification of any sealed artifact is a **CRITICAL VIOLATION** regardless of intent.

### RULE 6.1 ? ARTIFACT TAXONOMY: SEALED_IMMUTABLE vs VERSIONED_APPEND_ONLY

To prevent false corruption alarms while preserving strict cryptographic integrity, project artifacts are classified into two distinct governance classes:

1. **`SEALED_IMMUTABLE`**:
   - Fixed, certified historical observations representing closed phases.
   - Examples: `reports/FASE*` closure reports, `reports/FASE63_HYPOTHESIS_REGISTRY.json`, `reports/FASE63A_METRICS_ACCOUNTING_CLOSURE.md`, canonical raw datasets in `data/raw/bybit/`, credentials in `.env`, production database `database/quantumbot.db`.
   - Invariant: Byte-for-byte permanent immutability. Any modification is treated as an integrity failure.

2. **`VERSIONED_APPEND_ONLY`**:
   - Cumulative institutional ledgers and living engineering documentation that legitimately expand across research generations.
   - Examples: `reports/MULTIPLE_TESTING_LEDGER_V2.json`, `docs/ENGINEERING_HARNESS.md`.
   - Invariant: Historical entries within these files can NEVER mutate or be removed. New generation entries or documentation sections may only be added in an append-only manner through a formal reconciliation process (`RECONCILIATION-*.json`).
   - Prior receipts are marked `SUPERSEDED` and preserved for historical audit; new versioned receipts index the updated state.

---

### RULE 7 — UNKNOWN != PASS

If the outcome of a test or validation step cannot be determined:
- The status is `UNKNOWN`
- `UNKNOWN` is treated as `FAIL` for gate purposes
- Investigation is required before proceeding

---

### RULE 8 — PARTIAL != PASS

A partially satisfied criterion is a failed criterion.
There is no "mostly pass" state.

---

### RULE 9 — THE IMPLEMENTING AGENT CANNOT SELF-VALIDATE

The agent that implements a SPEC cannot be the sole verifier of its own gate.
At minimum:
- All SHA-256 hashes must be computed programmatically (not asserted from memory)
- All test results must be produced by running the actual test suite
- Protected file hashes must be compared against pre-implementation baselines

---

## WORKFLOW

```
SPEC DRAFTED
    │
    ▼ Human approval required
SPEC APPROVED
    │
    ▼
TASK(S) CREATED in TASK_LEDGER.json (status: OPEN)
    │
    ▼
TASK IN_PROGRESS
    │
    ▼
Implementation complete → receipts generated
    │
    ▼
TASK VERIFYING
    │
    ▼
GATE evaluated (all criteria + receipts + tests checked)
    │
    ├─ PASS → TASK CLOSED → SPEC CLOSED
    │
    └─ FAIL/BLOCKED → TASK returns to IN_PROGRESS or BLOCKED
                    → inconsistencies documented and corrected
                    → gate re-evaluated
```

---

## ESCALATION

If a harness constraint blocks necessary work, the correct path is:
1. Document the constraint and the reason it exists
2. Propose a SPEC that explicitly modifies the constraint
3. Obtain human approval for the SPEC
4. Modify the constraint under the approved SPEC
5. Re-verify that the modification does not violate higher-order policies

**There is no "urgent bypass" path.**

---

## VERSION HISTORY

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-09-15 | Initial version — H1 Bootstrap |
