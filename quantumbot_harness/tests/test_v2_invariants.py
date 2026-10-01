"""M0 executable contracts: metadata, real denial controls, and DEMO isolation."""

import argparse
import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

import harness
from core.entry_policy import resolve_environment
from quantumbot_harness.core.m0_invariants import EXPECTED_STATE, review_m0, validate_m0_state
from research.crypto_quant.holdout_vault import HoldoutVault


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = PROJECT_ROOT / "quantumbot_harness"
CONTRACT = json.loads((HARNESS_ROOT / "policies" / "V2_INVARIANTS.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((HARNESS_ROOT / "schemas" / "v2_invariants_manifest.schema.json").read_text(encoding="utf-8"))


def test_manifest_matches_schema_and_design_inheritance():
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA).validate(CONTRACT)
    design = json.loads((HARNESS_ROOT / "specs" / "SPEC-HARNESS-V2-ENGINEERING-001.json").read_text(encoding="utf-8"))
    assert CONTRACT["invariants"] == design["inherited_immutable_invariants"]
    assert len(CONTRACT["invariants"]) == 14


@pytest.mark.parametrize("key", list(CONTRACT["invariants"]))
def test_every_invariant_is_required_and_cannot_be_weakened(key):
    validator = Draft202012Validator(SCHEMA)
    missing = copy.deepcopy(CONTRACT)
    del missing["invariants"][key]
    with pytest.raises(ValidationError):
        validator.validate(missing)
    changed = copy.deepcopy(CONTRACT)
    value = changed["invariants"][key]
    changed["invariants"][key] = not value if isinstance(value, bool) else 1 if isinstance(value, int) else "WEAKENED"
    with pytest.raises(ValidationError):
        validator.validate(changed)


@pytest.mark.parametrize("key", ["holdout_access_count", "holdout_bars_read", "holdout_bytes_read"])
def test_schema_rejects_boolean_counter_disguised_as_zero(key):
    changed = copy.deepcopy(CONTRACT)
    changed["invariants"][key] = False
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(changed)


@pytest.mark.parametrize("key", list(EXPECTED_STATE))
def test_state_changes_and_missing_fields_fail_closed(key):
    state = dict(EXPECTED_STATE)
    assert validate_m0_state(state) == []
    del state[key]
    assert f"M0_STATE_MISMATCH: {key}" in validate_m0_state(state)
    expected = EXPECTED_STATE[key]
    state[key] = not expected if isinstance(expected, bool) else expected + 1 if isinstance(expected, int) else expected + "_CHANGED"
    assert f"M0_STATE_MISMATCH: {key}" in validate_m0_state(state)


@pytest.mark.parametrize("key", ["holdout_bars_read", "holdout_bytes_read", "final_holdout_bars_read", "final_holdout_bytes_read"])
def test_recorded_read_counters_must_be_zero(key):
    state = dict(EXPECTED_STATE)
    state[key] = 0
    assert validate_m0_state(state) == []
    for invalid in (1, False, "0", None):
        state[key] = invalid
        assert f"M0_STATE_MISMATCH: {key}" in validate_m0_state(state)


def test_review_reports_actual_metadata_and_unrecorded_counters():
    result = review_m0(PROJECT_ROOT)
    assert result["status"] == "PASS"
    assert result["milestone_status"] == "READY_FOR_INDEPENDENT_REVIEW"
    assert result["certification_effect"] == "NONE"
    assert result["observed_state"]["allow_live_trading"] is False
    assert result["observed_state"]["final_holdout_access_count"] == 0
    assert result["unrecorded_counters"] == ["holdout_bars_read", "holdout_bytes_read"]


def test_missing_evidence_blocks_review(tmp_path):
    result = review_m0(tmp_path)
    assert result["status"] == "BLOCKED"
    assert len(result["errors"]) == 4
    assert result["observed_state"]["final_holdout_access_count"] is None


def test_malformed_schema_blocks_review(monkeypatch):
    original = Path.read_text

    def read_with_invalid_schema(path, *args, **kwargs):
        if path.name == "v2_invariants_manifest.schema.json":
            return json.dumps({"type": "invalid-type"})
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_with_invalid_schema)
    result = review_m0(PROJECT_ROOT)
    assert result["status"] == "BLOCKED"
    assert any(error.startswith("M0_SCHEMA_INVALID") for error in result["errors"])


def test_inheritance_drift_blocks_review(monkeypatch):
    original = Path.read_text

    def read_with_changed_design(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        if path.name == "SPEC-HARNESS-V2-ENGINEERING-001.json":
            design = json.loads(value)
            design["inherited_immutable_invariants"]["ALLOW_LIVE_TRADING"] = True
            return json.dumps(design)
        return value

    monkeypatch.setattr(Path, "read_text", read_with_changed_design)
    result = review_m0(PROJECT_ROOT)
    assert result["status"] == "BLOCKED"
    assert "M0_INHERITANCE_MISMATCH" in result["errors"]


@pytest.mark.parametrize("path", ["mock/FINAL_HOLDOUT/data.csv", r"mock\FINAL_HOLDOUT\data.csv"])
def test_existing_harness_blocks_holdout_path_before_hashing(path, monkeypatch, capsys):
    def unexpected_read(*args, **kwargs):
        pytest.fail("Protected path reached file hashing")

    monkeypatch.setattr(harness, "compute_file_sha256", unexpected_read)
    assert harness.cmd_fingerprint(argparse.Namespace(paths=[path])) == 2
    assert "BLOCKED_PROTECTED_PATH" in capsys.readouterr().out


@pytest.mark.parametrize("token", [None, "EXPLICIT_OOS_VERIFICATION_TOKEN_AUTHORIZED"])
def test_actual_locked_vault_denies_synthetic_access_with_permission_error(token):
    # Only an in-memory synthetic fixture is supplied to this real vault.
    frame = pd.DataFrame(
        {"Open": [100.0] * 10, "High": [101.0] * 10, "Low": [99.0] * 10,
         "Close": [100.0] * 10, "Volume": [1.0] * 10},
        index=pd.date_range("2024-01-01", periods=10, freq="15min", tz="UTC"),
    )
    vault = HoldoutVault(frame, final_holdout_locked=True, dataset_id="SYNTHETIC-M0-DENIAL")
    assert len(vault.get_development_data()) == 7
    with pytest.raises(PermissionError, match="HOLDOUT_ACCESS_DENIED"):
        vault.request_final_holdout_data(
            "MOCK-M0", "MOCK-HYPOTHESIS", "1.0.0", "Synthetic denial test", token
        )
    assert len(vault.get_access_log()) == 1
    assert vault.get_access_log()[0].authorized is False


@pytest.mark.parametrize("mode", ["live", "real", "production", "prod"])
def test_actual_environment_policy_denies_live_by_default(mode):
    with pytest.raises(PermissionError, match="ALLOW_LIVE_TRADING"):
        resolve_environment(mode)


def test_demo_is_allowed_without_live_promotion():
    assert resolve_environment("demo", allow_live=False) == (True, "PAPER")
