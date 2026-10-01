"""Read-only M0 contract review. This module grants no execution authority."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from quantumbot_harness.core.holdout_evidence import review_holdout_evidence


# Freeze the existing research baseline while engineering milestones are reviewed.
EXPECTED_STATE = {
    "baseline_generation": "GEN-6.11-PASSIVE-EXECUTION-001",
    "current_certified_phase": "6.11",
    "final_holdout_status": "LOCKED/UNTOUCHED",
    "final_holdout_access_count": 0,
    "live_trading_status": "BLOCKED",
    "allow_live_trading": False,
    "lifetime_formal_hypotheses": 20,
    "validated_development_edge": 0,
    "research_validation_status": "PASSIVE_EXECUTION_UNVIABLE (edge=0, camino_b_concluded)",
}


def validate_m0_state(state):
    """Check historical metadata shape only, not current holdout independence."""
    if not isinstance(state, dict):
        return ["M0_STATE_INVALID: expected an object"]
    errors = []
    for key, expected in EXPECTED_STATE.items():
        observed = state.get(key)
        if type(observed) is not type(expected) or observed != expected:
            errors.append(f"M0_STATE_MISMATCH: {key}")
    # These counters are not recorded by the current PROJECT_STATE. If a later
    # state records them, they must be zero. Absence is disclosed in the review.
    for key in ("holdout_bars_read", "holdout_bytes_read", "final_holdout_bars_read", "final_holdout_bytes_read"):
        if key in state and (type(state[key]) is not int or state[key] != 0):
            errors.append(f"M0_STATE_MISMATCH: {key}")
    return errors


def review_m0(project_root):
    """Review fixed metadata paths only; never load dataset/holdout contents."""
    root = Path(project_root) / "quantumbot_harness"
    sources = {
        "contract": root / "policies" / "V2_INVARIANTS.json",
        "schema": root / "schemas" / "v2_invariants_manifest.schema.json",
        "design": root / "specs" / "SPEC-HARNESS-V2-ENGINEERING-001.json",
        "state": root / "PROJECT_STATE.json",
    }
    documents, errors = {}, []
    for name, path in sources.items():
        try:
            documents[name] = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(documents[name], dict):
                errors.append(f"M0_DOCUMENT_INVALID: {name}")
        except (OSError, ValueError) as exc:
            errors.append(f"M0_SOURCE_UNAVAILABLE: {name} ({type(exc).__name__})")

    if not errors:
        try:
            Draft202012Validator.check_schema(documents["schema"])
            for error in Draft202012Validator(documents["schema"]).iter_errors(documents["contract"]):
                errors.append(f"M0_CONTRACT_INVALID: {error.json_path}: {error.message}")
        except SchemaError as exc:
            errors.append(f"M0_SCHEMA_INVALID: {exc}")

        if documents["contract"].get("invariants") != documents["design"].get("inherited_immutable_invariants"):
            errors.append("M0_INHERITANCE_MISMATCH")
        errors.extend(validate_m0_state(documents["state"]))

    holdout_evidence = review_holdout_evidence(project_root)
    errors.extend(holdout_evidence["errors"])
    state = documents.get("state", {})
    if not isinstance(state, dict):
        state = {}
    return {
        "review_id": "HARNESS-V2-M0-REVIEW-001",
        "status": "BLOCKED" if errors else "PASS",
        "milestone_status": "BLOCKED" if errors else "READY_FOR_INDEPENDENT_REVIEW",
        "certification_effect": "NONE",
        "errors": errors,
        "holdout_evidence": holdout_evidence,
        "observed_state": {key: state.get(key) for key in EXPECTED_STATE},
        "unrecorded_counters": [
            label for label, aliases in (
                ("holdout_bars_read", ("holdout_bars_read", "final_holdout_bars_read")),
                ("holdout_bytes_read", ("holdout_bytes_read", "final_holdout_bytes_read")),
            ) if not any(key in state for key in aliases)
        ],
        "limits": [
            "Review checks metadata and contracts; it does not certify M0 or authorize M1.",
            "Absent bar/byte counters are not evidence of measured zero reads.",
            "Preserved UNTOUCHED/zero metadata does not override confirmed exposure.",
            "Historical artifact immutability is checked by baseline hashes and the existing gate verifier, not by a new filesystem write interceptor.",
        ],
    }
