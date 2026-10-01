"""Read-only verifier for the approved M0 registry.

It can establish registry integrity and a blocked/ready disposition. It cannot
certify M0, create receipts, mutate ledgers, authorize LIVE, or promote M1.
"""

import hashlib
import json
from pathlib import Path

from quantumbot_harness.core.m0_invariants import validate_m0_state
from quantumbot_harness.core.safety_cli import protected_path
from quantumbot_harness.core.holdout_evidence import review_holdout_evidence


EXPECTED_REGISTRY_ID = "HARNESS-M0-REGISTRY-001"
EXPECTED_STATUS = "READY_FOR_INDEPENDENT_REVIEW"
EXPECTED_FORMAL_GATE_STATUS = "BLOCKED"
EXPECTED_BASELINE = "GEN-6.11-PASSIVE-EXECUTION-001"
REQUIRED_BOUND_SOURCES = frozenset({
    "quantumbot_harness/core/safety_cli.py",
    "scripts/run_harness_v2_safe.py",
    "tests/test_harness_m0_safety_cli.py",
    "tests/test_m0_formalization_draft.py",
    "quantumbot_harness/specs/SPEC-HARNESS-M0-FORMALIZATION-001.json",
    "quantumbot_harness/docs/M0_FORMALIZATION_PLAN.md",
    "quantumbot_harness/docs/M0_RECEIPT_STATUS_CORRECTION.md",
    "harness.py",
})
REQUIRED_RECEIPTS = (
    "RECEIPT-M0-AUTHORIZATION-001",
    "RECEIPT-M0-CONTROLS-001",
    "RECEIPT-M0-INVARIANTS-001",
    "RECEIPT-M0-PRESERVATION-001",
    "RECEIPT-M0-INDEPENDENT-AUDIT-001",
)


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise PermissionError("SOURCE_PATH_INVALID")
    if ".." in Path(relative).parts:
        raise PermissionError("SOURCE_PATH_INVALID")
    if protected_path(relative, ("FINAL_HOLDOUT", ".env", "quantumbot.db"), root):
        raise PermissionError("SOURCE_PATH_PROTECTED")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise PermissionError("SOURCE_PATH_OUTSIDE_PROJECT")
    return resolved


