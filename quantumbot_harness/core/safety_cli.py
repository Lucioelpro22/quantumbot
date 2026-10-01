"""Additive, read-only M0 entry point; historical harness bytes stay sealed.

This is not a global filesystem sandbox or a certification authority. Only
callers using this entry point receive the additional safety checks.
"""

import argparse
import hashlib
import importlib.util
import ntpath
from pathlib import Path

from quantumbot_harness.core.m0_invariants import validate_m0_state
from quantumbot_harness.core.holdout_evidence import review_holdout_evidence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_HARNESS_SHA256 = "b6eefcba50ed0bc520c25dc048a1f1ffd5358dc975d82e64af65036a3ed7bd27"


def _path_forms(value):
    raw = str(value).replace("\\", "/").casefold()
    # Win32 ignores trailing dots/spaces in ordinary path components.
    windows = "/".join(part.rstrip(" .") for part in raw.split("/"))
    return (raw, windows, ntpath.normpath(windows).replace("\\", "/"))


def protected_path(value, patterns, project_root=PROJECT_ROOT):
    """Check both spelling and resolved aliases, without opening file contents."""
    forms = list(_path_forms(value))
    resolved = (Path(project_root) / str(value).replace("\\", "/")).resolve()
    forms.extend(_path_forms(resolved))
    return any(
        str(pattern).replace("\\", "/").casefold().strip("/") in form
        for pattern in patterns
        for form in forms
    )


def load_safe_harness(project_root=PROJECT_ROOT):
    """Load an isolated legacy module; never patch the shared imported harness."""
    root = Path(project_root).resolve()
    source_path = root / "harness.py"
    source_bytes = source_path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != HISTORICAL_HARNESS_SHA256:
        raise RuntimeError("SAFETY_HARNESS_SOURCE_DRIFT")
    # The historical module ensures these directories on import. Require them
    # to exist so this read-only entry does not bootstrap a missing project.
    for directory in ("candidates", "executions"):
        if not (root / "quantumbot_harness" / directory).is_dir():
            raise RuntimeError("SAFETY_HARNESS_METADATA_MISSING")
    spec = importlib.util.spec_from_file_location(
        "_quantumbot_m0_safe_harness", root / "harness.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("SAFETY_HARNESS_UNAVAILABLE")
    legacy = importlib.util.module_from_spec(spec)
    # Execute the exact verified bytes, not a second read of potentially changed
    # source or a cached bytecode file.
    exec(compile(source_bytes, str(source_path), "exec"), legacy.__dict__)

    legacy.is_protected_path = lambda value: protected_path(
        value, legacy.PROTECTED_PATTERNS, root
    )
    original_hash = legacy.compute_file_sha256
    original_load = legacy.load_json

    def reject_exposed_evidence():
        evidence = review_holdout_evidence(root)
        if evidence["status"] != "BLOCKED":
            # There is no admissible clean state for this exposed workflow.
            print("BLOCKED_HOLDOUT_EVIDENCE: INVALID_DISPOSITION")
        else:
            for error in evidence["errors"]:
                print(f"BLOCKED_HOLDOUT_EVIDENCE: {error}")
        return 1

    def assert_safe_read(path):
        if protected_path(path, ("FINAL_HOLDOUT", ".env", "quantumbot.db"), root):
            raise PermissionError("BLOCKED_PROTECTED_PATH: forbidden file read")
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root):
            raise PermissionError("BLOCKED_OUTSIDE_PROJECT: forbidden file read")
        return resolved

    def load_metadata(path):
        return original_load(assert_safe_read(path))

    def validate(args):
        try:
            state = legacy.load_json(legacy.HARNESS_DIR / "PROJECT_STATE.json")
        except (OSError, ValueError) as exc:
            print(f"BLOCKED_SAFETY_STATE: {type(exc).__name__}")
            return 1
        errors = validate_m0_state(state)
        if errors:
            for error in errors:
                print(f"BLOCKED_SAFETY_STATE: {error}")
            return 1
        return reject_exposed_evidence()

    def fingerprint_file(path):
        # A second check at the actual read boundary also covers gate receipts.
        # Sealed engine source hashes remain readable for historical verification.
        return original_hash(assert_safe_read(path))

    def gate(args):
        # No receipt combination can repair exposure. The old receipt proof
        # implementation is preserved in the pre-change snapshot, not reused
        # as a current authority while this workflow is inadmissible.
        return validate(args)

    legacy.load_json = load_metadata
    legacy.cmd_validate = validate
    legacy.cmd_gate = gate
    # Direct successor calls also reject before invoking historical proof code.
    legacy.cmd_verify_all = validate

    def fingerprint(args):
        # Retain protected-path denial codes without opening any contents.
        for path in args.paths:
            if legacy.is_protected_path(path):
                print(f"BLOCKED_PROTECTED_PATH: {path}")
                return 2
        return validate(args)

    legacy.cmd_fingerprint = fingerprint
    legacy.compute_file_sha256 = fingerprint_file
    return legacy


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="M0 safe read-only commands; no certification or trading authority."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    fingerprint = subparsers.add_parser("fingerprint")
    fingerprint.add_argument("paths", nargs="+")
    verify = subparsers.add_parser("verify-all")
    verify.add_argument("gate_id")
    args = parser.parse_args(argv)
    # Gate IDs are identifiers, not arbitrary filesystem paths.
    if args.command == "verify-all" and (
        not args.gate_id.startswith("GATE-")
        or not all(char.isalnum() or char in "-_." for char in args.gate_id)
        or ".." in args.gate_id
    ):
        print("BLOCKED_INVALID_GATE_ID")
        return 2
    try:
        legacy = load_safe_harness()
        # Every command checks state before file hashing or legacy verification.
        if args.command == "validate":
            return legacy.cmd_validate(args)
        state = legacy.load_json(legacy.HARNESS_DIR / "PROJECT_STATE.json")
        errors = validate_m0_state(state)
        if errors:
            for error in errors:
                print(f"BLOCKED_SAFETY_STATE: {error}")
            return 1
        evidence = review_holdout_evidence(PROJECT_ROOT)
        if evidence["status"] == "BLOCKED":
            for error in evidence["errors"]:
                print(f"BLOCKED_HOLDOUT_EVIDENCE: {error}")
            return 1
        if args.command == "fingerprint":
            return legacy.cmd_fingerprint(args)
        return legacy.cmd_verify_all(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"BLOCKED_SAFETY_COMMAND: {type(exc).__name__}: {exc}")
        return 2
