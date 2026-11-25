"""Tests for .github/scripts/lease_tamper.py.

Every case builds a real temporary git repository and drives the real CLI, so
the checks are proven against git history rather than mocked diffs.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "lease_tamper.py"


class GitRepo:
    def __init__(self, path):
        self.path = Path(path)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "lease-tamper@example.invalid")
        self.git("config", "user.name", "Lease Tamper Tests")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, check=True):
        proc = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise AssertionError(
                "git %s failed: %s\n%s" % (" ".join(args), proc.stdout, proc.stderr)
            )
        return proc

    def write(self, relative, text):
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-m", message)
        return self.rev()

    def rev(self, ref="HEAD"):
        return self.git("rev-parse", ref).stdout.strip()

    def checkout(self, *args):
        self.git("checkout", *args)


class LeaseTamperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lease-tamper-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- fixtures ---------------------------------------------------------

    def new_repo(self, name="repo"):
        root = self.tmp / name
        root.mkdir()
        return GitRepo(root)

    def make_slice(
        self,
        name="repo",
        verify=True,
        assigned=("src/slice.py",),
        test_files=("tests/test_frozen.py",),
        prohibited=(),
        contract_path=".rizzstack/lease.json",
    ):
        repo = self.new_repo(name)
        repo.write("src/slice.py", "base\n")
        repo.write("tests/test_frozen.py", "base\n")
        repo.write("src/unleased.py", "base\n")
        repo.write("README.md", "base\n")
        base = repo.commit("base")

        repo.checkout("-b", "slice")
        lease = {
            "source_rev": base,
            "scope": {
                "assigned_files": list(assigned),
                "test_files": list(test_files),
            },
        }
        if prohibited:
            lease["scope"]["prohibited"] = list(prohibited)
        repo.write(contract_path, json.dumps(lease, indent=2) + "\n")
        repo.commit("freeze lease")

        repo.write("src/slice.py", "implementation\n")
        verification = repo.commit("implement slice")

        if verify:
            lease["verify_sha"] = verification
            repo.write(contract_path, json.dumps(lease, indent=2) + "\n")
            repo.commit("record verify sha")

        return repo, base, verification

    def run_gate(self, repo, base, head, verify=None, contract=None, labels=None, body=None):
        command = [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo.path),
            "--base",
            base,
            "--head",
            head,
        ]
        if verify:
            command += ["--verify-sha", verify]
        if contract:
            command += ["--contract", contract]
        if labels:
            command += ["--labels", labels]
        if body:
            command += ["--body", body]
        return subprocess.run(command, capture_output=True, text=True)

    # -- clean history ----------------------------------------------------

    def test_clean_history_passes(self):
        repo, base, verify = self.make_slice()
        repo.write("src/slice.py", "follow-up inside the lease\n")
        head = repo.commit("follow-up inside the lease")

        proc = self.run_gate(repo, base, head, verify=verify)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)
        self.assertIn("no frozen test file touched", proc.stdout)

    def test_no_commit_after_verify_passes(self):
        repo, base, verify = self.make_slice(verify=False)
        head = repo.rev()

        proc = self.run_gate(repo, base, head, verify=head)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 commit(s) after verify sha", proc.stdout)

    # -- tamper cases -----------------------------------------------------

    def test_commit_touching_a_frozen_test_fails(self):
        repo, base, verify = self.make_slice()
        repo.write("tests/test_frozen.py", "tampered\n")
        head = repo.commit("quietly relax the frozen test")

        proc = self.run_gate(repo, base, head, verify=verify)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(
            "lease-tamper: FAILED: frozen test file 'tests/test_frozen.py' (scope.test_files) "
            "modified after verify sha " + verify,
            proc.stdout,
        )
        self.assertIn("by commit " + head[:12], proc.stdout)
        self.assertIn("frozen tests may never change", proc.stdout)

    def test_commit_outside_the_lease_fails(self):
        repo, base, verify = self.make_slice()
        repo.write("src/unleased.py", "sneaky\n")
        head = repo.commit("touch a file outside the lease")

        proc = self.run_gate(repo, base, head, verify=verify)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(
            "lease-tamper: FAILED: 'src/unleased.py' is outside the slice lease "
            "(scope.assigned_files)",
            proc.stdout,
        )
        self.assertIn("by commit " + head[:12], proc.stdout)

    def test_frozen_test_listed_in_assigned_files_still_fails(self):
        repo, base, verify = self.make_slice(
            assigned=("src/slice.py", "tests/test_frozen.py")
        )
        repo.write("tests/test_frozen.py", "tampered anyway\n")
        head = repo.commit("assigned but still frozen")

        proc = self.run_gate(repo, base, head, verify=verify)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("frozen test file 'tests/test_frozen.py'", proc.stdout)

    def test_prohibited_glob_fails(self):
        repo, base, verify = self.make_slice(prohibited=("docs/**",))
        repo.write("docs/notes.md", "not allowed\n")
        head = repo.commit("write a prohibited path")

        proc = self.run_gate(repo, base, head, verify=verify)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("frozen test file 'docs/notes.md' (scope.prohibited)", proc.stdout)

    # -- fail-closed cases ------------------------------------------------

    def test_missing_contract_fails_closed(self):
        repo = self.new_repo()
        repo.write("src/slice.py", "base\n")
        base = repo.commit("base")
        repo.write("src/slice.py", "change\n")
        head = repo.commit("change without any lease")

        proc = self.run_gate(repo, base, head, verify=head)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: FAILED: no slice contract", proc.stdout)
        self.assertIn(".rizzstack/lease.json", proc.stdout)

    def test_malformed_contract_fails_closed(self):
        repo = self.new_repo()
        repo.write("src/slice.py", "base\n")
        base = repo.commit("base")
        repo.write(".rizzstack/lease.json", "{not json")
        head = repo.commit("broken lease")

        proc = self.run_gate(repo, base, head)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("is not valid JSON", proc.stdout)

    def test_missing_assigned_files_fails_closed(self):
        repo = self.new_repo()
        repo.write("src/slice.py", "base\n")
        base = repo.commit("base")
        repo.write(".rizzstack/lease.json", json.dumps({"source_rev": base, "scope": {}}))
        head = repo.commit("lease without assigned files")

        proc = self.run_gate(repo, base, head)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("scope.assigned_files must be a non-empty list", proc.stdout)

    def test_verify_sha_that_is_not_an_ancestor_fails_closed(self):
        repo, base, verify = self.make_slice()
        repo.checkout("main")
        repo.write("README.md", "main moved\n")
        side = repo.commit("main moves on")
        repo.checkout("slice")
        head = repo.rev()

        proc = self.run_gate(repo, base, head, verify=side)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("is not an ancestor of PR head", proc.stdout)

    # -- contract resolution ---------------------------------------------

    def test_label_resolves_the_contract_path(self):
        repo, base, verify = self.make_slice(
            name="label", contract_path=".rizzstack/contracts/slice.json"
        )
        head = repo.rev()

        proc = self.run_gate(
            repo,
            base,
            head,
            verify=verify,
            labels="lease-contract:.rizzstack/contracts/slice.json",
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)

    def test_body_line_resolves_the_contract_path(self):
        repo, base, verify = self.make_slice(
            name="body", contract_path=".rizzstack/contracts/slice.json"
        )
        head = repo.rev()

        proc = self.run_gate(
            repo,
            base,
            head,
            verify=verify,
            body="Slice contract: see below\nLease-Contract: .rizzstack/contracts/slice.json\n",
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)

    def test_verify_sha_from_a_label(self):
        repo, base, _verify = self.make_slice(verify=False)
        head = repo.rev()

        # The implementation commit is the current head; the label names it.
        proc = self.run_gate(repo, base, head, labels="lease-verify:" + head)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("0 commit(s) after verify sha", proc.stdout)

    def test_contract_at_base_is_used_for_a_slice_that_does_not_carry_one(self):
        repo = self.new_repo("base-contract")
        repo.write("src/slice.py", "base\n")
        repo.write("tests/test_frozen.py", "base\n")
        repo.write(
            ".rizzstack/lease.json",
            json.dumps(
                {
                    "source_rev": "0" * 40,
                    "scope": {"assigned_files": ["src/slice.py"], "test_files": []},
                }
            ),
        )
        base = repo.commit("main carries the lease")
        # Rewrite source_rev to the real base; it is a coordinator-owned file on main.
        lease = json.loads((repo.path / ".rizzstack/lease.json").read_text())
        lease["source_rev"] = base
        repo.write(".rizzstack/lease.json", json.dumps(lease))
        base = repo.commit("fix lease source_rev")

        repo.checkout("-b", "slice")
        repo.write("src/slice.py", "implementation\n")
        head = repo.commit("implement")

        proc = self.run_gate(repo, base, head, verify=base)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)

    # -- merge handling ---------------------------------------------------

    def test_merge_of_the_base_is_ignored(self):
        repo, base, verify = self.make_slice(name="merge")
        branch_tip = repo.rev()

        repo.checkout("main")
        repo.write("src/unleased.py", "main moved this file\n")
        new_base = repo.commit("main moves a file outside the lease")

        repo.checkout("slice")
        repo.git("merge", "--no-ff", "-m", "merge main into slice", "main")
        head = repo.rev()
        self.assertEqual(repo.rev("HEAD^1"), branch_tip)

        proc = self.run_gate(repo, new_base, head, verify=verify)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)

    def test_conflict_resolution_in_a_frozen_test_fails(self):
        repo = self.new_repo("conflict")
        repo.write("src/slice.py", "base\n")
        repo.write("tests/test_frozen.py", "base\n")
        base = repo.commit("base")

        repo.checkout("-b", "slice")
        repo.write(
            ".rizzstack/lease.json",
            json.dumps(
                {
                    "source_rev": base,
                    "scope": {"assigned_files": ["src/slice.py"], "test_files": ["tests/test_frozen.py"]},
                    "verify_sha": base,
                }
            ),
        )
        repo.write("tests/test_frozen.py", "slice side\n")
        verify = repo.commit("slice edits the test before verify")

        repo.checkout("main")
        repo.write("tests/test_frozen.py", "main side\n")
        new_base = repo.commit("main edits the same test")

        repo.checkout("slice")
        proc = subprocess.run(
            ["git", "-C", str(repo.path), "merge", "main"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0, "the fixture must produce a conflict")
        repo.write("tests/test_frozen.py", "resolution smuggled in\n")
        head = repo.commit("resolve the conflict by rewriting the frozen test")

        gate = self.run_gate(repo, new_base, head, verify=verify)

        self.assertEqual(gate.returncode, 1, gate.stdout + gate.stderr)
        self.assertIn("frozen test file 'tests/test_frozen.py'", gate.stdout)
        self.assertIn("by merge commit " + head[:12], gate.stdout)

    # -- event handling ---------------------------------------------------

    def test_push_event_is_a_no_op(self):
        repo = self.new_repo("push")
        repo.write("src/slice.py", "base\n")
        base = repo.commit("base")
        event = self.tmp / "push-event.json"
        event.write_text(json.dumps({"ref": "refs/heads/main", "after": base}))

        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo.path), str(event)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no pull request in this event", proc.stdout)


if __name__ == "__main__":
    unittest.main()