def verify_registry(project_root):
    root = Path(project_root).resolve()
    errors = []
    holdout_evidence = review_holdout_evidence(project_root)
    errors.extend(holdout_evidence["errors"])
    try:
        registry_path = _safe_source(root, "quantumbot_harness/milestones/M0/REGISTRY.json")
        registry = _load(registry_path)
    except (OSError, PermissionError, ValueError) as exc:
        return {"status": "BLOCKED", "certification_effect": "NONE", "holdout_evidence": holdout_evidence, "errors": errors + [f"REGISTRY_UNAVAILABLE:{type(exc).__name__}"]}

    if not isinstance(registry, dict):
        return {"status": "BLOCKED", "certification_effect": "NONE", "holdout_evidence": holdout_evidence, "errors": errors + ["REGISTRY_SHAPE_INVALID"]}

    if registry.get("registry_id") != EXPECTED_REGISTRY_ID:
        errors.append("REGISTRY_ID_MISMATCH")
    if registry.get("status") != EXPECTED_STATUS:
        errors.append("REGISTRY_STATUS_NOT_REVIEW_READY")
    if registry.get("formal_gate_status") != EXPECTED_FORMAL_GATE_STATUS:
        errors.append("REGISTRY_MUST_REMAIN_BLOCKED")
    if registry.get("certification_effect") != "NONE":
        errors.append("REGISTRY_CANNOT_CERTIFY")
    if registry.get("next_action") != "EXTERNAL_REVIEW":
        errors.append("REGISTRY_NEXT_ACTION_INVALID")
    if registry.get("m1_authorized") is not False or registry.get("live_trading_allowed") is not False:
        errors.append("REGISTRY_AUTHORITY_ESCALATION")
    if registry.get("final_holdout_accessed") is not False:
        errors.append("REGISTRY_HOLDOUT_ASSERTION_INVALID")
    if registry.get("spec_id") != "SPEC-HARNESS-M0-FORMALIZATION-001":
        errors.append("REGISTRY_SPEC_ID_MISMATCH")
    if registry.get("baseline_generation") != EXPECTED_BASELINE:
        errors.append("REGISTRY_BASELINE_MISMATCH")
    if registry.get("inherited_invariants_source") != "quantumbot_harness/policies/V2_INVARIANTS.json":
        errors.append("REGISTRY_INVARIANTS_SOURCE_MISMATCH")
    approval = registry.get("approved_scope")
    if not isinstance(approval, dict) or not approval.get("approved_by") or not approval.get("approved_at"):
        errors.append("REGISTRY_APPROVAL_METADATA_INVALID")
    required_receipts = registry.get("required_receipts")
    if not isinstance(required_receipts, list) or tuple(required_receipts) != REQUIRED_RECEIPTS:
        errors.append("REGISTRY_RECEIPTS_MISMATCH")

    try:
        state = _load(_safe_source(root, "quantumbot_harness/PROJECT_STATE.json"))
        errors.extend(validate_m0_state(state))
    except (OSError, PermissionError, ValueError) as exc:
        errors.append(f"STATE_UNAVAILABLE:{type(exc).__name__}")

    try:
        spec = _load(_safe_source(root, "quantumbot_harness/specs/SPEC-HARNESS-M0-FORMALIZATION-001.json"))
        if not isinstance(spec, dict) or spec.get("status") != "APPROVED" or not spec.get("approved_by") or not spec.get("approved_at"):
            errors.append("SPEC_APPROVAL_INVALID")
        if not isinstance(spec, dict) or spec.get("spec_id") != registry.get("spec_id"):
            errors.append("SPEC_BINDING_MISMATCH")
    except (OSError, PermissionError, ValueError) as exc:
        errors.append(f"SPEC_UNAVAILABLE:{type(exc).__name__}")

    source_results = {}
    bound_sources = registry.get("bound_sources")
    if not isinstance(bound_sources, dict) or set(bound_sources) != REQUIRED_BOUND_SOURCES:
        errors.append("REGISTRY_BOUND_SOURCES_MISMATCH")
        bound_sources = bound_sources if isinstance(bound_sources, dict) else {}
    safe_sources = {}
    for relative, expected in bound_sources.items():
        if relative not in REQUIRED_BOUND_SOURCES or not isinstance(expected, str) or len(expected) != 64:
            errors.append(f"SOURCE_BINDING_INVALID:{relative}")
            continue
        try:
            safe_sources[relative] = _safe_source(root, relative)
        except (OSError, PermissionError) as exc:
            errors.append(f"SOURCE_PATH_INVALID:{relative}:{type(exc).__name__}")
    # Do not read any source until the entire binding set has passed validation.
    if not errors:
        for relative, path in safe_sources.items():
            expected = bound_sources[relative]
            try:
                actual = _hash(path)
            except OSError as exc:
                errors.append(f"SOURCE_UNAVAILABLE:{relative}:{type(exc).__name__}")
                continue
            source_results[relative] = {"expected": expected, "actual": actual, "match": actual == expected}
            if actual != expected:
                errors.append(f"SOURCE_HASH_MISMATCH:{relative}")

    blockers = registry.get("known_blockers")
    if not isinstance(blockers, list) or not blockers:
        errors.append("BLOCKER_REGISTER_MISSING")
    preservation = registry.get("preservation_evidence")
    if not isinstance(preservation, dict):
        errors.append("PRESERVATION_EVIDENCE_INVALID")
        preservation = {}
    if preservation.get("changed_historical_paths") != [] or preservation.get("deleted_artifacts") != []:
        errors.append("HISTORICAL_PRESERVATION_NOT_CLEAN")

    return {
        "registry_id": registry.get("registry_id"),
        "status": "BLOCKED" if errors else EXPECTED_STATUS,
        "formal_gate_status": EXPECTED_FORMAL_GATE_STATUS if not errors else "BLOCKED",
        "certification_effect": "NONE",
        "errors": errors,
        "holdout_evidence": holdout_evidence,
        "source_results": source_results,
        "known_blockers": blockers if isinstance(blockers, list) else [],
        "limits": [
            "This verifier checks an additive registry; it does not create or certify a gate.",
            "Absent historical bar/byte measurements remain UNKNOWN and are not converted to zero.",
            "It does not read real FINAL_HOLDOUT, credentials, or trading database contents.",
            "Independent external disposition remains required before any formal M0 gate.",
            "Historical registry bindings and zero counters cannot certify current non-exposure; successor code changes leave its snapshot unreconciled.",
        ],
    }
