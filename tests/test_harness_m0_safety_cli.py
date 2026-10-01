"""M0 regressions with fictitious paths and in-memory metadata only."""

import argparse
import hashlib
import json
from pathlib import Path

import harness
import pytest

from quantumbot_harness.core import safety_cli


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def safe_harness():
    return safety_cli.load_safe_harness()


@pytest.mark.parametrize("path", [
    "mock/FINAL_HOLDOUT/data.csv",
    "mock/final_holdout/data.csv",
    "mock/Final_Holdout/data.csv",
    r"mock\final_holdout\data.csv",
    "mock/FINAL_HOLDOUT./data.csv",
    "mock/final_holdout /data.csv",
    "CONFIG/SETTINGS.YAML",
    "MAIN.PY",
    "DATA/RAW/BYBIT/trades.csv",
    "mock/.ENV",
    "DATABASE/QUANTUMBOT.DB",
])
def test_fingerprint_denies_before_hashing(path, safe_harness, monkeypatch, capsys):
    def unexpected_read(*args):
        pytest.fail("Protected path reached hashing")

    monkeypatch.setattr(safe_harness, "compute_file_sha256", unexpected_read)
    assert safe_harness.cmd_fingerprint(argparse.Namespace(paths=[path])) == 2
    assert "BLOCKED_PROTECTED_PATH" in capsys.readouterr().out


def test_unprotected_read_only_fingerprint_positive_control(safe_harness, capsys):
    source = "quantumbot_harness/core/m0_invariants.py"
    assert safe_harness.cmd_fingerprint(argparse.Namespace(paths=[source])) == 0
    output = capsys.readouterr().out
    assert hashlib.sha256((PROJECT_ROOT / source).read_bytes()).hexdigest() in output


def test_isolated_module_does_not_patch_historical_harness(safe_harness):
    assert safe_harness is not harness
    assert safe_harness.is_protected_path("mock/final_holdout/file.csv") is True
    assert harness.is_protected_path("mock/final_holdout/file.csv") is False


@pytest.mark.parametrize("pattern", harness.PROTECTED_PATTERNS)
def test_all_inherited_protected_patterns_are_case_insensitive(pattern, safe_harness):
    assert safe_harness.is_protected_path(pattern.upper().replace("/", "\\"))


@pytest.mark.parametrize("override", [
    {"final_holdout_access_count": 1},
    {"final_holdout_access_count": False},
    {"final_holdout_status": "UNLOCKED"},
    {"allow_live_trading": True},
    {"allow_live_trading": 0},
    {"live_trading_status": "LIVE"},
    {"lifetime_formal_hypotheses": 21},
    {"holdout_bars_read": 1},
    {"holdout_bytes_read": 1},
])
def test_real_validation_blocks_unsafe_metadata(override, safe_harness, monkeypatch, capsys):
    original = safe_harness.load_json

    def synthetic_load(path):
        document = original(path)
        return {**document, **override} if Path(path).name == "PROJECT_STATE.json" else document

    monkeypatch.setattr(safe_harness, "load_json", synthetic_load)
    assert safe_harness.cmd_validate(argparse.Namespace()) == 1
    assert "BLOCKED_SAFETY_STATE" in capsys.readouterr().out


@pytest.mark.parametrize("missing", ["allow_live_trading", "final_holdout_access_count"])
def test_missing_safety_fields_block(safe_harness, monkeypatch, missing):
    original = safe_harness.load_json

    def synthetic_load(path):
        document = original(path)
        if Path(path).name == "PROJECT_STATE.json":
            del document[missing]
        return document

    monkeypatch.setattr(safe_harness, "load_json", synthetic_load)
    assert safe_harness.cmd_validate(argparse.Namespace()) == 1


def test_missing_state_file_blocks(safe_harness, monkeypatch):
    def missing(path):
        raise FileNotFoundError("synthetic missing metadata")

    monkeypatch.setattr(safe_harness, "load_json", missing)
    assert safe_harness.cmd_validate(argparse.Namespace()) == 1


@pytest.mark.parametrize("state", [None, [], "unsafe state", {}])
def test_non_object_or_empty_state_blocks(safe_harness, monkeypatch, state):
    monkeypatch.setattr(safe_harness, "load_json", lambda path: state)
    assert safe_harness.cmd_validate(argparse.Namespace()) == 1


