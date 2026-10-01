"""Structural review of the M0 preparation; no registry or approval writes."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1] / "quantumbot_harness"


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_formalization_draft_validates_with_format_checks():
    schema = read("schemas/spec.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        read("specs/SPEC-HARNESS-M0-FORMALIZATION-001.json")
    )


def test_approval_does_not_claim_gate_closure_or_m1_authority():
    draft = read("specs/SPEC-HARNESS-M0-FORMALIZATION-001.json")
    assert draft["status"] == "APPROVED"
    assert draft["approved_by"] == "User-approved in chat"
    assert draft["approved_at"]
    assert draft["gate_id"] is None
    assert draft["closed_at"] is None
    parent = read("specs/SPEC-HARNESS-V2-ENGINEERING-001.json")
    assert parent["status"] == "DESIGN_ONLY"
    assert parent["implementation_authorized"] is False


def test_draft_has_required_receipts_for_every_acceptance_criterion():
    draft = read("specs/SPEC-HARNESS-M0-FORMALIZATION-001.json")
    required = draft["required_receipts"]
    assert required
    assert len(required) == len(set(required))
    assert {criterion["receipt_required"] for criterion in draft["acceptance_criteria"]} == set(required)


def test_draft_does_not_authorize_mutation_of_historical_registries():
    draft = read("specs/SPEC-HARNESS-M0-FORMALIZATION-001.json")
    for path in (
        "harness.py", "quantumbot_harness/PROJECT_STATE.json",
        "quantumbot_harness/tasks/TASK_LEDGER.json",
        "quantumbot_harness/receipts/index.json",
        "quantumbot_harness/specs/SPEC-HARNESS-V2-ENGINEERING-001.json",
    ):
        assert path in draft["files_forbidden"]
        assert path not in draft["files_allowed_to_modify"]
