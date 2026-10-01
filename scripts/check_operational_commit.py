"""Offline engineering-only check of Git objects, never the dirty worktree.

Run this checker and its manifest from a trusted location outside the candidate.
No downloads, trading calls, baseline updates or canonical certification.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


MANIFEST_PATH = "quantumbot_harness/ci/ENGINEERING_BASELINE_001.json"
MAX_BLOB = 3 * 1024 * 1024
DENIED_PARTS = frozenset({
    "data", "research_data", "research", "final_holdout", "database",
    "logs", "backups", ".codex-remote-attachments", "strategies", "risk",
    "execution", "backtesting", "analytics", "machine_learning", ".git",
})


class CheckBlocked(ValueError):
    pass


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or any(ord(c) < 32 for c in value):
        raise CheckBlocked("PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in {".", ".."} or part.rstrip(" .") != part for part in path.parts
    ):
        raise CheckBlocked("PATH_INVALID")
    if any(part.casefold() in DENIED_PARTS or part.casefold().startswith(".env") for part in path.parts):
        raise CheckBlocked("PAYLOAD_OR_SECRET_PATH_DENIED")
    if path.suffix.casefold() in {".csv", ".gz", ".zip", ".db", ".sqlite", ".sqlite3", ".pem", ".pfx", ".key"}:
        raise CheckBlocked("PAYLOAD_OR_SECRET_PATH_DENIED")
    if value.casefold() in {"main.py", "runner.py", "bybit_client.py", "bingx_client.py"}:
        raise CheckBlocked("TRADING_ENGINE_DENIED")
    return path


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def git_blob_id(payload):
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


def check_remote_commit_metadata(candidate_sha, trusted_tree, document):
    """Metadata-only binding: candidate source must equal the frozen trust tree.

    The caller authenticates GitHub's commit-object response. No candidate
    checkout/fetch is needed: identical trees bind exactly the same file bytes.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", candidate_sha) or not re.fullmatch(r"[0-9a-f]{40}", trusted_tree):
        raise CheckBlocked("REMOTE_COMMIT_BINDING_INVALID")
    if not isinstance(document, dict) or document.get("sha") != candidate_sha:
        raise CheckBlocked("REMOTE_COMMIT_BINDING_INVALID")
    tree = document.get("tree")
    if not isinstance(tree, dict) or tree.get("sha") != trusted_tree:
        raise CheckBlocked("REMOTE_CANDIDATE_TREE_NOT_APPROVED")


def git(repo, *args):
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args],
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode:
        raise CheckBlocked("GIT_METADATA_UNAVAILABLE")
    return result.stdout


def entries(repo, commit=None):
    if commit is None:
        raw = git(repo, "ls-files", "--stage", "-z")
    else:
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise CheckBlocked("COMMIT_SHA_REQUIRED")
        if git(repo, "cat-file", "-t", commit).strip() != b"commit":
            raise CheckBlocked("COMMIT_OBJECT_REQUIRED")
        raw = git(repo, "ls-tree", "-r", "--full-tree", "-z", commit)
    records, seen = {}, set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, name = record.split(b"\t", 1)
            mode, oid, stage = header.decode("ascii").split() if commit is None else (None, None, None)
            if commit is not None:
                mode, kind, oid = header.decode("ascii").split()
                if kind != "blob":
                    raise CheckBlocked("NON_REGULAR_GIT_ENTRY")
            elif stage != "0":
                raise CheckBlocked("UNMERGED_INDEX")
            name = name.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise CheckBlocked("GIT_ENTRY_INVALID") from exc
        safe_path(name)  # before reading any content, even unknown staged paths
        if mode not in {"100644", "100755"}:
            raise CheckBlocked("NON_REGULAR_GIT_ENTRY")
        if not re.fullmatch(r"[0-9a-f]{40}", oid) or name.casefold() in seen:
            raise CheckBlocked("GIT_ENTRY_INVALID")
        seen.add(name.casefold())
        records[name] = {"mode": mode, "oid": oid}
    return records


def load_manifest(payload):
    if len(payload) > MAX_BLOB:
        raise CheckBlocked("MANIFEST_TOO_LARGE")
    try:
        manifest = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise CheckBlocked("MANIFEST_INVALID") from exc
    if not isinstance(manifest, dict) or manifest.get("baseline_id") != "ENGINEERING-BASELINE-001":
        raise CheckBlocked("MANIFEST_INVALID")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files or MANIFEST_PATH in files:
        raise CheckBlocked("MANIFEST_INVALID")
    seen = set()
    for name, binding in files.items():
        safe_path(name)
        if name.casefold() in seen or not isinstance(binding, dict):
            raise CheckBlocked("MANIFEST_INVALID")
        seen.add(name.casefold())
        if not re.fullmatch(r"[0-9a-f]{64}", str(binding.get("sha256"))) or not re.fullmatch(r"[0-9a-f]{40}", str(binding.get("git_blob_sha1"))):
            raise CheckBlocked("MANIFEST_INVALID")
        if binding.get("mode") not in {"100644", "100755"}:
            raise CheckBlocked("MANIFEST_INVALID")
    if manifest.get("dependencies") != {"pytest": "9.1.1", "jsonschema": "4.26.0"} or manifest.get("guard_tests") != 43:
        raise CheckBlocked("MANIFEST_INVALID")
    return manifest