def test_invalid_state_json_blocks(safe_harness, monkeypatch):
    def malformed(path):
        raise json.JSONDecodeError("synthetic invalid metadata", "{", 1)

    monkeypatch.setattr(safe_harness, "load_json", malformed)
    assert safe_harness.cmd_validate(argparse.Namespace()) == 1


def test_safe_validation_positive_control(safe_harness, capsys):
    assert safe_harness.cmd_validate(argparse.Namespace()) == 0
    assert "[SAFETY PASS]" in capsys.readouterr().out


@pytest.mark.parametrize("path", ["mock/final_holdout/file.csv", "mock/.ENV", "mock/QUANTUMBOT.DB"])
def test_hash_boundary_denies_without_opening_file(safe_harness, path):
    with pytest.raises(PermissionError, match="BLOCKED_PROTECTED_PATH"):
        safe_harness.compute_file_sha256(PROJECT_ROOT / path)


@pytest.mark.parametrize("path", ["mock/final_holdout/file.json", "mock/.ENV", "mock/QUANTUMBOT.DB"])
def test_json_boundary_denies_before_opening_file(safe_harness, path):
    with pytest.raises(PermissionError, match="BLOCKED_PROTECTED_PATH"):
        safe_harness.load_json(PROJECT_ROOT / path)


@pytest.mark.parametrize("method", ["load_json", "compute_file_sha256"])
def test_read_boundaries_reject_outside_project(safe_harness, method):
    fictitious = PROJECT_ROOT.parent / "MOCK-M0-OUTSIDE-PROJECT.json"
    with pytest.raises(PermissionError, match="BLOCKED_OUTSIDE_PROJECT"):
        getattr(safe_harness, method)(fictitious)


@pytest.mark.parametrize("command", [
    ["validate"],
    ["fingerprint", "quantumbot_harness/core/m0_invariants.py"],
    ["verify-all", "GATE-FASE611-PASSIVE-EXECUTION-001"],
])
def test_all_cli_commands_reject_unsafe_state(command, safe_harness, monkeypatch):
    original = safe_harness.load_json

    def unsafe(path):
        document = original(path)
        return {**document, "allow_live_trading": True} if Path(path).name == "PROJECT_STATE.json" else document

    monkeypatch.setattr(safe_harness, "load_json", unsafe)
    monkeypatch.setattr(safety_cli, "load_safe_harness", lambda: safe_harness)
    monkeypatch.setattr(
        safe_harness, "compute_file_sha256",
        lambda path: pytest.fail("Unsafe state reached file hashing"),
    )
    assert safety_cli.main(command) == 1


def test_verify_all_inherits_state_guard(safe_harness, monkeypatch, capsys):
    original = safe_harness.load_json

    def unsafe(path):
        document = original(path)
        return {**document, "final_holdout_access_count": 1} if Path(path).name == "PROJECT_STATE.json" else document

    monkeypatch.setattr(safe_harness, "load_json", unsafe)
    assert safe_harness.cmd_verify_all(argparse.Namespace(gate_id="GATE-FASE611-PASSIVE-EXECUTION-001")) == 1
    assert "BLOCKED_SAFETY_STATE" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["certify", "run", "freeze", "gate"])
def test_cli_exposes_no_mutating_commands(command):
    with pytest.raises(SystemExit) as exc:
        safety_cli.main([command])
    assert exc.value.code == 2


def test_gate_path_traversal_rejected():
    assert safety_cli.main(["verify-all", "GATE-../../FINAL_HOLDOUT/data"]) == 2


def test_drifted_historical_source_blocks_before_execution(monkeypatch):
    original = Path.read_bytes

    def altered_source(path):
        data = original(path)
        return data + b"\n# synthetic source drift\n" if path == PROJECT_ROOT / "harness.py" else data

    monkeypatch.setattr(Path, "read_bytes", altered_source)
    with pytest.raises(RuntimeError, match="SAFETY_HARNESS_SOURCE_DRIFT"):
        safety_cli.load_safe_harness()


def test_cli_reports_source_drift_as_blocked(monkeypatch, capsys):
    def drifted():
        raise RuntimeError("SAFETY_HARNESS_SOURCE_DRIFT")

    monkeypatch.setattr(safety_cli, "load_safe_harness", drifted)
    assert safety_cli.main(["validate"]) == 2
    assert "SAFETY_HARNESS_SOURCE_DRIFT" in capsys.readouterr().out


