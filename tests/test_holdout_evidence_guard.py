"""Current exposure regression suite: synthetic fixtures and code metadata only."""

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from quantumbot_harness.core import holdout_evidence as guard
from quantumbot_harness.core import m0_gate_verifier as registry
from quantumbot_harness.core import safety_cli
from quantumbot_harness.core.m0_invariants import review_m0, validate_m0_state, EXPECTED_STATE


ROOT = Path(__file__).resolve().parents[1]


def incident():
    return {
        "report_id": guard.INCIDENT_ID,
        "historical_holdout_exposure": "CONFIRMED",
        "status": "OPEN_GOVERNANCE_INCIDENT",
        "disposition": {"historical_holdout_independence": "COMPROMISED_FOR_THIS_WORKFLOW"},
    }


def bind_synthetic(monkeypatch, document):
    payload = json.dumps(document).encode()
    monkeypatch.setattr(guard, "INCIDENT_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(guard, "_incident_bytes", lambda root: payload)


def test_confirmed_exposure_blocks_despite_historical_zero_metadata():
    assert validate_m0_state(dict(EXPECTED_STATE)) == []  # structural, not independence
    result = guard.review_holdout_evidence(ROOT)
    assert result["status"] == "BLOCKED"
    assert result["errors"] == ["HOLDOUT_EXPOSURE_CONFIRMED"]
    assert result["incident_evidence_status"] == "VERIFIED_PRESERVED_SNAPSHOT"
    assert result["canonical_zero_counters_are_current_proof"] is False
    assert result["exact_historical_read_operations"] == "UNKNOWN"
    assert result["exact_historical_holdout_bytes_read"] == "UNKNOWN"


def test_missing_incident_never_means_clean(tmp_path):
    result = guard.review_holdout_evidence(tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["historical_exposure"] == "CONFIRMED_BY_PINNED_INCIDENT_RECORD"
    assert result["errors"] == ["HOLDOUT_INCIDENT_UNAVAILABLE:FileNotFoundError"]


@pytest.mark.parametrize("exception", [PermissionError, OSError, ValueError, RuntimeError])
def test_unavailable_incident_blocks(monkeypatch, exception):
    def denied(root):
        raise exception("synthetic failure")
    monkeypatch.setattr(guard, "_incident_bytes", denied)
    assert guard.review_holdout_evidence(ROOT)["errors"] == [f"HOLDOUT_INCIDENT_UNAVAILABLE:{exception.__name__}"]


@pytest.mark.parametrize("payload", [b"", b"{}", b"{broken", b"false", b"\xff", b"[]"])
def test_unbound_modified_incident_blocks_before_parsing(monkeypatch, payload):
    monkeypatch.setattr(guard, "_incident_bytes", lambda root: payload)
    assert guard.review_holdout_evidence(ROOT)["errors"] == ["HOLDOUT_INCIDENT_HASH_MISMATCH"]


@pytest.mark.parametrize("payload", [b"{broken", b"\xff"])
def test_bound_invalid_json_blocks(monkeypatch, payload):
    monkeypatch.setattr(guard, "INCIDENT_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(guard, "_incident_bytes", lambda root: payload)
    assert guard.review_holdout_evidence(ROOT)["errors"] == ["HOLDOUT_INCIDENT_INVALID_JSON"]


@pytest.mark.parametrize("document", [None, [], False, {},
    {"report_id": "WRONG"},
    {"report_id": guard.INCIDENT_ID, "historical_holdout_exposure": "UNTOUCHED"},
    {"report_id": guard.INCIDENT_ID, "historical_holdout_exposure": "CONFIRMED", "disposition": []},
    {"report_id": guard.INCIDENT_ID, "historical_holdout_exposure": "CONFIRMED", "disposition": {}},
])
def test_bound_invalid_shape_never_passes(monkeypatch, document):
    bind_synthetic(monkeypatch, document)
    assert guard.review_holdout_evidence(ROOT)["errors"] == ["HOLDOUT_INCIDENT_SHAPE_INVALID"]


@pytest.mark.parametrize("status", ["CLOSED", "RESOLVED", "APPROVED", None])
def test_administrative_closure_does_not_restore_independence(monkeypatch, status):
    document = incident()
    document["status"] = status
    bind_synthetic(monkeypatch, document)
    result = guard.review_holdout_evidence(ROOT)
    assert result["status"] == "BLOCKED"
    assert result["errors"] == ["HOLDOUT_EXPOSURE_CONFIRMED"]


def test_reader_only_opens_fixed_metadata_bounded_and_unbuffered(tmp_path, monkeypatch):
    calls = []
    class Source:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, count):
            assert count == guard.MAX_METADATA_BYTES + 1
            return b"synthetic-metadata"
    def opened(path, mode, **kwargs):
        calls.append(path)
        assert path == tmp_path / guard.INCIDENT_PATH
        assert mode == "rb" and kwargs == {"buffering": 0}
        return Source()
    monkeypatch.setattr(Path, "open", opened)
    assert guard._incident_bytes(tmp_path) == b"synthetic-metadata"
    assert len(calls) == 1


def test_oversized_metadata_blocks(tmp_path):
    path = tmp_path / guard.INCIDENT_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * (guard.MAX_METADATA_BYTES + 2))
    assert guard.review_holdout_evidence(tmp_path)["status"] == "BLOCKED"
    with pytest.raises(ValueError, match="INCIDENT_METADATA_TOO_LARGE"):
        guard._incident_bytes(tmp_path)


@pytest.mark.parametrize("alias", ["resolved", "symlink", "junction", "parent_symlink"])
def test_aliases_rejected_before_open(tmp_path, monkeypatch, alias):
    path = tmp_path / guard.INCIDENT_PATH
    original_resolve = Path.resolve
    if alias == "resolved":
        monkeypatch.setattr(Path, "resolve", lambda self, **kw: tmp_path / "FINAL_HOLDOUT" / "payload.csv" if self == path else original_resolve(self, **kw))
    elif alias == "junction":
        monkeypatch.setattr(Path, "is_junction", lambda self: self == path.parent, raising=False)
    else:
        target = path if alias == "symlink" else path.parent
        monkeypatch.setattr(Path, "is_symlink", lambda self: self == target)
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("Redirected metadata reached payload open"))
    assert guard.review_holdout_evidence(tmp_path)["errors"] == ["HOLDOUT_INCIDENT_UNAVAILABLE:PermissionError"]