def verified_blobs(repo, manifest_payload, records):
    manifest = load_manifest(manifest_payload)
    expected = manifest["files"]
    if set(records) != set(expected) | {MANIFEST_PATH}:
        raise CheckBlocked("STAGED_OR_TREE_SCOPE_MISMATCH")
    if records[MANIFEST_PATH] != {"mode": "100644", "oid": git_blob_id(manifest_payload)}:
        raise CheckBlocked("CANDIDATE_CANNOT_REPLACE_TRUSTED_MANIFEST")
    # Check all identities before reading a single candidate blob.
    for name, binding in expected.items():
        if records[name] != {"mode": binding["mode"], "oid": binding["git_blob_sha1"]}:
            raise CheckBlocked("UNREVIEWED_BLOB_CHANGE:" + name)
    blobs = {MANIFEST_PATH: manifest_payload}
    for name, binding in expected.items():
        oid = records[name]["oid"]
        size = int(git(repo, "cat-file", "-s", oid))
        if size > MAX_BLOB:
            raise CheckBlocked("BLOB_TOO_LARGE")
        payload = git(repo, "cat-file", "blob", oid)
        if len(payload) != size or sha256(payload) != binding["sha256"]:
            raise CheckBlocked("BLOB_INTEGRITY_FAILED")
        if re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}", payload):
            raise CheckBlocked("SECRET_LITERAL_DETECTED")
        blobs[name] = payload
    return manifest, blobs


def check_registry_result(exit_code, output):
    try:
        result = json.loads(output)
        evidence = result["holdout_evidence"]
        valid = (
            exit_code == 1 and result["status"] == "BLOCKED"
            and result["formal_gate_status"] == "BLOCKED"
            and result["certification_effect"] == "NONE"
            and result["errors"] == ["HOLDOUT_EXPOSURE_CONFIRMED"]
            and result["source_results"] == {}
            and evidence["incident_evidence_status"] == "VERIFIED_PRESERVED_SNAPSHOT"
            and evidence["exact_historical_read_operations"] == "UNKNOWN"
            and evidence["exact_historical_holdout_bytes_read"] == "UNKNOWN"
            and evidence["canonical_zero_counters_are_current_proof"] is False
        )
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        raise CheckBlocked("OPERATIONAL_EVIDENCE_INVALID")


def run_snapshot(manifest, blobs):
    for package, version in manifest["dependencies"].items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise CheckBlocked("OFFLINE_DEPENDENCY_MISSING:" + package) from exc
        if actual != version:
            raise CheckBlocked("OFFLINE_DEPENDENCY_VERSION_MISMATCH:" + package)
    # Disposable approved engineering files only; no worktree mounts or secrets.
    with tempfile.TemporaryDirectory(prefix="quantumbot-engineering-") as location:
        root = Path(location).resolve()
        if root.parent != Path(tempfile.gettempdir()).resolve():
            raise CheckBlocked("TEMP_SNAPSHOT_LOCATION_INVALID")
        for name, payload in blobs.items():
            target = root.joinpath(*safe_path(name).parts)
            if not target.is_relative_to(root):
                raise CheckBlocked("TEMP_SNAPSHOT_PATH_INVALID")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        for name in ("candidates", "executions"):
            (root / "quantumbot_harness" / name).mkdir(parents=True, exist_ok=True)
        env = {key: value for key, value in os.environ.items() if key.upper() in {
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL",
        }}
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        commands = [
            [sys.executable, "-I", "-B", "tests/test_operational_commit_check.py"],
            [sys.executable, "-I", "-B", "-c",
             "import sys,pytest;sys.path.insert(0,'.');raise SystemExit(pytest.main(['-q','-p','no:cacheprovider','tests/test_holdout_evidence_guard.py','--junitxml=.guard-junit.xml']))"],
        ]
        for command in commands:
            done = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=120)
            if done.returncode:
                raise CheckBlocked("SNAPSHOT_REGRESSION_FAILED")
        suites = ET.parse(root / ".guard-junit.xml").getroot().iter("testsuite")
        counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
        for suite in suites:
            for key in counts:
                counts[key] += int(suite.get(key, "0"))
        if counts != {"tests": 43, "failures": 0, "errors": 0, "skipped": 0}:
            raise CheckBlocked("GUARD_TEST_COVERAGE_CHANGED_OR_SKIPPED")
        diagnostic = subprocess.run(
            [sys.executable, "-I", "-B", "scripts/run_m0_registry_verifier.py"],
            cwd=root, env=env, capture_output=True, timeout=30,
        )
        check_registry_result(diagnostic.returncode, diagnostic.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--trusted-manifest", required=True)
    parser.add_argument("--commit")  # absent: index snapshot, not workspace files
    args = parser.parse_args(argv)
    try:
        repo = Path(args.repo).resolve()
        trusted = Path(args.trusted_manifest)
        if trusted.is_symlink() or trusted.resolve() != trusted.absolute():
            raise CheckBlocked("TRUSTED_MANIFEST_REDIRECTED")
        with trusted.open("rb", buffering=0) as stream:
            payload = stream.read(MAX_BLOB + 1)
        before = entries(repo, args.commit)
        manifest, blobs = verified_blobs(repo, payload, before)
        run_snapshot(manifest, blobs)
        if entries(repo, args.commit) != before:
            raise CheckBlocked("GIT_SNAPSHOT_CHANGED_DURING_CHECK")
        print(json.dumps({"engineering_check": "OK", "operational_execution": "BLOCKED", "certification_effect": "NONE", "files_checked": len(blobs), "guard_tests": 43}))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        print(json.dumps({"engineering_check": "BLOCKED", "operational_execution": "BLOCKED", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
