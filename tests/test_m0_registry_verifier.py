"""Read-only tests for the approved M0 registry and its blocked authority."""

import copy
import json
from pathlib import Path

from quantumbot_harness.core.m0_gate_verifier import verify_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "quantumbot_harness" / "milestones" / "M0" / "REGISTRY.json"


def test_registry_is_review_ready_but_formally_blocked():
    result = verify_registry(ROOT)
    assert result["status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert result["formal_gate_status"] == "BLOCKED"
    assert result["certification_effect"] == "NONE"
    assert result["errors"] == []
    assert result["known_blockers"]


def test_registry_sources_match():
    result = verify_registry(ROOT)
    assert all(item["match"] for item in result["source_results"].values())


def test_tampered_registry_authority_blocks(monkeypatch):
    original = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    altered = copy.deepcopy(original)
    altered["formal_gate_status"] = "PASS"
    altered["certification_effect"] = "CERTIFIED"

    import quantumbot_harness.core.m0_gate_verifier as verifier
    monkeypatch.setattr(verifier, "_load", lambda path: altered if Path(path) == REGISTRY_PATH else json.loads(Path(path).read_text(encoding="utf-8")))
    result = verifier.verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert "REGISTRY_MUST_REMAIN_BLOCKED" in result["errors"]
    assert "REGISTRY_CANNOT_CERTIFY" in result["errors"]


def test_tampered_bound_source_blocks(monkeypatch):
    original = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    altered = copy.deepcopy(original)
    altered["bound_sources"]["quantumbot_harness/core/safety_cli.py"] = "0" * 64

    import quantumbot_harness.core.m0_gate_verifier as verifier
    monkeypatch.setattr(verifier, "_load", lambda path: altered if Path(path) == REGISTRY_PATH else json.loads(Path(path).read_text(encoding="utf-8")))
    result = verifier.verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert "SOURCE_HASH_MISMATCH:quantumbot_harness/core/safety_cli.py" in result["errors"]


def test_missing_state_blocks(monkeypatch):
    import quantumbot_harness.core.m0_gate_verifier as verifier
    original = verifier._load

    def missing(path):
        if Path(path).name == "PROJECT_STATE.json":
            raise FileNotFoundError("synthetic")
        return original(path)

    monkeypatch.setattr(verifier, "_load", missing)
    result = verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert any(error.startswith("STATE_UNAVAILABLE") for error in result["errors"])


def test_empty_bound_sources_blocks_without_hashing(monkeypatch):
    original = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    altered = copy.deepcopy(original)
    altered["bound_sources"] = {}

    import quantumbot_harness.core.m0_gate_verifier as verifier
    monkeypatch.setattr(verifier, "_load", lambda path: altered if Path(path) == REGISTRY_PATH else json.loads(Path(path).read_text(encoding="utf-8")))
    monkeypatch.setattr(verifier, "_hash", lambda path: (_ for _ in ()).throw(AssertionError("hash reached")))
    result = verifier.verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert "REGISTRY_BOUND_SOURCES_MISMATCH" in result["errors"]
    assert result["source_results"] == {}


def test_arbitrary_outside_source_blocks_before_hashing(monkeypatch):
    original = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    altered = copy.deepcopy(original)
    altered["bound_sources"]["mock/Final_Holdout/MOCK-MISSING.csv"] = "0" * 64

    import quantumbot_harness.core.m0_gate_verifier as verifier
    monkeypatch.setattr(verifier, "_load", lambda path: altered if Path(path) == REGISTRY_PATH else json.loads(Path(path).read_text(encoding="utf-8")))
    monkeypatch.setattr(verifier, "_hash", lambda path: (_ for _ in ()).throw(AssertionError("hash reached")))
    result = verifier.verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert "REGISTRY_BOUND_SOURCES_MISMATCH" in result["errors"]
    assert any(error.startswith("SOURCE_BINDING_INVALID") for error in result["errors"])


def test_invalid_registry_shape_blocks(monkeypatch):
    import quantumbot_harness.core.m0_gate_verifier as verifier
    monkeypatch.setattr(verifier, "_load", lambda path: [])
    result = verifier.verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert "REGISTRY_SHAPE_INVALID" in result["errors"]


def test_invalid_receipt_and_preservation_shapes_block(monkeypatch):
    original = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    altered = copy.deepcopy(original)
    altered["required_receipts"] = None
    altered["preservation_evidence"] = []

    import quantumbot_harness.core.m0_gate_verifier as verifier
    monkeypatch.setattr(verifier, "_load", lambda path: altered if Path(path) == REGISTRY_PATH else json.loads(Path(path).read_text(encoding="utf-8")))
    result = verifier.verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert "REGISTRY_RECEIPTS_MISMATCH" in result["errors"]
    assert "PRESERVATION_EVIDENCE_INVALID" in result["errors"]


def test_invalid_approval_and_binding_metadata_block(monkeypatch):
    original = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    altered = copy.deepcopy(original)
    altered["baseline_generation"] = "WRONG"
    altered["inherited_invariants_source"] = "wrong.json"
    altered["approved_scope"] = {}

    import quantumbot_harness.core.m0_gate_verifier as verifier
    monkeypatch.setattr(verifier, "_load", lambda path: altered if Path(path) == REGISTRY_PATH else json.loads(Path(path).read_text(encoding="utf-8")))
    result = verifier.verify_registry(ROOT)
    assert result["status"] == "BLOCKED"
    assert "REGISTRY_BASELINE_MISMATCH" in result["errors"]
    assert "REGISTRY_INVARIANTS_SOURCE_MISMATCH" in result["errors"]
    assert "REGISTRY_APPROVAL_METADATA_INVALID" in result["errors"]