def test_current_m0_review_rejects_preserved_zero_metadata():
    result = review_m0(ROOT)
    assert result["status"] == result["milestone_status"] == "BLOCKED"
    assert result["observed_state"]["final_holdout_access_count"] == 0
    assert result["holdout_evidence"]["exact_historical_read_operations"] == "UNKNOWN"
    assert "HOLDOUT_EXPOSURE_CONFIRMED" in result["errors"]
    assert result["certification_effect"] == "NONE"


def test_current_registry_blocks_before_bound_source_hashing(monkeypatch):
    monkeypatch.setattr(registry, "_hash", lambda path: pytest.fail("Exposure reached source hashing"))
    result = registry.verify_registry(ROOT)
    assert result["status"] == result["formal_gate_status"] == "BLOCKED"
    assert "HOLDOUT_EXPOSURE_CONFIRMED" in result["errors"]
    assert result["source_results"] == {}
    assert result["certification_effect"] == "NONE"


@pytest.mark.parametrize("method,args", [
    ("cmd_validate", argparse.Namespace()),
    ("cmd_gate", argparse.Namespace(gate_id="GATE-FASE611-PASSIVE-EXECUTION-001")),
    ("cmd_verify_all", argparse.Namespace(gate_id="GATE-FASE611-PASSIVE-EXECUTION-001")),
    ("cmd_fingerprint", argparse.Namespace(paths=["quantumbot_harness/core/m0_invariants.py"])),
])
def test_successor_direct_commands_reject_before_proof_or_hashing(monkeypatch, capsys, method, args):
    safe = safety_cli.load_safe_harness()
    original_load = safe.load_json
    def state_only(path):
        assert Path(path).name == "PROJECT_STATE.json", "Reached historical proof metadata"
        return original_load(path)
    monkeypatch.setattr(safe, "load_json", state_only)
    monkeypatch.setattr(safe, "compute_file_sha256", lambda path: pytest.fail("Exposure reached source hashing"))
    assert getattr(safe, method)(args) == 1
    output = capsys.readouterr().out
    assert "HOLDOUT_EXPOSURE_CONFIRMED" in output
    assert "VERIFIED_PASS" not in output and "[SAFETY PASS]" not in output


@pytest.mark.parametrize("command", [
    ["validate"],
    ["verify-all", "GATE-FASE611-PASSIVE-EXECUTION-001"],
    ["fingerprint", "quantumbot_harness/core/m0_invariants.py"],
])
def test_successor_cli_blocks_exposure(monkeypatch, command, capsys):
    safe = safety_cli.load_safe_harness()
    monkeypatch.setattr(safety_cli, "load_safe_harness", lambda: safe)
    monkeypatch.setattr(safe, "compute_file_sha256", lambda path: pytest.fail("Exposure reached source hashing"))
    assert safety_cli.main(command) == 1
    assert "HOLDOUT_EXPOSURE_CONFIRMED" in capsys.readouterr().out


def test_archived_assertions_have_current_replacements_and_unchanged_sources():
    lineage = json.loads((ROOT / "tests/test_lineage.json").read_text(encoding="utf-8"))
    additions = lineage["holdout_exposure_guard_archive"]
    assert set(additions) <= set(lineage["archived_nodeids"])
    assert len(additions) == 10
    for replacement in additions.values():
        assert replacement in globals() and callable(globals()[replacement])
    snapshot = json.loads((ROOT / "quantumbot_harness/docs/FASE61_HOLDOUT_EVIDENCE_GUARD_SNAPSHOT_001.json").read_text(encoding="utf-8"))
    for binding in snapshot["sources"]:
        assert hashlib.sha256(binding["content"].encode("utf-8")).hexdigest() == binding["sha256"]
    for binding in snapshot["preserved_sources"]:
        assert hashlib.sha256((ROOT / binding["path"]).read_bytes()).hexdigest() == binding["sha256"], binding["path"]


def test_safe_module_does_not_change_historical_harness():
    source = ROOT / "harness.py"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == safety_cli.HISTORICAL_HARNESS_SHA256
