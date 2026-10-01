"""Standard-library tests with disposable synthetic Git repositories only."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location(
    "operational_commit_check",
    Path(__file__).resolve().parents[1] / "scripts/check_operational_commit.py",
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(prefix="quantumbot-git-fixture-")
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)
        self.run_git("init", "-q")
        self.run_git("config", "core.autocrlf", "false")
        self.run_git("config", "user.name", "Synthetic fixture")
        self.run_git("config", "user.email", "fixture@example.invalid")
        self.payload = b"reviewed synthetic engineering\n"
        self.manifest = {
            "baseline_id": "ENGINEERING-BASELINE-001",
            "guard_tests": 43,
            "dependencies": {"pytest": "9.1.1", "jsonschema": "4.26.0"},
            "files": {"allowed.md": {
                "sha256": check.sha256(self.payload),
                "git_blob_sha1": check.git_blob_id(self.payload),
                "mode": "100644",
            }},
        }
        self.trusted = json.dumps(self.manifest).encode()
        self.write("allowed.md", self.payload)
        self.write(check.MANIFEST_PATH, self.trusted)
        self.run_git("add", "--", "allowed.md", check.MANIFEST_PATH)

    def run_git(self, *args):
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=" + str(self.root / "no-hooks"), "-C", str(self.root), *args],
            capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def write(self, name, payload):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def verify(self):
        return check.verified_blobs(self.root, self.trusted, check.entries(self.root))

    def test_exact_index_is_accepted(self):
        self.assertEqual(self.verify()[1]["allowed.md"], self.payload)

    def test_unstaged_change_is_not_executed_or_used(self):
        self.write("allowed.md", b"unreviewed worktree")
        self.assertEqual(self.verify()[1]["allowed.md"], self.payload)

    def test_safe_worktree_cannot_hide_bad_index(self):
        self.write("allowed.md", b"unreviewed staged change")
        self.run_git("add", "--", "allowed.md")
        self.write("allowed.md", self.payload)
        with self.assertRaises(check.CheckBlocked):
            self.verify()

    def test_extra_file_is_rejected(self):
        self.write("extra.md", b"synthetic")
        self.run_git("add", "--", "extra.md")
        with self.assertRaises(check.CheckBlocked):
            self.verify()

    def test_missing_file_is_rejected(self):
        self.run_git("update-index", "--force-remove", "allowed.md")
        with self.assertRaises(check.CheckBlocked):
            self.verify()

    def test_candidate_cannot_replace_manifest(self):
        self.write(check.MANIFEST_PATH, b"{}")
        self.run_git("add", "--", check.MANIFEST_PATH)
        with self.assertRaises(check.CheckBlocked):
            self.verify()

    def test_symlink_mode_rejected_without_reading_target(self):
        self.run_git("update-index", "--cacheinfo", "120000," + check.git_blob_id(self.payload) + ",allowed.md")
        with self.assertRaises(check.CheckBlocked):
            check.entries(self.root)

    def test_executable_mode_change_rejected(self):
        self.run_git("update-index", "--chmod=+x", "allowed.md")
        with self.assertRaises(check.CheckBlocked):
            self.verify()

    def test_case_alias_rejected(self):
        self.run_git("update-index", "--add", "--cacheinfo", "100644," + check.git_blob_id(self.payload) + ",Allowed.md")
        with self.assertRaises(check.CheckBlocked):
            check.entries(self.root)

    def test_all_object_ids_checked_before_any_blob_read(self):
        records = check.entries(self.root)
        records["allowed.md"]["oid"] = "0" * 40
        with mock.patch.object(check, "git", side_effect=AssertionError("Blob read before identity checks")):
            with self.assertRaises(check.CheckBlocked):
                check.verified_blobs(self.root, self.trusted, records)

    def test_dependency_or_mode_self_approval_is_rejected(self):
        for key, value in (("dependencies", {}), ("guard_tests", 42)):
            candidate = copy.deepcopy(self.manifest)
            candidate[key] = value
            with self.subTest(key=key), self.assertRaises(check.CheckBlocked):
                check.load_manifest(json.dumps(candidate).encode())
        candidate = copy.deepcopy(self.manifest)
        candidate["files"]["allowed.md"]["mode"] = "120000"
        with self.assertRaises(check.CheckBlocked):
            check.load_manifest(json.dumps(candidate).encode())

    def test_exact_commit_ignores_dirty_worktree(self):
        self.run_git("-c", "commit.gpgsign=false", "commit", "-qm", "Synthetic engineering fixture")
        oid = self.run_git("rev-parse", "HEAD").decode().strip()
        self.write("allowed.md", b"dirty worktree")
        blobs = check.verified_blobs(self.root, self.trusted, check.entries(self.root, oid))[1]
        self.assertEqual(blobs["allowed.md"], self.payload)


class PolicyTests(unittest.TestCase):
    def test_remote_metadata_accepts_only_bound_identical_tree(self):
        check.check_remote_commit_metadata("a" * 40, "b" * 40, {
            "sha": "a" * 40, "tree": {"sha": "b" * 40},
        })

    def test_remote_metadata_drift_is_denied_before_checkout(self):
        for document in (None, [], {}, {"sha": "a" * 40},
                         {"sha": "c" * 40, "tree": {"sha": "b" * 40}},
                         {"sha": "a" * 40, "tree": {"sha": "c" * 40}}):
            with self.subTest(document=document), self.assertRaises(check.CheckBlocked):
                check.check_remote_commit_metadata("a" * 40, "b" * 40, document)
        with self.assertRaises(check.CheckBlocked):
            check.check_remote_commit_metadata("HEAD", "b" * 40, {})

    def test_denied_paths(self):
        for path in (".env", "docs/.env.local", "data/a.json", "FINAL_HOLDOUT/x.json",
                     "research/a.py", "main.py", "runner.py", "execution/x.py",
                     "a.csv", "a.zip", "../x", "a/../x", "a/./x", "a\\x",
                     "C:/x", "/x", "a. /x", "a\nx"):
            with self.subTest(path=path), self.assertRaises(check.CheckBlocked):
                check.safe_path(path)

    def test_commit_requires_full_sha(self):
        for value in ("HEAD", "abcd", "x" * 40):
            with self.subTest(value=value), self.assertRaises(check.CheckBlocked):
                check.entries(Path("unused"), value)

    def test_invalid_manifest(self):
        for payload in (b"", b"[]", b"{}", b"null", b"\xff", b"x" * (check.MAX_BLOB + 1)):
            with self.subTest(size=len(payload)), self.assertRaises(check.CheckBlocked):
                check.load_manifest(payload)

    def evidence(self):
        return {
            "status": "BLOCKED", "formal_gate_status": "BLOCKED",
            "certification_effect": "NONE", "errors": ["HOLDOUT_EXPOSURE_CONFIRMED"],
            "source_results": {}, "holdout_evidence": {
                "incident_evidence_status": "VERIFIED_PRESERVED_SNAPSHOT",
                "exact_historical_read_operations": "UNKNOWN",
                "exact_historical_holdout_bytes_read": "UNKNOWN",
                "canonical_zero_counters_are_current_proof": False,
            },
        }

    def test_only_verified_expected_block_is_success(self):
        check.check_registry_result(1, json.dumps(self.evidence()))

    def test_generic_failure_and_accidental_success_rejected(self):
        for code in (0, 2, 10, 20, 30):
            with self.subTest(code=code), self.assertRaises(check.CheckBlocked):
                check.check_registry_result(code, json.dumps(self.evidence()))
        for output in (b"{}", b"null", b"[]", b"invalid"):
            with self.subTest(output=output), self.assertRaises(check.CheckBlocked):
                check.check_registry_result(1, output)

    def test_evidence_drift_rejected(self):
        original = self.evidence()
        changes = [
            ("status", "PASS"), ("formal_gate_status", "PASS"),
            ("certification_effect", "PROMOTED"), ("errors", ["OTHER"]),
            ("source_results", {"historical": "PASS"}),
        ]
        for key, value in changes:
            candidate = copy.deepcopy(original)
            candidate[key] = value
            with self.subTest(key=key), self.assertRaises(check.CheckBlocked):
                check.check_registry_result(1, json.dumps(candidate))
        for key, value in (
            ("incident_evidence_status", "MISSING"),
            ("exact_historical_read_operations", 0),
            ("exact_historical_holdout_bytes_read", 0),
            ("canonical_zero_counters_are_current_proof", 0),
            ("canonical_zero_counters_are_current_proof", True),
        ):
            candidate = copy.deepcopy(original)
            candidate["holdout_evidence"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(check.CheckBlocked):
                check.check_registry_result(1, json.dumps(candidate))


if __name__ == "__main__":
    unittest.main()
