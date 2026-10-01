"""
harness.py - Deterministic Verifier & CLI Foundation for QuantumBot Pro Harness v1.
Spec: SPEC-H2-VERIFIER-CLI-001
Principle: NO EVIDENCE = NOT COMPLETED
Read-only-first, deterministic, fail-closed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Resolve project root strictly relative to this script
PROJECT_ROOT = Path(__file__).resolve().parent
HARNESS_DIR = PROJECT_ROOT / "quantumbot_harness"
SCHEMAS_DIR = HARNESS_DIR / "schemas"
SPECS_DIR = HARNESS_DIR / "specs"
TASKS_DIR = HARNESS_DIR / "tasks"
RECEIPTS_DIR = HARNESS_DIR / "receipts"
GATES_DIR = HARNESS_DIR / "gates"
STATE_DIR = HARNESS_DIR / "state"
CANDIDATES_DIR = HARNESS_DIR / "candidates"
EXECUTIONS_DIR = HARNESS_DIR / "executions"

CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
EXECUTIONS_DIR.mkdir(parents=True, exist_ok=True)

LOCK_FILE = STATE_DIR / "CERTIFICATION_LOCK.json"

def get_lock_state(lock_file_path: Optional[Path] = None) -> Dict[str, Any]:
    """Retrieves current certification lock state."""
    target = lock_file_path or LOCK_FILE
    if not target.exists():
        return {
            "lock_id": None,
            "owner": None,
            "purpose": None,
            "baseline_generation": get_current_baseline_generation(),
            "acquired_at": None,
            "expires_at": None,
            "status": "RELEASED",
            "lock_type": "COOPERATIVE_CERTIFICATION_LOCK",
            "notes": "No active certification lock."
        }
    return load_json(target)

def is_lock_active(lock_state: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Checks if a lock is currently active and unexpired.
    Returns (is_active, status_reason).
    """
    status = lock_state.get("status")
    if status != "ACTIVE":
        return False, f"Lock is {status}"

    expires_at_str = lock_state.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            now_utc = datetime.now(timezone.utc)
            if now_utc > expires_at:
                return False, f"Lock expired at {expires_at_str} (current time: {now_utc.isoformat()})"
        except Exception as exc:
            pass
    return True, "Lock is active"