@pytest.mark.parametrize("status", [
    "PENDING", "PENDING_MANIFEST", "UNKNOWN", "INVALID", "SUPERSEDED",
    "verified", " VERIFIED", None, True, "<MISSING>",
])
@pytest.mark.parametrize("method", ["cmd_gate", "cmd_verify_all"])
def test_required_receipt_must_be_exactly_verified(status, method, safe_harness, monkeypatch, capsys):
    original = safe_harness.load_json

    def synthetic_receipt(path):
        document = original(path)
        if Path(path) == safe_harness.RECEIPTS_DIR / "index.json":
            for receipt in document["receipts"]:
                if receipt["receipt_id"] == "RECEIPT-FASE611-REPORT-001":
                    if status == "<MISSING>":
                        receipt.pop("verification_status", None)
                    else:
                        receipt["verification_status"] = status
        return document

    monkeypatch.setattr(safe_harness, "load_json", synthetic_receipt)
    monkeypatch.setattr(safe_harness, "compute_file_sha256", lambda path: pytest.fail("Unverified receipt reached hashing"))
    assert getattr(safe_harness, method)(argparse.Namespace(gate_id="GATE-FASE611-PASSIVE-EXECUTION-001")) == 1
    assert "VERIFIED_PASS" not in capsys.readouterr().out


def test_cli_rejects_pending_receipt(safe_harness, monkeypatch):
    original = safe_harness.load_json

    def pending(path):
        document = original(path)
        if Path(path) == safe_harness.RECEIPTS_DIR / "index.json":
            for receipt in document["receipts"]:
                if receipt["receipt_id"] == "RECEIPT-FASE611-REPORT-001":
                    receipt["verification_status"] = "PENDING"
        return document

    monkeypatch.setattr(safe_harness, "load_json", pending)
    monkeypatch.setattr(safety_cli, "load_safe_harness", lambda: safe_harness)
    assert safety_cli.main(["verify-all", "GATE-FASE611-PASSIVE-EXECUTION-001"]) == 1


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_missing_or_ambiguous_required_receipt_blocks(mutation, safe_harness, monkeypatch):
    original = safe_harness.load_json

    def mutated(path):
        document = original(path)
        if Path(path) == safe_harness.RECEIPTS_DIR / "index.json":
            target = "RECEIPT-FASE611-REPORT-001"
            if mutation == "missing":
                document["receipts"] = [r for r in document["receipts"] if r["receipt_id"] != target]
            else:
                document["receipts"].append(dict(next(r for r in document["receipts"] if r["receipt_id"] == target)))
        return document

    monkeypatch.setattr(safe_harness, "load_json", mutated)
    monkeypatch.setattr(safe_harness, "compute_file_sha256", lambda path: pytest.fail("Ambiguous receipt reached hashing"))
    assert safe_harness.cmd_gate(argparse.Namespace(gate_id="GATE-FASE611-PASSIVE-EXECUTION-001")) == 1


def test_verified_required_receipts_positive_control(safe_harness, capsys):
    assert safe_harness.cmd_gate(argparse.Namespace(gate_id="GATE-FASE611-PASSIVE-EXECUTION-001")) == 0
    assert "GATE_VERIFIED: PASS" in capsys.readouterr().out


def test_gate_uses_single_checked_receipt_snapshot(safe_harness, monkeypatch):
    original = safe_harness.load_json
    loads = []

    def alternating(path):
        document = original(path)
        if Path(path) == safe_harness.RECEIPTS_DIR / "index.json":
            loads.append(path)
            if len(loads) > 1:
                for receipt in document["receipts"]:
                    if receipt["receipt_id"] == "RECEIPT-FASE611-REPORT-001":
                        receipt["verification_status"] = "PENDING"
        return document

    monkeypatch.setattr(safe_harness, "load_json", alternating)
    assert safe_harness.cmd_gate(argparse.Namespace(gate_id="GATE-FASE611-PASSIVE-EXECUTION-001")) == 0
    assert len(loads) == 1


def test_historical_evidence_stays_unchanged():
    evidence_path = PROJECT_ROOT / "quantumbot_harness/docs/M0_REVIEW_EVIDENCE.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    records = {
        **evidence["protected_metadata_comparison"]["sha256_before"],
        **evidence["sources_sha256"],
    }
    for relative, expected in records.items():
        assert not any(part.casefold() in {"final_holdout", ".env"} for part in Path(relative).parts)
        assert hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest() == expected, relative
