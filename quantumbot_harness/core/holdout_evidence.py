"""Current holdout-evidence disposition; fixed metadata only, no payload I/O.

Historical zero counters are observations, not evidence of independence. The
known exposure cannot be cleared by deleting, closing or rewriting its incident.
This module does not impose a sandbox on the immutable historical harness.
"""

import hashlib
import json
from pathlib import Path


INCIDENT_PATH = "quantumbot_harness/docs/FASE61_HOLDOUT_EXPOSURE_INCIDENT_001.json"
INCIDENT_ID = "FASE61-HOLDOUT-EXPOSURE-INCIDENT-001"
INCIDENT_SHA256 = "0a418335eb15e95d780887adfbea32539bcb87c48a0e7c0ec25020ca2f5c58d4"
MAX_METADATA_BYTES = 65536


def _incident_bytes(project_root):
    """Deny redirects before opening the one allowlisted metadata file."""
    root = Path(project_root).absolute()
    path = root / INCIDENT_PATH
    if path.resolve(strict=False) != path:
        raise PermissionError("INCIDENT_PATH_REDIRECTED")
    for component in (path, *path.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise PermissionError("INCIDENT_PATH_REDIRECTED")
    with path.open("rb", buffering=0) as source:
        payload = source.read(MAX_METADATA_BYTES + 1)
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError("INCIDENT_METADATA_TOO_LARGE")
    return payload


def review_holdout_evidence(project_root):
    """Always reject current independence for the known exposed workflow.

Missing/invalid incident evidence is BLOCKED, never an implicit clean state.
The pinned digest authenticates the preserved snapshot, not market data.
"""
    result = {
        "status": "BLOCKED",
        "independent_validation_eligibility": "INELIGIBLE_FOR_THIS_WORKFLOW",
        "historical_exposure": "CONFIRMED_BY_PINNED_INCIDENT_RECORD",
        "incident_evidence_status": "UNVERIFIED",
        "incident_path": INCIDENT_PATH,
        "expected_incident_sha256": INCIDENT_SHA256,
        "observed_incident_sha256": None,
        "exact_historical_read_operations": "UNKNOWN",
        "exact_historical_holdout_bytes_read": "UNKNOWN",
        "canonical_zero_counters_are_current_proof": False,
        "certification_effect": "NONE",
        "errors": [],
    }
    try:
        payload = _incident_bytes(project_root)
    except (OSError, ValueError, RuntimeError) as exc:
        result["errors"] = [f"HOLDOUT_INCIDENT_UNAVAILABLE:{type(exc).__name__}"]
        return result
    digest = hashlib.sha256(payload).hexdigest()
    result["observed_incident_sha256"] = digest
    if digest != INCIDENT_SHA256:
        result["errors"] = ["HOLDOUT_INCIDENT_HASH_MISMATCH"]
        return result
    try:
        incident = json.loads(payload)
    except (ValueError, UnicodeError):
        result["errors"] = ["HOLDOUT_INCIDENT_INVALID_JSON"]
        return result
    if (
        not isinstance(incident, dict)
        or incident.get("report_id") != INCIDENT_ID
        or incident.get("historical_holdout_exposure") != "CONFIRMED"
        or not isinstance(incident.get("disposition"), dict)
        or incident["disposition"].get("historical_holdout_independence")
        != "COMPROMISED_FOR_THIS_WORKFLOW"
    ):
        result["errors"] = ["HOLDOUT_INCIDENT_SHAPE_INVALID"]
        return result
    result["incident_evidence_status"] = "VERIFIED_PRESERVED_SNAPSHOT"
    result["errors"] = ["HOLDOUT_EXPOSURE_CONFIRMED"]
    return result
