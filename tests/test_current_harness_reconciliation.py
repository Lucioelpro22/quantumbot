"""Current-state governance checks; do not inspect FINAL_HOLDOUT contents."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_current_project_state_keeps_live_blocked_and_holdout_metadata_locked():
    state = _read_json("quantumbot_harness/PROJECT_STATE.json")

    assert state["current_certified_phase"] == "6.11"
    assert state["current_phase_status"] == "APPROVED"
    assert state["baseline_generation"] == "GEN-6.11-PASSIVE-EXECUTION-001"
    assert state["live_trading_status"] == "BLOCKED"
    assert state["allow_live_trading"] is False
    assert state["final_holdout_status"] == "LOCKED/UNTOUCHED"
    assert state["final_holdout_access_count"] == 0
    assert state["lifetime_formal_hypotheses"] == 20


def test_current_gate_passes_and_requires_canonical_receipts():
    gate = _read_json(
        "quantumbot_harness/gates/GATE-FASE611-PASSIVE-EXECUTION-001.json"
    )

    assert gate["status"] == "PASS"
    assert gate["required_baseline_generation"] == "GEN-6.11-PASSIVE-EXECUTION-001"
    assert "RECEIPT-CANON-ENGINEERING-HARNESS-POST-FASE611" in gate["required_receipts"]
    assert "RECEIPT-CANON-MULTIPLE-TESTING-LEDGER-V2-POST-FASE611" in gate["required_receipts"]


def test_current_canonical_receipt_hashes_match_disk():
    index = _read_json("quantumbot_harness/receipts/index.json")
    required = {
        "RECEIPT-CANON-ENGINEERING-HARNESS-POST-FASE611",
        "RECEIPT-CANON-MULTIPLE-TESTING-LEDGER-V2-POST-FASE611",
    }
    entries = {entry["receipt_id"]: entry for entry in index["receipts"]}

    for receipt_id in required:
        entry = entries[receipt_id]
        file_path = ROOT / entry["source_path"]
        content = file_path.read_bytes()
        assert len(content) == entry["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]