def acquire_lock(
    purpose: str,
    ttl_seconds: int = 300,
    owner: Optional[str] = None,
    baseline_generation: Optional[str] = None,
    lock_file_path: Optional[Path] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Acquires the cooperative certification lock fail-closed.
    If already active and unexpired, returns (False, error_msg, current_lock).
    """
    target = lock_file_path or LOCK_FILE
    lock_state = get_lock_state(target)
    active, reason = is_lock_active(lock_state)
    if active:
        msg = f"LOCK_ALREADY_HELD: Active lock '{lock_state.get('lock_id')}' held by '{lock_state.get('owner')}' until {lock_state.get('expires_at')}. Purpose: '{lock_state.get('purpose')}'"
        return False, msg, lock_state

    now_utc = datetime.now(timezone.utc)
    expires_utc = now_utc + timedelta(seconds=ttl_seconds)
    lock_id = f"LOCK-{now_utc.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"
    bg = baseline_generation or get_current_baseline_generation()
    owner_str = owner or f"pid-{os.getpid()}@harness"

    new_lock = {
        "schema_version": "1.0.0",
        "lock_id": lock_id,
        "owner": owner_str,
        "purpose": purpose,
        "baseline_generation": bg,
        "acquired_at": now_utc.isoformat(),
        "expires_at": expires_utc.isoformat(),
        "status": "ACTIVE",
        "lock_type": "COOPERATIVE_CERTIFICATION_LOCK",
        "ttl_seconds": ttl_seconds,
        "notes": "Exclusive certification window held. Do not modify baseline-governed artifacts."
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(new_lock, f, indent=2)
    return True, f"Lock '{lock_id}' acquired successfully until {expires_utc.isoformat()}", new_lock

def release_lock(
    lock_id: Optional[str] = None,
    force: bool = False,
    lock_file_path: Optional[Path] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Releases the cooperative certification lock.
    """
    target = lock_file_path or LOCK_FILE
    lock_state = get_lock_state(target)
    current_status = lock_state.get("status")
    if current_status != "ACTIVE":
        return True, f"Lock is already in state '{current_status}'", lock_state

    current_id = lock_state.get("lock_id")
    if lock_id and lock_id != current_id and not force:
        msg = f"Lock ID mismatch: expected '{current_id}', got '{lock_id}'"
        return False, msg, lock_state

    now_utc = datetime.now(timezone.utc)
    lock_state["status"] = "RELEASED"
    lock_state["released_at"] = now_utc.isoformat()
    with open(target, "w", encoding="utf-8") as f:
        json.dump(lock_state, f, indent=2)
    return True, f"Lock '{current_id}' released successfully", lock_state

def verify_baseline_artifacts(expected_generation: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    Verifies that baseline-governed artifacts match their canonical versioned receipt hashes
    under the specified baseline generation.
    """
    bg = expected_generation or get_current_baseline_generation()
    rindex_path = RECEIPTS_DIR / "index.json"
    if not rindex_path.exists():
        return False, ["Missing receipts/index.json"]

    rindex = load_json(rindex_path)
    discrepancies = []
    checked = 0

    target_paths = ["docs/ENGINEERING_HARNESS.md", "reports/MULTIPLE_TESTING_LEDGER_V2.json"]
    for r in rindex.get("receipts", []):
        if r.get("baseline_generation") == bg and r.get("source_path") in target_paths:
            checked += 1
            src = PROJECT_ROOT / r["source_path"]
            if not src.exists():
                discrepancies.append(f"Missing baseline file: {r['source_path']}")
                continue
            act_sha, act_size = compute_file_sha256(src)
            is_append_only = r.get("classification") == "APPEND_ONLY"
            if is_append_only and act_size >= r["size_bytes"]:
                content = src.read_bytes()
                prefix_hash = hashlib.sha256(content[:r["size_bytes"]]).hexdigest()
                if prefix_hash.lower() != r["sha256"].lower():
                    discrepancies.append(
                        f"EVIDENCE_DRIFT on {r['source_path']}: baseline prefix corrupted (expected {r['sha256'][:16]}..., got {prefix_hash[:16]}...)"
                    )
            elif act_sha.lower() != r["sha256"].lower():
                discrepancies.append(
                    f"EVIDENCE_DRIFT on {r['source_path']}: expected {r['sha256'][:16]}..., got {act_sha[:16]}..."
                )
            elif act_size != r["size_bytes"]:
                discrepancies.append(
                    f"SIZE_MISMATCH on {r['source_path']}: expected {r['size_bytes']} B, got {act_size} B"
                )

    if checked < len(target_paths):
        discrepancies.append(
            f"Incomplete baseline receipts for generation '{bg}': found {checked}/{len(target_paths)} target receipts."
        )

    if discrepancies:
        return False, discrepancies
    return True, []

# Explicit list of protected / sealed paths that MUST NOT be fingerprinted or modified
PROTECTED_PATTERNS = [
    ".env",
    "quantumbot.db",
    "FINAL_HOLDOUT",
    "database/quantumbot.db",
    "database/db_manager.py",
    "main.py",
    "runner.py",
    "risk/kill_switch.py",
    "core/entry_policy.py",
    "config/settings.yaml",
    "data/raw/bybit",
    "research/crypto_quant/holdout_vault.py",
    "machine_learning/purged_cv.py",
    "reports/FASE",
    "reports/MULTIPLE_TESTING_LEDGER_V2.json",
    "docs/ENGINEERING_HARNESS.md"
]

def is_protected_path(path_str: str) -> bool:
    """Checks whether a path targets a protected, sealed, or sensitive asset."""
    norm = path_str.replace("\\", "/").strip("/")
    for pattern in PROTECTED_PATTERNS:
        p_norm = pattern.replace("\\", "/").strip("/")
        if norm == p_norm or norm.startswith(p_norm + "/") or f"/{p_norm}/" in f"/{norm}/" or p_norm in norm:
            return True
    return False

def compute_file_sha256(path: Path) -> Tuple[str, int]:
    """Computes SHA-256 and byte length of a file on disk."""
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)

def load_json(path: Path) -> Dict[str, Any]:
    """Loads a JSON file with standard UTF-8 encoding."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_current_baseline_generation() -> str:
    """Retrieves current authorized baseline generation from PROJECT_STATE.json."""
    ps_path = HARNESS_DIR / "PROJECT_STATE.json"
    if ps_path.exists():
        try:
            ps = load_json(ps_path)
            bg = ps.get("baseline_generation")
            if bg:
                return str(bg)
        except Exception:
            pass
    return "GEN-6.5a-STRATIFIED-AUDIT"

def compute_candidate_fingerprint(files: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Computes a deterministic candidate fingerprint.
    Invariant: Sorted by relative_path, no timestamps, no absolute paths, no machine metadata.
    """
    sorted_files = sorted(files, key=lambda f: f["relative_path"])
    payload_lines = [f"{f['relative_path']}:{f['sha256']}:{f['size_bytes']}" for f in sorted_files]
    payload_str = "\n".join(payload_lines) + "\n"
    fingerprint = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    return fingerprint, sorted_files

def verify_candidate_internal(candidate_id: str) -> Tuple[bool, str, Dict[str, Any], str]:
    """
    Pure read-only verification of a frozen candidate against current disk state.
    Returns: (is_valid, status_code, candidate_data, error_detail)
    """
    cand_file = CANDIDATES_DIR / f"{candidate_id}.json"
    if not cand_file.exists():
        return False, "MISSING", {}, f"Candidate file '{candidate_id}.json' not found in candidates/"

    try:
        cdata = load_json(cand_file)
    except Exception as e:
        return False, "CORRUPT", {}, f"Could not load candidate JSON: {e}"

    frozen_fp = cdata.get("candidate_fingerprint", "")
    files = cdata.get("files", [])

    missing_files = []
    changed_files = []
    current_file_records = []

    for f in files:
        rel = f.get("relative_path", "")
        p = PROJECT_ROOT / rel
        if not p.exists():
            missing_files.append(rel)
            continue
        actual_sha, actual_sz = compute_file_sha256(p)
        current_file_records.append({
            "relative_path": rel,
            "sha256": actual_sha,
            "size_bytes": actual_sz
        })
        if actual_sha.lower() != f.get("sha256", "").lower() or actual_sz != f.get("size_bytes"):
            changed_files.append(rel)

    if missing_files or changed_files:
        details = []
        if missing_files:
            details.append(f"MISSING: {', '.join(missing_files)}")
        if changed_files:
            details.append(f"CHANGED: {', '.join(changed_files)}")
        return False, "CANDIDATE_STALE", cdata, "; ".join(details)

    current_fp, _ = compute_candidate_fingerprint(current_file_records)
    if current_fp.lower() != frozen_fp.lower():
        return False, "CANDIDATE_STALE", cdata, f"Fingerprint mismatch: frozen={frozen_fp[:16]}... current={current_fp[:16]}..."

    return True, "CANDIDATE_VERIFIED", cdata, ""

def is_command_allowlisted(cmd_args: List[str]) -> bool:
    """Enforces strict allowlist for test commands executed via 'run'."""
    if not cmd_args:
        return False

    prog = cmd_args[0].lower().replace("\\", "/")
    if not (prog == "python" or prog.endswith("/python") or prog.endswith("/python.exe") or prog == "python.exe"):
        return False

    cmd_str = " ".join(cmd_args)
    for fc in [";", "&", "|", ">", "<", "`", "$"]:
        if fc in cmd_str:
            return False

    if len(cmd_args) >= 3 and cmd_args[1] == "-m" and cmd_args[2] == "unittest":
        for arg in cmd_args[3:]:
            if arg.startswith("-"):
                continue
            norm_arg = arg.replace("\\", "/")
            if "main.py" in norm_arg or "runner.py" in norm_arg or ".env" in norm_arg or "FINAL_HOLDOUT" in norm_arg:
                return False
        return True

    if len(cmd_args) >= 2:
        target = cmd_args[1].replace("\\", "/")
        if (target.startswith("tests/") or target.startswith("scratch/")) and target.endswith(".py"):
            return True

    return False

# --- SUBCOMMAND IMPLEMENTATIONS ---

def cmd_state(args: argparse.Namespace) -> int:
    """Displays project and harness state."""
    try:
        ps_path = HARNESS_DIR / "PROJECT_STATE.json"
        ps = load_json(ps_path)
    except Exception as exc:
        print(f"[BLOCKED] Could not load PROJECT_STATE.json: {exc}", file=sys.stderr)
        return 2

    print("==================================================")
    print("      QUANTUMBOT HARNESS v1 ? PROJECT STATE       ")
    print("==================================================")
    print(f"Current Certified Phase: {ps.get('current_certified_phase')}")
    print(f"Phase Status:            {ps.get('current_phase_status')}")
    print(f"Active Spec:             {ps.get('active_spec')}")
    print(f"Active Task:             {ps.get('active_task')}")
    print(f"Last Closed Task:        {ps.get('last_closed_task')}")
    print(f"Last Receipt ID:         {ps.get('last_receipt_id')}")
    print(f"Last Gate ID:            {ps.get('last_gate_id')}")
    print(f"Development Dataset:     {ps.get('development_dataset_id')}")
    print(f"Dataset Fingerprint:     {ps.get('development_dataset_fingerprint')}")
    print(f"Final Holdout Status:    {ps.get('final_holdout_status')}")
    print(f"Holdout Access Count:    {ps.get('final_holdout_access_count')}")
    print(f"Live Trading Status:     {ps.get('live_trading_status')} (allow_live_trading={ps.get('allow_live_trading')})")
    print(f"Updated At:              {ps.get('updated_at')}")
    print("==================================================")
    return 0

def cmd_validate(args: argparse.Namespace) -> int:
    """Validates JSON schemas, instances, and cross-references."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("[BLOCKED] jsonschema package is required but not installed.", file=sys.stderr)
        return 2

    errors: List[str] = []

    # 1. Meta-validate schemas
    schema_names = [
        "spec.schema.json",
        "spec_v2.schema.json",
        "task.schema.json",
        "receipt.schema.json",
        "gate.schema.json",
        "candidate.schema.json",
        "execution.schema.json"
    ]
    schemas: Dict[str, Dict[str, Any]] = {}
    print("--- 1. SCHEMA META-VALIDATION (Draft 2020-12) ---")
    for sname in schema_names:
        spath = SCHEMAS_DIR / sname
        if not spath.exists():
            continue
        try:
            sdata = load_json(spath)
            Draft202012Validator.check_schema(sdata)
            schemas[sname] = sdata
            print(f"  [PASS] {sname}")
        except Exception as exc:
            msg = f"Schema meta-validation failed for {sname}: {exc}"
            print(f"  [FAIL] {msg}")
            errors.append(msg)

    if errors:
        print("\n[VALIDATION FAILED] Schema meta-validation errors detected.")
        return 1

    # 2. Validate instances
    print("\n--- 2. INSTANCE VALIDATION ---")
    # Tasks
    try:
        tledger = load_json(TASKS_DIR / "TASK_LEDGER.json")
        tvalidator = Draft202012Validator(schemas["task.schema.json"])
        for task in tledger.get("tasks", []):
            task_errs = list(tvalidator.iter_errors(task))
            if task_errs:
                for err in task_errs:
                    msg = f"Task {task.get('task_id')} schema error at {err.json_path}: {err.message}"
                    print(f"  [FAIL] {msg}")
                    errors.append(msg)
            else:
                print(f"  [PASS] Task {task.get('task_id')} ({task.get('status')})")
    except Exception as exc:
        msg = f"Failed to load or validate TASK_LEDGER.json: {exc}"
        print(f"  [FAIL] {msg}")
        errors.append(msg)

    # Receipts
    try:
        rindex = load_json(RECEIPTS_DIR / "index.json")
        rvalidator = Draft202012Validator(schemas["receipt.schema.json"])
        for receipt in rindex.get("receipts", []):
            r_errs = list(rvalidator.iter_errors(receipt))
            if r_errs:
                for err in r_errs:
                    msg = f"Receipt {receipt.get('receipt_id')} schema error at {err.json_path}: {err.message}"
                    print(f"  [FAIL] {msg}")
                    errors.append(msg)
            else:
                print(f"  [PASS] Receipt {receipt.get('receipt_id')}")
    except Exception as exc:
        msg = f"Failed to load or validate receipts/index.json: {exc}"
        print(f"  [FAIL] {msg}")
        errors.append(msg)

    # Gates
    try:
        gvalidator = Draft202012Validator(schemas["gate.schema.json"])
        for gpath in sorted(GATES_DIR.glob("*.json")):
            gdata = load_json(gpath)
            g_errs = list(gvalidator.iter_errors(gdata))
            if g_errs:
                for err in g_errs:
                    msg = f"Gate {gpath.name} schema error at {err.json_path}: {err.message}"
                    print(f"  [FAIL] {msg}")
                    errors.append(msg)
            else:
                print(f"  [PASS] Gate {gpath.name}")
    except Exception as exc:
        msg = f"Failed to validate gates: {exc}"
        print(f"  [FAIL] {msg}")
        errors.append(msg)

    # Specs
    try:
        svalidator_v1 = Draft202012Validator(schemas["spec.schema.json"])
        svalidator_v2 = Draft202012Validator(schemas["spec_v2.schema.json"]) if "spec_v2.schema.json" in schemas else None
        spec_files = list(SPECS_DIR.glob("*.json"))
        if not spec_files:
            print("  [INFO] No JSON spec instances in specs/ (SPEC_INSTANCE = MISSING)")
        for sp in spec_files:
            s_data = load_json(sp)
            
            # Schema dispatch:
            # Both V1 and V2 specs use schema_version 1.0.0. 
            # We use the exact governed spec_id prefix as the discriminator.
            spec_id = s_data.get("spec_id", "")
            schema_version = s_data.get("schema_version")
            is_v2 = spec_id.startswith("SPEC-HARNESS-V2-")
            
            if schema_version != "1.0.0":
                s_errs = [type("Err", (object,), {"json_path": "schema_version", "message": f"Unsupported schema_version: {schema_version}"})()]
            elif is_v2:
                if svalidator_v2:
                    s_errs = list(svalidator_v2.iter_errors(s_data))
                else:
                    s_errs = [type("Err", (object,), {"json_path": "$", "message": "spec_v2 schema is not loaded"})()]
            else:
                s_errs = list(svalidator_v1.iter_errors(s_data))

            if s_errs:
                for err in s_errs:
                    msg = f"Spec {sp.name} schema error at {err.json_path}: {err.message}"
                    print(f"  [FAIL] {msg}")
                    errors.append(msg)
            else:
                print(f"  [PASS] Spec {sp.name}")
    except Exception as exc:
        msg = f"Failed to validate specs: {exc}"
        print(f"  [FAIL] {msg}")
        errors.append(msg)

    # Candidates
    if "candidate.schema.json" in schemas:
        try:
            cvalidator = Draft202012Validator(schemas["candidate.schema.json"])
            cand_files = list(CANDIDATES_DIR.glob("*.json"))
            
            # M6: Load KNOWN_FAILURES.json to skip legacy files
            known_failures = {}
            kf_path = HARNESS_DIR / "docs" / "KNOWN_FAILURES.json"
            if kf_path.exists():
                known_failures = load_json(kf_path).get("classifications", {})

            for cp in sorted(cand_files):
                if cp.name in known_failures:
                    print(f"  [SKIP] Candidate {cp.name} ({known_failures[cp.name].get('reason')})")
                    continue
                    
                c_data = load_json(cp)
                c_errs = list(cvalidator.iter_errors(c_data))
                if c_errs:
                    for err in c_errs:
                        msg = f"Candidate {cp.name} schema error at {err.json_path}: {err.message}"
                        print(f"  [FAIL] {msg}")
                        errors.append(msg)
                else:
                    print(f"  [PASS] Candidate {cp.name} ({c_data.get('status')}, {c_data.get('verification_status')})")
        except Exception as exc:
            msg = f"Failed to validate candidates: {exc}"
            print(f"  [FAIL] {msg}")
            errors.append(msg)

    # Executions
    if "execution.schema.json" in schemas:
        try:
            evalidator = Draft202012Validator(schemas["execution.schema.json"])
            exec_files = list(EXECUTIONS_DIR.glob("*.json"))
            for ep in sorted(exec_files):
                e_data = load_json(ep)
                e_errs = list(evalidator.iter_errors(e_data))
                if e_errs:
                    for err in e_errs:
                        msg = f"Execution {ep.name} schema error at {err.json_path}: {err.message}"
                        print(f"  [FAIL] {msg}")
                        errors.append(msg)
                else:
                    print(f"  [PASS] Execution {ep.name} ({e_data.get('result')}, code {e_data.get('exit_code')})")
        except Exception as exc:
            msg = f"Failed to validate executions: {exc}"
            print(f"  [FAIL] {msg}")
            errors.append(msg)

    # 3. Cross-reference validation
    print("\n--- 3. CROSS-REFERENCE VALIDATION ---")
    try:
        ps = load_json(HARNESS_DIR / "PROJECT_STATE.json")
        tledger = load_json(TASKS_DIR / "TASK_LEDGER.json")
        rindex = load_json(RECEIPTS_DIR / "index.json")

        task_ids = {t["task_id"] for t in tledger.get("tasks", [])}
        receipt_ids = {r["receipt_id"] for r in rindex.get("receipts", [])}
        spec_ids = {p.stem for p in SPECS_DIR.glob("*.json")}

        # PROJECT_STATE references
        lct = ps.get("last_closed_task")
        if lct and lct not in task_ids:
            msg = f"PROJECT_STATE.last_closed_task '{lct}' not found in TASK_LEDGER"
            print(f"  [FAIL] {msg}")
            errors.append(msg)
        else:
            print(f"  [PASS] last_closed_task -> '{lct}' found")

        lri = ps.get("last_receipt_id")
        if lri and lri not in receipt_ids:
            msg = f"PROJECT_STATE.last_receipt_id '{lri}' not found in receipts/index.json"
            print(f"  [FAIL] {msg}")
            errors.append(msg)
        else:
            print(f"  [PASS] last_receipt_id -> '{lri}' found")

        lgi = ps.get("last_gate_id")
        if lgi:
            gpath = GATES_DIR / f"{lgi}.json"
            if not gpath.exists():
                msg = f"PROJECT_STATE.last_gate_id '{lgi}' file does not exist ({gpath})"
                print(f"  [FAIL] {msg}")
                errors.append(msg)
            else:
                print(f"  [PASS] last_gate_id -> '{lgi}.json' exists")

        # Task references
        for t in tledger.get("tasks", []):
            tid = t["task_id"]
            for rid in t.get("receipt_ids", []):
                if rid not in receipt_ids:
                    msg = f"Task {tid} references missing receipt '{rid}'"
                    print(f"  [FAIL] {msg}")
                    errors.append(msg)
            gid = t.get("gate_id")
            if gid:
                if not (GATES_DIR / f"{gid}.json").exists():
                    msg = f"Task {tid} references missing gate '{gid}.json'"
                    print(f"  [FAIL] {msg}")
                    errors.append(msg)
            sid = t.get("spec_id")
            if sid and sid not in spec_ids:
                # If spec is approved in text or missing json
                pass

        # Receipt references
        for r in rindex.get("receipts", []):
            rid = r["receipt_id"]
            rt = r.get("related_task")
            if rt and rt not in task_ids:
                msg = f"Receipt {rid} references orphan task '{rt}'"
                print(f"  [FAIL] {msg}")
                errors.append(msg)
            rs = r.get("related_spec")
            if rs and rs not in spec_ids:
                msg = f"Receipt {rid} references missing spec '{rs}'"
                print(f"  [FAIL] {msg}")
                errors.append(msg)

        if not errors:
            print("  [PASS] All cross-references resolved successfully")

    except Exception as exc:
        msg = f"Cross-reference validation failed: {exc}"
        print(f"  [FAIL] {msg}")
        errors.append(msg)

    if errors:
        print(f"\n[VALIDATION FAILED] Total errors: {len(errors)}")
        return 1

    print("\n[VALIDATION SUCCESS] All schemas, instances, and cross-references passed.")
    return 0

def cmd_verify(args: argparse.Namespace) -> int:
    """Verifies a single receipt against its source file on disk."""
    receipt_id = args.receipt_id
    rindex_path = RECEIPTS_DIR / "index.json"

    try:
        rindex = load_json(rindex_path)
    except Exception as exc:
        print(f"[BLOCKED] Could not load receipts index: {exc}", file=sys.stderr)
        return 2

    # Find receipt
    matched = [r for r in rindex.get("receipts", []) if r.get("receipt_id") == receipt_id]
    if not matched:
        print(f"MISSING: Receipt '{receipt_id}' not found in receipts/index.json")
        return 1

    receipt = matched[0]
    source_path_str = receipt.get("source_path", "")
    expected_hash = receipt.get("sha256", "")

    # Security check on source path
    if is_protected_path(source_path_str) and not source_path_str.startswith("reports/") and source_path_str != "docs/ENGINEERING_HARNESS.md" and source_path_str != "database/kill_switch_state.json":
        print(f"BLOCKED: Source path '{source_path_str}' is protected from direct verification")
        return 2

    source_path = PROJECT_ROOT / source_path_str
    if not source_path.exists():
        print(f"SOURCE_FILE_MISSING: File '{source_path_str}' does not exist on disk")
        return 1

    actual_hash, actual_size = compute_file_sha256(source_path)
    if actual_hash.lower() == expected_hash.lower():
        print(f"VERIFIED: Receipt '{receipt_id}'")
        print(f"  Source Path:   {source_path_str}")
        print(f"  SHA-256:       {actual_hash}")
        print(f"  Size (Bytes):  {actual_size}")
        print(f"  Status:        VERIFIED")
        return 0
    else:
        print(f"EVIDENCE_DRIFT: Receipt '{receipt_id}' hash mismatch!")
        print(f"  Source Path:   {source_path_str}")
        print(f"  Expected Hash: {expected_hash}")
        print(f"  Actual Hash:   {actual_hash}")
        print(f"  Status:        MISMATCH / EVIDENCE_DRIFT")
        return 1

def cmd_task_list(args: argparse.Namespace) -> int:
    """Lists tasks recorded in TASK_LEDGER.json."""
    try:
        tledger = load_json(TASKS_DIR / "TASK_LEDGER.json")
    except Exception as exc:
        print(f"[BLOCKED] Could not load TASK_LEDGER.json: {exc}", file=sys.stderr)
        return 2

    tasks = tledger.get("tasks", [])
    print("=========================================================================================")
    print(f"{'TASK ID':<15} {'SPEC ID':<28} {'STATUS':<14} {'GATE ID':<25}")
    print("-----------------------------------------------------------------------------------------")
    for t in tasks:
        tid = t.get("task_id", "")
        sid = t.get("spec_id", "")
        st = t.get("status", "")
        gid = t.get("gate_id") or "NONE"
        print(f"{tid:<15} {sid:<28} {st:<14} {gid:<25}")
    print("=========================================================================================")
    return 0

def cmd_gate(args: argparse.Namespace) -> int:
    """Verifies a gate by checking all underlying evidence and receipts."""
    gate_id = args.gate_id
    gate_path = GATES_DIR / f"{gate_id}.json"
    if not gate_path.exists():
        print(f"[FAIL] GATE_FILE_MISSING: Gate file '{gate_id}.json' not found in gates/")
        return 1

    try:
        gdata = load_json(gate_path)
    except Exception as exc:
        print(f"[BLOCKED] Could not read gate file: {exc}", file=sys.stderr)
        return 2

    print(f"=== EVALUATING GATE: {gate_id} ===")
    declared_status = gdata.get("status")
    print(f"Declared Status: {declared_status}")

    failures: List[str] = []

    # 1. Verify required receipts
    rindex_path = RECEIPTS_DIR / "index.json"
    rindex = load_json(rindex_path)
    receipt_map = {r["receipt_id"]: r for r in rindex.get("receipts", [])}

    req_receipts = gdata.get("required_receipts", [])
    print(f"\nChecking Required Receipts ({len(req_receipts)}):")
    for rid in req_receipts:
        if rid not in receipt_map:
            failures.append(f"Required receipt '{rid}' missing from receipts/index.json")
            print(f"  [FAIL] Receipt '{rid}': NOT FOUND in index")
            continue
        r_entry = receipt_map[rid]
        source_str = r_entry.get("source_path", "")
        source_p = PROJECT_ROOT / source_str
        if not source_p.exists():
            failures.append(f"Source file '{source_str}' for receipt '{rid}' does not exist on disk")
            print(f"  [FAIL] Receipt '{rid}': source file missing ({source_str})")
            continue
        if r_entry.get("type") == "RUNTIME_STATE":
            try:
                load_json(source_p)
                print(f"  [PASS] Receipt '{rid}': verified dynamic runtime state on {source_str}")
            except Exception as exc:
                failures.append(f"Invalid runtime state JSON in '{source_str}': {exc}")
                print(f"  [FAIL] Receipt '{rid}': invalid runtime state ({exc})")
            continue

        actual_h, actual_s = compute_file_sha256(source_p)
        expected_h = r_entry.get("sha256", "")
        if actual_h.lower() != expected_h.lower():
            failures.append(f"EVIDENCE_DRIFT on receipt '{rid}': expected {expected_h[:16]}... got {actual_h[:16]}...")
            print(f"  [FAIL] Receipt '{rid}': EVIDENCE_DRIFT detected on {source_str}")
        else:
            print(f"  [PASS] Receipt '{rid}': verified on disk ({actual_h[:16]}...)")

    # 2. Check Candidate if gate requires candidate
    req_cid = gdata.get("required_candidate_id")
    if req_cid:
        print(f"\nChecking Required Candidate '{req_cid}':")
        ok, status, cdata, err = verify_candidate_internal(req_cid)
        if not ok:
            failures.append(f"Candidate '{req_cid}' verification failed: {err}")
            print(f"  [FAIL] Candidate '{req_cid}': {status} ({err})")
        else:
            req_cfp = gdata.get("required_candidate_fingerprint")
            if req_cfp and req_cfp.lower() != cdata.get("candidate_fingerprint", "").lower():
                failures.append(f"Candidate '{req_cid}' fingerprint mismatch: expected {req_cfp}, got {cdata.get('candidate_fingerprint')}")
                print(f"  [FAIL] Candidate '{req_cid}': fingerprint mismatch")
            else:
                print(f"  [PASS] Candidate '{req_cid}': verified ({cdata.get('candidate_fingerprint')[:16]}...)")

    # 3. Check Baseline Generation binding
    req_bg = gdata.get("required_baseline_generation")
    if req_bg:
        print(f"\nChecking Required Baseline Generation '{req_bg}':")
        cur_bg = get_current_baseline_generation()
        if req_bg != cur_bg:
            failures.append(f"Baseline generation mismatch: required '{req_bg}', current '{cur_bg}'")
            print(f"  [FAIL] Baseline generation mismatch: {req_bg} != {cur_bg} (BASELINE_GENERATION_MISMATCH)")
        else:
            print(f"  [PASS] Baseline generation '{req_bg}': matched")

    # 4. Check Execution Receipts
    req_execs = gdata.get("required_execution_receipts", [])
    if req_execs:
        print(f"\nChecking Required Execution Receipts ({len(req_execs)}):")
        for eid in req_execs:
            efile = EXECUTIONS_DIR / f"{eid}.json"
            if not efile.exists():
                failures.append(f"Required execution receipt '{eid}' missing from disk")
                print(f"  [FAIL] Execution receipt '{eid}': NOT FOUND")
                continue
            try:
                edata = load_json(efile)
                if edata.get("result") != "PASS":
                    failures.append(f"Execution receipt '{eid}' status is '{edata.get('result')}' (not PASS)")
                    print(f"  [FAIL] Execution receipt '{eid}': status != PASS")
                elif edata.get("exit_code") != 0:
                    failures.append(f"Execution receipt '{eid}' exit_code is {edata.get('exit_code')} (expected 0)")
                    print(f"  [FAIL] Execution receipt '{eid}': exit_code != 0")
                else:
                    print(f"  [PASS] Execution receipt '{eid}': verified PASS")
            except Exception as exc:
                failures.append(f"Could not load execution receipt '{eid}': {exc}")
                print(f"  [FAIL] Execution receipt '{eid}': {exc}")

    # 5. Check Criteria
    print(f"\nChecking Criteria ({len(gdata.get('criteria', []))}):")
    for crit in gdata.get("criteria", []):
        cid = crit.get("criterion_id")
        desc = crit.get("description")
        req = crit.get("required", True)
        sat = crit.get("satisfied", False)
        if req and not sat:
            failures.append(f"Criterion '{cid}' not satisfied: {desc}")
            print(f"  [FAIL] Criterion {cid}: NOT SATISFIED ({desc})")
        else:
            print(f"  [PASS] Criterion {cid}: satisfied")

    # 3. Check Tests
    print(f"\nChecking Tests ({len(gdata.get('tests', []))}):")
    for test in gdata.get("tests", []):
        tid = test.get("test_id")
        tstat = test.get("status")
        if tstat != "PASS":
            failures.append(f"Test '{tid}' has status '{tstat}' (expected PASS)")
            print(f"  [FAIL] Test {tid}: status={tstat}")
        else:
            print(f"  [PASS] Test {tid}: PASS")

    # 4. Check failure reasons in gate
    f_reasons = gdata.get("failure_reasons", [])
    if f_reasons:
        failures.extend(f_reasons)
        print(f"  [FAIL] Gate has non-empty failure_reasons: {f_reasons}")

    # Final verdict
    print("\n--- GATE VERIFICATION SUMMARY ---")
    if failures:
        print(f"[EVIDENCE_DRIFT] Gate '{gate_id}' verification FAILED with {len(failures)} discrepancy(ies):")
        for f in failures:
            print(f"  - {f}")
        return 1

    if declared_status != "PASS":
        print(f"[GATE_INCOMPLETE] Gate evidence is consistent, but gate declared status is '{declared_status}' (not PASS).")
        return 1

    print(f"[GATE_VERIFIED: PASS] All required receipts, criteria, tests, and evidence verified with 0 drift.")
    return 0

def cmd_fingerprint(args: argparse.Namespace) -> int:
    """Computes a deterministic candidate fingerprint for given files/directories."""
    raw_paths = args.paths
    if not raw_paths:
        print("[FAIL] No paths provided for candidate fingerprinting.", file=sys.stderr)
        return 1

    # Security check: any protected path causes immediate BLOCKED response
    for p_str in raw_paths:
        if is_protected_path(p_str):
            print(f"BLOCKED_PROTECTED_PATH: Path '{p_str}' is protected/sealed and cannot be fingerprinted.")
            return 2

    # Collect and normalize all target files
    collected_files: Set[Path] = set()
    for p_str in raw_paths:
        p = (PROJECT_ROOT / p_str).resolve()
        if not p.exists():
            print(f"[FAIL] Path does not exist: {p_str}", file=sys.stderr)
            return 1
        if p.is_file():
            # Check individual resolved file
            rel_str = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
            if is_protected_path(rel_str):
                print(f"BLOCKED_PROTECTED_PATH: File '{rel_str}' is protected/sealed.")
                return 2
            collected_files.add(p)
        elif p.is_dir():
            for child in p.rglob("*"):
                if child.is_file():
                    rel_str = str(child.relative_to(PROJECT_ROOT)).replace("\\", "/")
                    if is_protected_path(rel_str):
                        print(f"BLOCKED_PROTECTED_PATH: File '{rel_str}' is protected/sealed.")
                        return 2
                    collected_files.add(child)

    if not collected_files:
        print("[FAIL] No files found in specified paths.", file=sys.stderr)
        return 1

    # Deterministic sorting of normalized relative paths
    file_records: List[Tuple[str, str, int]] = []
    for fpath in collected_files:
        rel_path = str(fpath.relative_to(PROJECT_ROOT)).replace("\\", "/")
        f_hash, f_size = compute_file_sha256(fpath)
        file_records.append((rel_path, f_hash, f_size))

    file_records.sort(key=lambda item: item[0])

    print(f"{'RELATIVE PATH':<65} {'SHA-256':<64} {'SIZE (BYTES)'}")
    print("-" * 145)
    canonical_lines: List[str] = []
    for rel_path, f_hash, f_size in file_records:
        print(f"{rel_path:<65} {f_hash:<64} {f_size}")
        canonical_lines.append(f"{rel_path}:{f_hash}:{f_size}")

    # Deterministic candidate fingerprint
    canonical_payload = "\n".join(canonical_lines).encode("utf-8")
    candidate_fp = hashlib.sha256(canonical_payload).hexdigest()

    print("-" * 145)
    print(f"CANDIDATE_FINGERPRINT: {candidate_fp}")
    print(f"Total Files Covered:   {len(file_records)}")
    return 0

def cmd_freeze(args: argparse.Namespace) -> int:
    """Freezes a set of files into a candidate snapshot with a deterministic fingerprint."""
    candidate_id = args.candidate_id
    if not candidate_id.startswith("CANDIDATE-"):
        print(f"[FAIL] Invalid candidate_id '{candidate_id}'. Must start with 'CANDIDATE-'", file=sys.stderr)
        return 1

    cand_file = CANDIDATES_DIR / f"{candidate_id}.json"
    if cand_file.exists():
        print(f"BLOCKED: Candidate '{candidate_id}' already exists and is immutable (cannot overwrite).")
        return 1

    raw_paths = args.paths
    if not raw_paths:
        print("[FAIL] No paths specified to freeze.", file=sys.stderr)
        return 1

    # Security check on input paths
    for p_str in raw_paths:
        if is_protected_path(p_str) or any(sensitive in p_str for sensitive in [".env", "FINAL_HOLDOUT", "quantumbot.db"]):
            print(f"BLOCKED_PROTECTED_PATH: Path '{p_str}' is a protected asset and cannot be part of a candidate.")
            return 2

    # Collect and normalize files
    file_records: List[Dict[str, Any]] = []
    seen_paths: Set[str] = set()

    for raw_p in raw_paths:
        p = (PROJECT_ROOT / raw_p).resolve()
        if not p.exists():
            p = Path(raw_p).resolve()
            if not p.exists():
                print(f"[FAIL] Path not found: {raw_p}", file=sys.stderr)
                return 1

        if is_protected_path(str(p)) or any(s in str(p) for s in [".env", "FINAL_HOLDOUT", "quantumbot.db"]):
            print(f"BLOCKED_PROTECTED_PATH: Path '{raw_p}' targets a protected asset.")
            return 2

        if p.is_file():
            try:
                rel = p.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                rel = p.name
            if is_protected_path(rel) or any(s in rel for s in [".env", "FINAL_HOLDOUT", "quantumbot.db"]):
                print(f"BLOCKED_PROTECTED_PATH: File '{rel}' is protected.")
                return 2
            if rel not in seen_paths:
                seen_paths.add(rel)
                sha, sz = compute_file_sha256(p)
                file_records.append({"relative_path": rel, "sha256": sha, "size_bytes": sz})

        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    try:
                        rel = child.relative_to(PROJECT_ROOT).as_posix()
                    except ValueError:
                        rel = child.name
                    if is_protected_path(rel) or any(s in rel for s in [".env", "FINAL_HOLDOUT", "quantumbot.db"]):
                        print(f"BLOCKED_PROTECTED_PATH: Directory contains protected file '{rel}'.")
                        return 2
                    if any(ign in rel for ign in ["__pycache__", ".git", ".pytest_cache", ".venv"]):
                        continue
                    if rel not in seen_paths:
                        seen_paths.add(rel)
                        sha, sz = compute_file_sha256(child)
                        file_records.append({"relative_path": rel, "sha256": sha, "size_bytes": sz})

    if not file_records:
        print(f"[FAIL] No eligible files found to freeze for candidate '{candidate_id}'", file=sys.stderr)
        return 1

    candidate_fp, sorted_files = compute_candidate_fingerprint(file_records)
    current_baseline = get_current_baseline_generation()

    ps_path = HARNESS_DIR / "PROJECT_STATE.json"
    active_spec = "SPEC-H3-FROZEN-CANDIDATE-001"
    active_task = "H3-TASK-001"
    if ps_path.exists():
        try:
            ps = load_json(ps_path)
            active_spec = ps.get("active_spec", active_spec) or active_spec
            active_task = ps.get("active_task", active_task) or active_task
        except Exception:
            pass

    spec_id = getattr(args, "spec_id", None) or active_spec

    candidate_data = {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "spec_id": spec_id,
        "task_ids": [active_task],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN",
        "files": sorted_files,
        "candidate_fingerprint": candidate_fp,
        "baseline_generation": current_baseline,
        "verification_status": "VERIFIED"
    }

    try:
        from jsonschema import Draft202012Validator
        cs_path = SCHEMAS_DIR / "candidate.schema.json"
        if cs_path.exists():
            cs = load_json(cs_path)
            val = Draft202012Validator(cs)
            val.validate(candidate_data)
    except Exception as exc:
        print(f"[FAIL] Candidate schema validation error: {exc}", file=sys.stderr)
        return 1

    cand_file.write_text(json.dumps(candidate_data, indent=2), encoding="utf-8")
    print(f"CANDIDATE_FROZEN: Candidate '{candidate_id}' successfully frozen.")
    print(f"  Fingerprint:         {candidate_fp}")
    print(f"  Baseline Generation: {current_baseline}")
    print(f"  Files Count:         {len(sorted_files)}")
    print(f"  Status:              FROZEN")
    return 0

def cmd_candidate_verify(args: argparse.Namespace) -> int:
    """Verifies a frozen candidate against current disk state."""
    candidate_id = args.candidate_id
    ok, status, cdata, err = verify_candidate_internal(candidate_id)
    if ok:
        fp = cdata.get("candidate_fingerprint")
        print(f"CANDIDATE_VERIFIED: Candidate '{candidate_id}' matches frozen fingerprint ({fp}).")
        return 0
    else:
        if status == "MISSING":
            print(f"MISSING: {err}")
            return 1
        else:
            print(f"CANDIDATE_STALE: Candidate '{candidate_id}' verification failed ({status})!")
            print(f"  Details: {err}")
            return 1

def cmd_run(args: argparse.Namespace) -> int:
    """Executes an approved test command against a verified frozen candidate."""
    candidate_id = args.candidate_id
    exec_cmd = args.exec_cmd
    if exec_cmd and exec_cmd[0] == "--":
        exec_cmd = exec_cmd[1:]

    if not exec_cmd:
        print("[FAIL] No command specified. Syntax: python harness.py run <candidate_id> -- <command...>", file=sys.stderr)
        return 1

    cmd_str = " ".join(exec_cmd)

    if not is_command_allowlisted(exec_cmd):
        print(f"COMMAND_NOT_ALLOWED: Command '{cmd_str}' is not in approved harness test allowlist.")
        return 2

    # 1. Pre-execution candidate verification
    ok, status, cdata, err = verify_candidate_internal(candidate_id)
    if not ok:
        print(f"BLOCKED: Candidate '{candidate_id}' is not in verified state ({status}): {err}")
        return 1

    candidate_fp = cdata.get("candidate_fingerprint")
    baseline_gen = cdata.get("baseline_generation")
    current_baseline = get_current_baseline_generation()

    if baseline_gen != current_baseline:
        print(f"BASELINE_GENERATION_MISMATCH: Candidate baseline '{baseline_gen}' != current authorized baseline '{current_baseline}'")
        return 1

    print(f"=== RUNNING APPROVED COMMAND AGAINST CANDIDATE {candidate_id} ===")
    print(f"Command:             {cmd_str}")
    print(f"Candidate FP:        {candidate_fp}")
    print(f"Baseline Generation: {baseline_gen}")

    t_start = time.time()
    started_at = datetime.now(timezone.utc).isoformat()

    proc = subprocess.run(
        exec_cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    t_end = time.time()
    finished_at = datetime.now(timezone.utc).isoformat()
    duration = round(t_end - t_start, 4)

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    stdout_sha = hashlib.sha256(proc.stdout.encode("utf-8")).hexdigest()
    stderr_sha = hashlib.sha256(proc.stderr.encode("utf-8")).hexdigest()

    # 2. Post-execution candidate verification
    ok_post, status_post, _, err_post = verify_candidate_internal(candidate_id)
    if not ok_post:
        print(f"EXECUTION_INVALIDATED: Candidate '{candidate_id}' was mutated during execution! ({status_post}: {err_post})")
        result = "FAIL"
        exit_code = proc.returncode if proc.returncode != 0 else 1
    else:
        result = "PASS" if proc.returncode == 0 else "FAIL"
        exit_code = proc.returncode

    # Parse test counts
    combined_out = proc.stderr + proc.stdout
    m_ran = re.search(r"Ran (\d+) tests? in", combined_out)
    if m_ran:
        tests_total = int(m_ran.group(1))
        if "OK" in combined_out and proc.returncode == 0:
            tests_passed = tests_total
            tests_failed = 0
        else:
            m_fail = re.search(r"FAILED \((?:failures=(\d+))?(?:, )?(?:errors=(\d+))?\)", combined_out)
            if m_fail:
                f_cnt = int(m_fail.group(1) or 0)
                e_cnt = int(m_fail.group(2) or 0)
                tests_failed = f_cnt + e_cnt
                tests_passed = max(0, tests_total - tests_failed)
            else:
                tests_failed = 1
                tests_passed = max(0, tests_total - 1)
    else:
        if proc.returncode == 0:
            tests_total = 1
            tests_passed = 1
            tests_failed = 0
        else:
            tests_total = 1
            tests_passed = 0
            tests_failed = 1

    # Generate sequential execution_id
    existing_execs = list(EXECUTIONS_DIR.glob(f"EXEC-{candidate_id}-*.json"))
    seq_num = len(existing_execs) + 1
    execution_id = f"EXEC-{candidate_id}-{seq_num:03d}"

    fp_payload = f"{execution_id}:{candidate_id}:{candidate_fp}:{baseline_gen}:{cmd_str}:{exit_code}:{stdout_sha}:{stderr_sha}"
    receipt_fp = hashlib.sha256(fp_payload.encode("utf-8")).hexdigest()

    exec_data = {
        "schema_version": "1.0.0",
        "execution_id": execution_id,
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate_fp,
        "baseline_generation": baseline_gen,
        "command": cmd_str,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "exit_code": exit_code,
        "result": result,
        "tests_total": tests_total,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "stdout_sha256": stdout_sha,
        "stderr_sha256": stderr_sha,
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": sys.platform
        },
        "execution_receipt_fingerprint": receipt_fp,
        "notes": f"Executed against candidate {candidate_id} under baseline {baseline_gen}."
    }

    try:
        from jsonschema import Draft202012Validator
        es_path = SCHEMAS_DIR / "execution.schema.json"
        if es_path.exists():
            es = load_json(es_path)
            val = Draft202012Validator(es)
            val.validate(exec_data)
    except Exception as exc:
        print(f"[FAIL] Execution receipt schema error: {exc}", file=sys.stderr)
        return 1

    exec_file = EXECUTIONS_DIR / f"{execution_id}.json"
    exec_file.write_text(json.dumps(exec_data, indent=2), encoding="utf-8")

    print("-" * 60)
    print(f"EXECUTION RECEIPT CREATED: {execution_id}")
    print(f"  Result:              {result} (exit code: {exit_code})")
    print(f"  Candidate:           {candidate_id} ({candidate_fp[:16]}...)")
    print(f"  Receipt Fingerprint: {receipt_fp}")
    print(f"  Receipt File:        {exec_file.relative_to(PROJECT_ROOT)}")

    return 0 if result == "PASS" else 1

def cmd_verify_all(args: argparse.Namespace) -> int:
    """Independently reconstructs all validations, receipts, candidates, and gates from scratch."""
    gate_id = args.gate_id
    gate_path = GATES_DIR / f"{gate_id}.json"
    if not gate_path.exists():
        print(f"[BLOCKED] Gate file '{gate_id}.json' not found in gates/")
        return 1

    print(f"=== VERIFY-ALL: INDEPENDENT COMPLETE PROOF RECONSTRUCTION FOR {gate_id} ===")

    # 1. Full schema validation
    print("\n[STEP 1/5] Schema Meta-Validation & Instance Validation...")
    val_res = cmd_validate(argparse.Namespace())
    if val_res != 0:
        print("[VERIFY-ALL: VERIFIED_FAIL] Schema validation failed.")
        return 1

    # 2. Gate evaluation
    print("\n[STEP 2/5] Gate Evidence Evaluation...")
    g_res = cmd_gate(argparse.Namespace(gate_id=gate_id))
    if g_res != 0:
        print(f"[VERIFY-ALL: VERIFIED_FAIL] Gate '{gate_id}' evaluation failed.")
        return 1

    gdata = load_json(gate_path)
    current_baseline = get_current_baseline_generation()

    # 3. Baseline generation check
    print("\n[STEP 3/5] Baseline Generation Binding...")
    req_bg = gdata.get("required_baseline_generation")
    if req_bg and req_bg != current_baseline:
        print(f"[VERIFY-ALL: BASELINE_GENERATION_MISMATCH] Gate required baseline '{req_bg}' != current authorized '{current_baseline}'")
        return 1
    print(f"  [PASS] Baseline generation bound to '{current_baseline}'")

    # 4. Candidate verification
    print("\n[STEP 4/5] Candidate Independent Verification...")
    req_cid = gdata.get("required_candidate_id")
    if req_cid:
        ok, status, cdata, err = verify_candidate_internal(req_cid)
        if not ok:
            if status == "CANDIDATE_STALE":
                print(f"[VERIFY-ALL: CANDIDATE_STALE] Candidate '{req_cid}' is stale: {err}")
            else:
                print(f"[VERIFY-ALL: VERIFIED_FAIL] Candidate '{req_cid}': {err}")
            return 1

        cand_bg = cdata.get("baseline_generation")
        if cand_bg != current_baseline:
            print(f"[VERIFY-ALL: BASELINE_GENERATION_MISMATCH] Candidate baseline '{cand_bg}' != current '{current_baseline}'")
            return 1

        req_cfp = gdata.get("required_candidate_fingerprint")
        if req_cfp and req_cfp.lower() != cdata.get("candidate_fingerprint", "").lower():
            print(f"[VERIFY-ALL: CANDIDATE_STALE] Gate candidate fingerprint mismatch!")
            return 1
        print(f"  [PASS] Candidate '{req_cid}' verified with current fingerprint ({cdata.get('candidate_fingerprint')[:16]}...)")

    # 5. Execution receipt verification
    print("\n[STEP 5/5] Execution Receipts Binding...")
    req_execs = gdata.get("required_execution_receipts", [])
    for eid in req_execs:
        efile = EXECUTIONS_DIR / f"{eid}.json"
        if not efile.exists():
            print(f"[VERIFY-ALL: VERIFIED_FAIL] Execution receipt '{eid}' not found.")
            return 1
        edata = load_json(efile)
        if edata.get("result") != "PASS" or edata.get("exit_code") != 0:
            print(f"[VERIFY-ALL: VERIFIED_FAIL] Execution receipt '{eid}' result is not PASS")
            return 1
        if req_cid and edata.get("candidate_id") != req_cid:
            print(f"[VERIFY-ALL: VERIFIED_FAIL] Execution receipt candidate mismatch: {edata.get('candidate_id')} != {req_cid}")
            return 1
        if edata.get("baseline_generation") != current_baseline:
            print(f"[VERIFY-ALL: BASELINE_GENERATION_MISMATCH] Execution baseline mismatch: {edata.get('baseline_generation')} != {current_baseline}")
            return 1

        cmd_s = edata.get("command", "")
        ec = edata.get("exit_code", 0)
        so_h = edata.get("stdout_sha256", "")
        se_h = edata.get("stderr_sha256", "")
        c_fp = edata.get("candidate_fingerprint", "")
        b_gen = edata.get("baseline_generation", "")
        exp_fp = hashlib.sha256(f"{eid}:{edata.get('candidate_id')}:{c_fp}:{b_gen}:{cmd_s}:{ec}:{so_h}:{se_h}".encode("utf-8")).hexdigest()
        if exp_fp.lower() != edata.get("execution_receipt_fingerprint", "").lower():
            print(f"[VERIFY-ALL: EVIDENCE_DRIFT] Execution receipt '{eid}' fingerprint mismatch!")
            return 1
        print(f"  [PASS] Execution receipt '{eid}' verified and bound to candidate ({c_fp[:16]}...)")

    print(f"\n[VERIFY-ALL: VERIFIED_PASS] Gate '{gate_id}' independently verified with zero drift.")
    return 0

# --- MAIN ENTRYPOINT ---


def cmd_lock(args: argparse.Namespace) -> int:
    """Handles cooperative certification lock operations."""
    action = getattr(args, "lock_action", None)
    if action == "acquire":
        purpose = getattr(args, "purpose", "Certification Window")
        ttl = getattr(args, "ttl", 300)
        owner = getattr(args, "owner", None)
        bg = getattr(args, "baseline", None)
        ok, msg, info = acquire_lock(purpose=purpose, ttl_seconds=ttl, owner=owner, baseline_generation=bg)
        if not ok:
            print(f"[FAIL] {msg}", file=sys.stderr)
            return 1
        print(f"[PASS] {msg}")
        print(f"  Lock ID:     {info.get('lock_id')}")
        print(f"  Owner:       {info.get('owner')}")
        print(f"  Baseline:    {info.get('baseline_generation')}")
        print(f"  Expires At:  {info.get('expires_at')}")
        return 0

    elif action == "status":
        info = get_lock_state()
        active, reason = is_lock_active(info)
        print("=== CERTIFICATION LOCK STATUS ===")
        print(f"Lock Type:   {info.get('lock_type', 'COOPERATIVE_CERTIFICATION_LOCK')}")
        print(f"Status:      {info.get('status')}")
        print(f"Active:      {'YES' if active else 'NO'} ({reason})")
        print(f"Lock ID:     {info.get('lock_id')}")
        print(f"Owner:       {info.get('owner')}")
        print(f"Purpose:     {info.get('purpose')}")
        print(f"Baseline:    {info.get('baseline_generation')}")
        print(f"Acquired At: {info.get('acquired_at')}")
        print(f"Expires At:  {info.get('expires_at')}")
        if info.get("released_at"):
            print(f"Released At: {info.get('released_at')}")
        return 0

    elif action == "release":
        lid = getattr(args, "lock_id", None)
        force = getattr(args, "force", False)
        ok, msg, info = release_lock(lock_id=lid, force=force)
        if not ok:
            print(f"[FAIL] {msg}", file=sys.stderr)
            return 1
        print(f"[PASS] {msg}")
        return 0
    else:
        print(f"Unknown lock action: {action}", file=sys.stderr)
        return 1

def cmd_certify(args: argparse.Namespace) -> int:
    """
    Executes atomic fail-closed certification workflow for a gate.
    Workflow:
      1. Acquire cooperative certification lock
      2. Pre-certification baseline verification
      3. Pre-execution candidate verification
      4. Approved execution verification
      5. Post-execution candidate verification
      6. Post-execution baseline verification (CERTIFICATION_WINDOW_DRIFT check)
      7. Verify-all independent proof reconstruction
      8. Finally: Release certification lock
    """
    gate_id = args.gate_id
    ttl = getattr(args, "ttl", 300)
    print(f"=== ATOMIC CERTIFICATION WORKFLOW: {gate_id} ===")
    print(f"Classification: COOPERATIVE_CERTIFICATION_LOCK (Enforced by QuantumBot Harness)")

    # 1. Acquire Lock
    purpose = f"Atomic certification window for {gate_id}"
    acquired, msg, lock_info = acquire_lock(purpose=purpose, ttl_seconds=ttl)
    if not acquired:
        print(f"[FAIL] {msg}", file=sys.stderr)
        return 1
    print(f"[STEP 1/7] {msg}")
    lock_id = lock_info["lock_id"]

    try:
        # Load Gate
        gpath = GATES_DIR / f"{gate_id}.json"
        if not gpath.exists():
            print(f"[FAIL] Gate file not found: {gpath}", file=sys.stderr)
            return 1
        gate_data = load_json(gpath)
        candidate_id = gate_data.get("required_candidate_id") or gate_data.get("required_candidate")
        required_bg = gate_data.get("required_baseline_generation")

        # 2. Pre-certification baseline verification
        print(f"\n[STEP 2/7] Pre-certification baseline verification (Baseline: {required_bg})...")
        b_ok, b_discrepancies = verify_baseline_artifacts(required_bg)
        if not b_ok:
            for d in b_discrepancies:
                print(f"  [DRIFT] {d}")
            print(f"[FAIL] PRE_CERTIFICATION_BASELINE_DRIFT detected. Aborting certification.", file=sys.stderr)
            return 1
        print("  [PASS] Pre-certification baseline artifacts verified identical to canonical receipts.")

        # 3. Pre-execution candidate verification
        print(f"\n[STEP 3/7] Pre-execution candidate verification ({candidate_id})...")
        c_ok, c_status, c_data, c_err = verify_candidate_internal(candidate_id)
        if not c_ok:
            print(f"  [FAIL] Candidate verification failed: {c_status} ({c_err})", file=sys.stderr)
            return 1
        print(f"  [PASS] Candidate '{candidate_id}' snapshot verified (Fingerprint: {c_data.get('candidate_fingerprint')[:16]}...).")

        # 4. Approved execution verification
        print(f"\n[STEP 4/7] Approved execution verification...")
        req_execs = gate_data.get("required_execution_receipts", [])
        if not req_execs:
            print("  [FAIL] Gate defines no required_execution_receipts.", file=sys.stderr)
            return 1
        for eid in req_execs:
            efile = EXECUTIONS_DIR / f"{eid}.json"
            if not efile.exists():
                print(f"  [FAIL] Execution receipt not found: {efile}", file=sys.stderr)
                return 1
            edata = load_json(efile)
            if edata.get("result") != "PASS" or edata.get("exit_code") != 0:
                print(f"  [FAIL] Execution receipt '{eid}' result is {edata.get('result')} (exit code {edata.get('exit_code')})", file=sys.stderr)
                return 1
            print(f"  [PASS] Execution receipt '{eid}' verified (Result: PASS, exit_code: 0).")

        # 5. Post-execution candidate verification
        print(f"\n[STEP 5/7] Post-execution candidate immutability verification ({candidate_id})...")
        c_ok_post, c_status_post, c_data_post, c_err_post = verify_candidate_internal(candidate_id)
        if not c_ok_post:
            print(f"  [FAIL] CANDIDATE_MUTATION_DURING_TESTS: {c_status_post} ({c_err_post})", file=sys.stderr)
            return 1
        print("  [PASS] Candidate files remained 100% immutable throughout execution window.")

        # 6. Post-execution baseline verification
        print(f"\n[STEP 6/7] Post-execution baseline verification (Baseline: {required_bg})...")
        b_ok_post, b_discrepancies_post = verify_baseline_artifacts(required_bg)
        if not b_ok_post:
            for d in b_discrepancies_post:
                print(f"  [DRIFT] {d}")
            print(f"[FAIL] CERTIFICATION_WINDOW_DRIFT: Baseline artifacts modified during certification window! Aborting.", file=sys.stderr)
            return 1
        print("  [PASS] Baseline artifacts remained 100% immutable throughout certification window.")

        # 7. Verify-All (Independent Complete Proof Reconstruction)
        print(f"\n[STEP 7/7] Executing complete independent proof reconstruction (verify-all)...")
        va_args = argparse.Namespace(gate_id=gate_id, quick=False)
        va_exit = cmd_verify_all(va_args)
        if va_exit != 0:
            print(f"[FAIL] Verify-all proof failed with exit code {va_exit}", file=sys.stderr)
            return va_exit

        print(f"\n=== ATOMIC CERTIFICATION SUCCESSFUL: {gate_id} ===")
        print(f"Candidate: {candidate_id}")
        print(f"Baseline:  {required_bg}")
        print(f"Status:    VERIFIED_PASS")
        return 0

    finally:
        rel_ok, rel_msg, _ = release_lock(lock_id=lock_id)
        print(f"\n[FINALLY] {rel_msg}")


def resolve_research_state(
    root: Optional[Path] = None,
    ps_path_override: Optional[Path] = None,
    harness_md_override: Optional[Path] = None,
    ledger_path_override: Optional[Path] = None,
) -> Tuple[Dict[str, str], bool, List[str]]:
    """
    Resolves canonical quantitative research state strictly from authoritative sources:
    - research_phase: docs/ENGINEERING_HARNESS.md (latest section) cross-checked with PROJECT_STATE.json
    - research_generation: reports/MULTIPLE_TESTING_LEDGER_V2.json (experiments[-1].generation_id)
    - research_validation_status: reports/MULTIPLE_TESTING_LEDGER_V2.json (validated_development_edge, economically_viable_development)

    Fail-closed: returns UNKNOWN and sets is_safe=False if any source is missing, malformed, or contradictory.
    Forbids hardcoding phase/generation and forbids regex inferencing from generation IDs.
    """
    proj_root = root or PROJECT_ROOT
    ps_path = ps_path_override or (proj_root / "quantumbot_harness" / "PROJECT_STATE.json")
    md_path = harness_md_override or (proj_root / "docs" / "ENGINEERING_HARNESS.md")
    ledger_path = ledger_path_override or (proj_root / "reports" / "MULTIPLE_TESTING_LEDGER_V2.json")

    reasons: List[str] = []
    is_safe = True

    # 1. Resolve research generation & validation status from ledger
    res_gen = "UNKNOWN"
    res_val_status = "UNKNOWN"
    if not ledger_path.exists():
        reasons.append(f"Research ledger missing at {ledger_path}")
        is_safe = False
    else:
        try:
            ledger_data = load_json(ledger_path)
            exps = ledger_data.get("experiments")
            if not isinstance(exps, list) or len(exps) == 0:
                reasons.append("No valid experiments array found in research ledger")
                is_safe = False
            else:
                latest_exp = exps[-1]
                if not isinstance(latest_exp, dict):
                    reasons.append("Malformed experiment entry in research ledger")
                    is_safe = False
                else:
                    gid = latest_exp.get("generation_id")
                    if not gid or not isinstance(gid, str) or not gid.strip():
                        reasons.append("Missing or empty generation_id in research ledger experiment")
                        is_safe = False
                    else:
                        res_gen = gid.strip()

                    val_edge = latest_exp.get("validated_development_edge")
                    econ_viable = latest_exp.get("economically_viable_development")
                    if val_edge is None or econ_viable is None or not isinstance(val_edge, (int, float)) or not isinstance(econ_viable, bool):
                        res_val_status = "UNKNOWN (malformed edge/economic metadata)"
                        reasons.append("Malformed research validation metadata in ledger")
                        is_safe = False
                    elif val_edge == 0 and not econ_viable:
                        res_val_status = "NO_EDGE (edge=0, economically_negative)"
                    elif val_edge > 0 and econ_viable:
                        res_val_status = f"EDGE_DETECTED (edge={val_edge}, economically_viable)"
                    else:
                        res_val_status = f"VALIDATED (edge={val_edge}, viable={econ_viable})"
        except Exception as exc:
            reasons.append(f"Error reading research ledger: {exc}")
            is_safe = False

    # 2. Resolve research phase from docs/ENGINEERING_HARNESS.md
    res_phase = "UNKNOWN"
    if not md_path.exists():
        reasons.append(f"ENGINEERING_HARNESS.md missing at {md_path}")
        is_safe = False
    else:
        try:
            md_text = md_path.read_text(encoding="utf-8")
            phase_matches = re.findall(r"^##\s+\d+\.\s+FASE\s+([\d\.]+[a-zA-Z]?):", md_text, re.MULTILINE)
            if not phase_matches:
                reasons.append("No FASE section headers found in ENGINEERING_HARNESS.md")
                is_safe = False
            else:
                res_phase = phase_matches[-1].strip()
        except Exception as exc:
            reasons.append(f"Error reading ENGINEERING_HARNESS.md: {exc}")
            is_safe = False

    # 3. Cross-check against PROJECT_STATE.json
    if not ps_path.exists():
        reasons.append(f"PROJECT_STATE.json missing at {ps_path}")
        is_safe = False
    else:
        try:
            ps_data = load_json(ps_path)
            ps_phase = ps_data.get("research_phase") or ps_data.get("current_certified_phase")
            if not ps_phase or ps_phase == "UNKNOWN":
                reasons.append("research_phase is missing or UNKNOWN in PROJECT_STATE.json")
                is_safe = False
            elif res_phase != "UNKNOWN" and ps_phase != res_phase:
                reasons.append(f"Conflicting research phase: ENGINEERING_HARNESS.md has '{res_phase}' but PROJECT_STATE.json has '{ps_phase}'")
                is_safe = False

            ps_gen = ps_data.get("research_generation") or ps_data.get("baseline_generation")
            if not ps_gen or ps_gen == "UNKNOWN":
                reasons.append("research_generation is missing or UNKNOWN in PROJECT_STATE.json")
                is_safe = False
            elif res_gen != "UNKNOWN" and ps_gen != res_gen:
                reasons.append(f"Conflicting research generation: ledger has '{res_gen}' but PROJECT_STATE.json has '{ps_gen}'")
                is_safe = False
        except Exception as exc:
            reasons.append(f"Error reading PROJECT_STATE.json for research cross-check: {exc}")
            is_safe = False

    res_data = {
        "research_phase": res_phase,
        "research_generation": res_gen,
        "research_validation_status": res_val_status,
    }
    return res_data, is_safe, reasons


def get_bot_status_data(
    root: Optional[Path] = None,
    ps_path_override: Optional[Path] = None,
    ks_path_override: Optional[Path] = None,
    lock_path_override: Optional[Path] = None,
    gates_dir_override: Optional[Path] = None,
    mock_baseline_clean: Optional[bool] = None,
    harness_md_override: Optional[Path] = None,
    ledger_path_override: Optional[Path] = None,
) -> Tuple[Dict[str, Any], bool, List[str]]:
    """
    Evaluates deterministic operational summary of safe, non-secret state.
    Strictly read-only: does not modify any files.
    Fail-closed: returns is_safe=True only if all safety criteria are satisfied.
    Forbids access to .env, FINAL_HOLDOUT, and quantumbot.db.
    """
    proj_root = root or PROJECT_ROOT
    ps_path = ps_path_override or (proj_root / "quantumbot_harness" / "PROJECT_STATE.json")
    ks_path = ks_path_override or (proj_root / "database" / "kill_switch_state.json")
    lock_path = lock_path_override or (proj_root / "quantumbot_harness" / "state" / "CERTIFICATION_LOCK.json")
    gates_dir = gates_dir_override or (proj_root / "quantumbot_harness" / "gates")

    reasons: List[str] = []
    is_safe = True

    # 1. Load PROJECT_STATE.json
    ps: Dict[str, Any] = {}
    if not ps_path.exists():
        reasons.append(f"PROJECT_STATE.json missing at {ps_path}")
        is_safe = False
    else:
        try:
            ps = load_json(ps_path)
        except Exception as exc:
            reasons.append(f"Could not load PROJECT_STATE.json: {exc}")
            is_safe = False

    # 2. Harness baseline generation
    bg = ps.get("baseline_generation")
    if not bg or bg == "UNKNOWN":
        bg_display = "UNKNOWN"
        reasons.append("baseline_generation is missing or UNKNOWN in PROJECT_STATE.json")
        is_safe = False
    else:
        bg_display = str(bg)

    # 3. Harness certified gate and candidate
    last_gate_id = ps.get("last_gate_id")
    if not last_gate_id:
        cand_display = "UNKNOWN"
        cert_status_display = "UNCERTIFIED / NO_GATE"
        reasons.append("last_gate_id is missing in PROJECT_STATE.json")
        is_safe = False
    else:
        gpath = gates_dir / f"{last_gate_id}.json"
        if not gpath.exists():
            cand_display = "UNKNOWN"
            cert_status_display = f"GATE_NOT_FOUND ({last_gate_id})"
            reasons.append(f"Gate file '{last_gate_id}.json' not found")
            is_safe = False
        else:
            try:
                gdata = load_json(gpath)
                req_cand = gdata.get("required_candidate_id") or gdata.get("required_candidate")
                gate_status = gdata.get("status")
                gate_req_bg = gdata.get("required_baseline_generation")

                cand_display = req_cand or "UNKNOWN"
                if not req_cand:
                    reasons.append("required_candidate_id missing in gate")
                    is_safe = False

                if gate_status == "PASS":
                    cert_status_display = "CERTIFIED / PASS"
                else:
                    cert_status_display = f"UNCERTIFIED ({gate_status})"
                    reasons.append(f"Gate '{last_gate_id}' status is '{gate_status}', expected 'PASS'")
                    is_safe = False

                if gate_req_bg and bg and gate_req_bg != bg:
                    reasons.append(f"Baseline generation mismatch: gate requires '{gate_req_bg}', project has '{bg}'")
                    is_safe = False
            except Exception as exc:
                cand_display = "UNKNOWN"
                cert_status_display = f"GATE_ERROR ({exc})"
                reasons.append(f"Error loading gate '{last_gate_id}': {exc}")
                is_safe = False

    # 4. Quantitative Research Track resolution
    res_data, res_safe, res_reasons = resolve_research_state(
        root=proj_root,
        ps_path_override=ps_path,
        harness_md_override=harness_md_override,
        ledger_path_override=ledger_path_override
    )
    if not res_safe:
        is_safe = False
        reasons.extend(res_reasons)

    # 5. LIVE trading status
    lt_status = ps.get("live_trading_status")
    lt_allow = ps.get("allow_live_trading")
    if lt_status == "BLOCKED" and lt_allow is False:
        live_display = "BLOCKED"
    else:
        live_display = f"ALLOWED / DANGEROUS (status={lt_status}, allow_live_trading={lt_allow})"
        reasons.append(f"LIVE trading is not blocked: status={lt_status}, allow_live_trading={lt_allow}")
        is_safe = False

    # 6. Kill switch
    if not ks_path.exists():
        ks_display = "UNKNOWN / ERROR (file not found)"
        reasons.append(f"kill_switch_state.json not found at {ks_path}")
        is_safe = False
    else:
        try:
            ks_data = load_json(ks_path)
            mka = ks_data.get("manual_kill_active")
            if not isinstance(mka, bool):
                ks_display = f"UNKNOWN / INVALID (manual_kill_active={mka})"
                reasons.append(f"kill switch manual_kill_active is not boolean: {mka}")
                is_safe = False
            elif mka is False:
                ks_display = "DISARMED / READY (manual_kill_active=false)"
            else:
                ks_display = "ARMED / ENGAGED (manual_kill_active=true)"
        except Exception as exc:
            ks_display = f"UNKNOWN / ERROR ({exc})"
            reasons.append(f"Error loading kill_switch_state.json: {exc}")
            is_safe = False

    # 7. FINAL_HOLDOUT status (Must strictly NEVER read FINAL_HOLDOUT directory)
    fh_status = ps.get("final_holdout_status")
    fh_count = ps.get("final_holdout_access_count")
    if fh_status == "LOCKED/UNTOUCHED" and fh_count == 0:
        holdout_display = "LOCKED (0 access, 0 bars read)"
    else:
        holdout_display = f"UNLOCKED / ACCESSED (status={fh_status}, access_count={fh_count})"
        reasons.append(f"FINAL_HOLDOUT is not locked/untouched: status={fh_status}, count={fh_count}")
        is_safe = False

    # 8. Evidence drift
    if mock_baseline_clean is not None:
        if mock_baseline_clean:
            drift_display = "CLEAN"
        else:
            drift_display = "DRIFT DETECTED"
            reasons.append("Simulated baseline evidence drift")
            is_safe = False
    else:
        try:
            b_ok, b_discrepancies = verify_baseline_artifacts(bg if bg != "UNKNOWN" else None)
            if b_ok:
                drift_display = "CLEAN"
            else:
                drift_display = "DRIFT DETECTED"
                reasons.append(f"Baseline evidence drift detected: {'; '.join(b_discrepancies)}")
                is_safe = False
        except Exception as exc:
            drift_display = f"ERROR ({exc})"
            reasons.append(f"Error verifying baseline artifacts: {exc}")
            is_safe = False

    # 9. Certification lock
    try:
        lock_state = get_lock_state(lock_path)
        is_act, act_reason = is_lock_active(lock_state)
        l_status = lock_state.get("status")
        if is_act:
            lock_display = f"ACTIVE ({lock_state.get('lock_id')} held by {lock_state.get('owner')})"
            reasons.append(f"Certification lock is currently ACTIVE: {lock_state.get('lock_id')}")
            is_safe = False
        elif l_status == "RELEASED":
            lock_display = "RELEASED"
        else:
            lock_display = f"EXPIRED ({act_reason})"
    except Exception as exc:
        lock_display = f"UNKNOWN / ERROR ({exc})"
        reasons.append(f"Error reading certification lock: {exc}")
        is_safe = False

    # 10. Overall development safety
    safety_display = "SAFE" if is_safe else "BLOCKED"

    status_data = {
        "harness_baseline_generation": bg_display,
        "harness_certified_candidate": cand_display,
        "harness_certification_status": cert_status_display,
        "research_phase": res_data["research_phase"],
        "research_generation": res_data["research_generation"],
        "research_validation_status": res_data["research_validation_status"],
        "live_trading_status": live_display,
        "kill_switch": ks_display,
        "final_holdout": holdout_display,
        "evidence_drift": drift_display,
        "certification_lock": lock_display,
        "overall_development_safety": safety_display,
        "is_safe": is_safe,
        "safety_reasons": reasons,
        "current_certified_research_phase": res_data["research_phase"],
        "latest_known_research_baseline": res_data["research_generation"]
    }

    return status_data, is_safe, reasons


def format_bot_status_text(data: Dict[str, Any]) -> str:
    """Formats bot status dictionary into the exact 20-line canonical diagnostic report."""
    lines = [
        "=" * 70,
        "QUANTUMBOT STATUS",
        "=" * 70,
        f"{'Harness baseline generation:':<38}{data['harness_baseline_generation']}",
        f"{'Harness certified candidate:':<38}{data['harness_certified_candidate']}",
        f"{'Harness certification status:':<38}{data['harness_certification_status']}",
        "",
        f"{'Research phase:':<38}{data['research_phase']}",
        f"{'Research generation:':<38}{data['research_generation']}",
        f"{'Research validation status:':<38}{data['research_validation_status']}",
        "",
        f"{'LIVE trading:':<38}{data['live_trading_status']}",
        f"{'Kill switch:':<38}{data['kill_switch']}",
        f"{'FINAL_HOLDOUT:':<38}{data['final_holdout']}",
        "",
        f"{'Evidence drift:':<38}{data['evidence_drift']}",
        f"{'Certification lock:':<38}{data['certification_lock']}",
        "",
        f"{'Overall development safety:':<38}{data['overall_development_safety']}",
        "=" * 70
    ]
    return "\n".join(lines)


def cmd_bot_status(args: argparse.Namespace) -> int:
    """Handles 'bot-status' CLI command."""
    data, is_safe, reasons = get_bot_status_data()

    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
    else:
        print(format_bot_status_text(data))

    return 0 if is_safe else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="harness",
        description="QuantumBot Harness Deterministic Verifier & CLI Foundation (H2/H3)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Harness command to execute")

    # state
    subparsers.add_parser("state", help="Inspect current project and harness state")

    # validate
    subparsers.add_parser("validate", help="Validate schemas, instances, and cross-references")

    # verify <receipt_id>
    verify_p = subparsers.add_parser("verify", help="Cryptographically verify a receipt source")
    verify_p.add_argument("receipt_id", help="ID of the receipt to verify")

    # task list
    task_p = subparsers.add_parser("task", help="Task management commands")
    task_sub = task_p.add_subparsers(dest="task_action", help="Task action")
    task_sub.add_parser("list", help="List all registered tasks")

    # gate <gate_id>
    gate_p = subparsers.add_parser("gate", help="Evaluate gate against verifiable evidence")
    gate_p.add_argument("gate_id", help="ID of the gate to evaluate")

    # fingerprint <path...>
    fp_p = subparsers.add_parser("fingerprint", help="Generate deterministic candidate fingerprint")
    fp_p.add_argument("paths", nargs="+", help="Files or directories to fingerprint")

    # freeze <candidate_id> <path...>
    freeze_p = subparsers.add_parser("freeze", help="Freeze candidate snapshot and compute fingerprint")
    freeze_p.add_argument("candidate_id", help="Unique candidate ID (e.g. CANDIDATE-H3-HARNESS-001)")
    freeze_p.add_argument("paths", nargs="+", help="Files or directories to freeze into candidate")
    freeze_p.add_argument("--spec-id", dest="spec_id", default=None, help="Associated SPEC ID")

    # candidate verify <candidate_id>
    cand_p = subparsers.add_parser("candidate", help="Candidate operations")
    cand_sub = cand_p.add_subparsers(dest="candidate_action", help="Candidate action")
    cand_ver_p = cand_sub.add_parser("verify", help="Verify candidate against frozen snapshot")
    cand_ver_p.add_argument("candidate_id", help="Candidate ID to verify")

    # run <candidate_id> -- <command...>
    run_p = subparsers.add_parser("run", help="Execute approved test command against frozen candidate")
    run_p.add_argument("candidate_id", help="Candidate ID to execute against")
    run_p.add_argument("exec_cmd", nargs=argparse.REMAINDER, help="Approved command to execute (after --)")

    # lock <acquire|status|release>
    lock_p = subparsers.add_parser("lock", help="Manage cooperative certification lock")
    lock_sub = lock_p.add_subparsers(dest="lock_action", help="Lock action")
    
    lacq_p = lock_sub.add_parser("acquire", help="Acquire certification lock")
    lacq_p.add_argument("purpose", nargs="?", default="Certification Window", help="Purpose of lock")
    lacq_p.add_argument("--ttl", type=int, default=300, help="TTL in seconds (default 300)")
    lacq_p.add_argument("--owner", default=None, help="Lock owner")
    lacq_p.add_argument("--baseline", default=None, help="Baseline generation")
    
    lock_sub.add_parser("status", help="Show lock status")
    
    lrel_p = lock_sub.add_parser("release", help="Release certification lock")
    lrel_p.add_argument("--lock-id", default=None, help="Lock ID to release")
    lrel_p.add_argument("--force", action="store_true", help="Force release regardless of ID")

    # certify <gate_id>
    cert_p = subparsers.add_parser("certify", help="Execute atomic fail-closed certification workflow")
    cert_p.add_argument("gate_id", help="Gate ID to certify")
    cert_p.add_argument("--ttl", type=int, default=300, help="Lock TTL in seconds (default 300)")

    # verify-all <gate_id>
    va_p = subparsers.add_parser("verify-all", help="Independently reconstruct all validations for a gate")
    va_p.add_argument("gate_id", help="Gate ID to verify")

    # bot-status [--json]
    status_p = subparsers.add_parser("bot-status", help="Display deterministic operational summary of safe, non-secret state")
    status_p.add_argument("--json", action="store_true", help="Output summary in machine-readable JSON format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # M2: Machine Tool Manifest + Role Enforcement
    role = os.environ.get("HARNESS_ROLE")
    if role:
        tools_path = Path("quantumbot_harness/tools.yaml")
        if tools_path.exists():
            import yaml
            with open(tools_path, "r", encoding="utf-8") as f:
                tools_acl = yaml.safe_load(f).get("tools", {})
            allowed_roles = tools_acl.get(args.command, [])
            if role not in allowed_roles:
                print(f"Role '{role}' is not authorized to execute command '{args.command}'", file=sys.stderr)
                return 1

    if args.command == "state":
        return cmd_state(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "task":
        if getattr(args, "task_action", None) == "list":
            return cmd_task_list(args)
        else:
            print("Unknown task action. Use 'python harness.py task list'", file=sys.stderr)
            return 1
    elif args.command == "gate":
        return cmd_gate(args)
    elif args.command == "fingerprint":
        return cmd_fingerprint(args)
    elif args.command == "freeze":
        return cmd_freeze(args)
    elif args.command == "candidate":
        if getattr(args, "candidate_action", None) == "verify":
            return cmd_candidate_verify(args)
        else:
            print("Unknown candidate action. Use 'python harness.py candidate verify <candidate_id>'", file=sys.stderr)
            return 1
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "verify-all":
        return cmd_verify_all(args)
    elif args.command == "lock":
        return cmd_lock(args)
    elif args.command == "certify":
        return cmd_certify(args)
    elif args.command == "bot-status":
        return cmd_bot_status(args)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())
