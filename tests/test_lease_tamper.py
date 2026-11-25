"""Tests for .github/scripts/lease_tamper.py.

Every case builds a real temporary git repository and drives the real CLI, so
the checks are proven against git history rather than mocked diffs.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def new_git_repo(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return GitRepo(path)


def build_slice(
    root,
    verify=True,
    assigned=("src/slice.py",),
    test_files=("tests/test_frozen.py",),
    prohibited=(),
    contract_path=".rizzstack/lease.json",
):
    """Build a base commit, a slice branch with a lease, and an implementation."""
    repo = new_git_repo(root)
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


class LeaseTamperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lease-tamper-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- fixtures ---------------------------------------------------------

    def new_repo(self, name="repo"):
        return new_git_repo(self.tmp / name)

    def make_slice(
        self,
        name="repo",
        verify=True,
        assigned=("src/slice.py",),
        test_files=("tests/test_frozen.py",),
        prohibited=(),
        contract_path=".rizzstack/lease.json",
    ):
        return build_slice(
            self.tmp / name,
            verify=verify,
            assigned=assigned,
            test_files=test_files,
            prohibited=prohibited,
            contract_path=contract_path,
        )

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

        env = dict(os.environ)
        env.pop("GITHUB_EVENT_NAME", None)
        env.pop("GITHUB_EVENT_PATH", None)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo.path), str(event)],
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no pull request in this event", proc.stdout)


# -- lease source: base branch or frozen store, never the PR branch ---------


def lease_hash(document):
    """The frozen-contract identity: sorted compact JSON without ``review``."""
    body = {key: value for key, value in document.items() if key != "review"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LeaseSourceTests(unittest.TestCase):
    """The lease is judged from trusted storage, not from the pull request.

    A pull request can edit any file on its branch, including its lease, so the
    gate resolves the lease from the base branch (tip or merge-base) or from a
    frozen contract store keyed by contract hash.  A branch-only lease fails
    with ``lease_not_on_base``.  The only exception is a repository whose base
    has no gate yet: the pull request that introduces the gate bootstraps.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lease-source-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(
        self,
        name="repo",
        gate_on_base=True,
        lease_on_base=True,
        assigned=("src/slice.py", "src/other_leased.py"),
        test_files=("tests/test_frozen.py",),
    ):
        """Base commit(s), a slice branch, and the hashes the tests need."""
        repo = new_git_repo(self.tmp / name)
        repo.write("src/slice.py", "base\n")
        repo.write("src/other_leased.py", "base\n")
        repo.write("tests/test_frozen.py", "base\n")
        repo.write("src/unleased.py", "base\n")
        repo.write("README.md", "base\n")
        if gate_on_base:
            repo.write(".github/scripts/lease_tamper.py", "# the gate already exists on base\n")
        root = repo.commit("base")

        lease = {
            "id": "slice",
            "source_rev": root,
            "scope": {
                "assigned_files": list(assigned),
                "test_files": list(test_files),
            },
        }
        base = root
        if lease_on_base:
            repo.write(".rizzstack/leases/slice.json", json.dumps(lease, indent=2) + "\n")
            base = repo.commit("land the slice lease on base")

        repo.checkout("-b", "slice")
        repo.write("src/slice.py", "implementation\n")
        verify = repo.commit("implement the slice")
        return types.SimpleNamespace(
            repo=repo, root=root, base=base, verify=verify, lease=lease
        )

    def run_gate(self, repo, base, head, body=None, labels=None, verify=None, stores=None):
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
        if body:
            command += ["--body", body]
        if labels:
            command += ["--labels", labels]
        if verify:
            command += ["--verify-sha", verify]
        for store in stores or []:
            command += ["--contract-store", str(store)]
        env = dict(os.environ)
        env.pop("BUNDLEBEES_CONTRACT_STORE", None)
        env.pop("GITHUB_EVENT_PATH", None)
        env.pop("GITHUB_EVENT_NAME", None)
        return subprocess.run(command, capture_output=True, text=True, env=env)

    # -- the five required behaviours -------------------------------------

    def test_lease_on_base_passes(self):
        fixture = self.build()
        repo = fixture.repo
        repo.write("src/other_leased.py", "follow-up inside the lease\n")
        head = repo.commit("follow-up inside the lease")

        proc = self.run_gate(
            repo,
            fixture.base,
            head,
            body="Lease-Contract: .rizzstack/leases/slice.json\n",
            verify=fixture.verify,
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)
        self.assertIn(".rizzstack/leases/slice.json", proc.stdout)

    def test_lease_only_on_branch_fails_lease_not_on_base(self):
        fixture = self.build(name="branch-only", lease_on_base=False)
        repo = fixture.repo
        # The slice adds its own lease to the branch, exactly what the rule forbids.
        repo.write(".rizzstack/leases/slice.json", json.dumps(fixture.lease, indent=2) + "\n")
        head = repo.commit("add the lease on the branch")

        proc = self.run_gate(
            repo,
            fixture.base,
            head,
            body="Lease-Contract: .rizzstack/leases/slice.json\n",
            verify=fixture.verify,
        )

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("reason=lease_not_on_base", proc.stdout)
        self.assertIn("exists only on PR head", proc.stdout)
        self.assertIn("may not supply or edit the lease", proc.stdout)

    def test_frozen_store_resolves_lease_by_contract_hash(self):
        fixture = self.build(name="store", lease_on_base=False)
        store = self.tmp / "frozen-contracts"
        store.mkdir()
        digest = lease_hash(fixture.lease)
        (store / (digest + ".json")).write_text(
            json.dumps(fixture.lease, indent=2) + "\n", encoding="utf-8"
        )
        repo = fixture.repo
        head = fixture.verify

        proc = self.run_gate(
            repo,
            fixture.base,
            head,
            body="Lease-Contract-Sha256: " + digest + "\n",
            stores=[store],
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)
        self.assertIn("frozen contract store", proc.stdout)

    def test_merge_from_base_touching_nothing_leased_passes(self):
        fixture = self.build(name="merge-clean")
        repo = fixture.repo
        branch_tip = fixture.verify

        repo.checkout("main")
        repo.write("src/other_leased.py", "main moved a leased file\n")
        repo.write("src/unleased.py", "main moved an unleased file\n")
        repo.write("README.md", "main moved the readme\n")
        new_base = repo.commit("main moves on")

        repo.checkout("slice")
        repo.git("merge", "--no-ff", "-m", "merge main into slice", "main")
        head = repo.rev()
        self.assertEqual(repo.rev("HEAD^1"), branch_tip)

        proc = self.run_gate(
            repo,
            new_base,
            head,
            body="Lease-Contract: .rizzstack/leases/slice.json\n",
            verify=branch_tip,
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lease-tamper: OK:", proc.stdout)

    def test_merge_from_base_touching_a_frozen_test_fails(self):
        fixture = self.build(name="merge-frozen")
        repo = fixture.repo
        branch_tip = fixture.verify

        repo.checkout("main")
        repo.write("tests/test_frozen.py", "main relaxes the frozen test\n")
        new_base = repo.commit("main edits the frozen test")

        repo.checkout("slice")
        repo.git("merge", "--no-ff", "-m", "merge main into slice", "main")
        head = repo.rev()

        proc = self.run_gate(
            repo,
            new_base,
            head,
            body="Lease-Contract: .rizzstack/leases/slice.json\n",
            verify=branch_tip,
        )

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("frozen test file 'tests/test_frozen.py'", proc.stdout)
        self.assertIn("by merge commit " + head[:12], proc.stdout)

    # -- the security property behind the rule ---------------------------

    def test_a_lease_edited_on_the_branch_is_ignored_and_the_base_lease_applies(self):
        fixture = self.build(name="edited")
        repo = fixture.repo
        widened = dict(fixture.lease)
        widened["scope"] = dict(fixture.lease["scope"])
        widened["scope"]["assigned_files"] = ["src/slice.py", "src/unleased.py"]
        repo.write(".rizzstack/leases/slice.json", json.dumps(widened, indent=2) + "\n")
        repo.write("src/unleased.py", "sneaky follow-up\n")
        head = repo.commit("widen the lease on the branch and use it")

        proc = self.run_gate(
            repo,
            fixture.base,
            head,
            body="Lease-Contract: .rizzstack/leases/slice.json\n",
            verify=fixture.verify,
        )

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("'src/unleased.py' is outside the slice lease", proc.stdout)

    def test_bootstrap_branch_lease_passes_when_base_has_no_gate(self):
        fixture = self.build(name="bootstrap", gate_on_base=False, lease_on_base=False)
        repo = fixture.repo
        repo.write(".rizzstack/leases/slice.json", json.dumps(fixture.lease, indent=2) + "\n")
        head = repo.commit("introduce the gate and its lease")

        proc = self.run_gate(
            repo,
            fixture.base,
            head,
            body="Lease-Contract: .rizzstack/leases/slice.json\n",
            verify=fixture.verify,
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("bootstrap mode", proc.stdout)

    def test_path_and_hash_together_must_agree(self):
        fixture = self.build(name="path-and-hash")
        head = fixture.verify
        body = (
            "Lease-Contract: .rizzstack/leases/slice.json\n"
            "Lease-Contract-Sha256: " + lease_hash(fixture.lease) + "\n"
        )

        proc = self.run_gate(fixture.repo, fixture.base, head, body=body, verify=head)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_named_contract_hash_that_does_not_match_the_base_lease_fails(self):
        fixture = self.build(name="mismatch")
        head = fixture.verify
        wrong = "0" * 64

        proc = self.run_gate(
            repo=fixture.repo,
            base=fixture.base,
            head=head,
            body="Lease-Contract-Sha256: " + wrong + "\n",
            verify=fixture.verify,
        )

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("no matching lease", proc.stdout)

    def test_frozen_store_file_named_by_hash_must_hash_to_that_name(self):
        fixture = self.build(name="store-mismatch", lease_on_base=False)
        store = self.tmp / "frozen-mismatch"
        store.mkdir()
        wrong = "f" * 64
        (store / (wrong + ".json")).write_text(
            json.dumps(fixture.lease, indent=2) + "\n", encoding="utf-8"
        )

        proc = self.run_gate(
            repo=fixture.repo,
            base=fixture.base,
            head=fixture.verify,
            body="Lease-Contract-Sha256: " + wrong + "\n",
            stores=[store],
        )

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("is not the contract with hash", proc.stdout)


# -- merge_queue -----------------------------------------------------------

QUEUE_REPO = "owner/repo"


class FakeGitHubApi:
    """A loopback stand-in for the GitHub endpoints the gate uses.

    Real HTTP through urllib is exercised, so the tests cover the path a runner
    takes: authorization header, JSON decoding, 404/500 handling.
    """

    def __init__(self):
        self.pulls = {}
        self.commit_pulls = {}
        self.check_runs = {}
        self.status = {}
        self.requests = []
        self.authorizations = []
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                api.requests.append(self.path)
                api.authorizations.append(self.headers.get("Authorization") or "")
                status, payload = api.respond(self.path)
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def add_check_run(self, sha, conclusion="success", status="completed"):
        self.check_runs.setdefault(sha, []).append(
            {"name": "lease-tamper", "head_sha": sha, "status": status, "conclusion": conclusion}
        )

    def respond(self, path):
        clean = (path or "").split("?")[0]
        if clean in self.status:
            return self.status[clean], {"message": "forced by the test"}
        parts = clean.strip("/").split("/")
        if len(parts) < 5 or parts[0] != "repos":
            return 404, {"message": "no route for " + clean}
        if parts[3] == "pulls":
            return self._pull(parts)
        if parts[3] == "commits":
            return self._commit(parts)
        return 404, {"message": "no route for " + clean}

    def _pull(self, parts):
        number = int(parts[4]) if len(parts) == 5 else 0
        if number in self.pulls:
            return 200, self.pulls[number]
        return 404, {"message": "Not Found"}

    def _commit(self, parts):
        if len(parts) != 6:
            return 404, {"message": "bad commit path"}
        sha, kind = parts[4], parts[5]
        if kind == "pulls":
            return 200, self.commit_pulls.get(sha, [])
        if kind == "check-runs":
            runs = self.check_runs.get(sha, [])
            return 200, {"total_count": len(runs), "check_runs": runs}
        return 404, {"message": "bad commit route"}

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class MergeGroupTests(unittest.TestCase):
    """merge_group: prove per pull request that the reviewed head passed here."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lease-tamper-queue-"))
        self.api = FakeGitHubApi()

    def tearDown(self):
        self.api.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build_stack(self, numbers=(69,), red=(), head_ref=None, move_base=True):
        """Build a queue group stacking ``numbers`` in order, newest last.

        The group is a real merge chain: base (moved on), merge entry 1, merge
        entry 2 -- the shape GitHub builds for a stacked queue group.
        """
        repo = new_git_repo(self.tmp / "queue")
        repo.write("README.md", "base\n")
        repo.write("src/unleased.py", "base\n")
        base = repo.commit("base")
        current = base
        entries = []
        for number in numbers:
            repo.git("checkout", "-b", "pr-%d" % number, current)
            repo.write("src/slice_%d.py" % number, "implementation %d\n" % number)
            pr_head = repo.commit("implement #%d" % number)
            pull = {
                "number": number,
                "head": {"sha": pr_head},
                "base": {"sha": current},
                "labels": [],
                "body": "",
            }
            self.api.pulls[number] = pull
            self.api.commit_pulls[pr_head] = [pull]
            self.api.add_check_run(pr_head, conclusion="failure" if number in red else "success")
            entries.append({"number": number, "head": pr_head})
            current = pr_head

        repo.git("checkout", "main")
        if move_base:
            repo.write("README.md", "main moved after the pull requests opened\n")
            repo.commit("main moves on")
        base_tip = repo.rev()
        for entry in entries:
            repo.git(
                "merge", "--no-ff", "-m", "merge group entry #%d" % entry["number"], entry["head"]
            )
        head = repo.rev()

        if head_ref is None:
            head_ref = "refs/heads/gh-readonly-queue/main/pr-%d-%s" % (numbers[-1], head)
        event = self.tmp / "merge-group.json"
        event.write_text(
            json.dumps(
                {
                    "merge_group": {
                        "head_sha": head,
                        "head_ref": head_ref,
                        "base_sha": base_tip,
                        "base_ref": "refs/heads/main",
                    }
                }
            )
        )
        return types.SimpleNamespace(repo=repo, event=event, head=head, base=base_tip, entries=entries)

    def run_gate(self, queue, token="test-token"):
        env = dict(os.environ)
        env.pop("GITHUB_EVENT_PATH", None)
        env.pop("GH_TOKEN", None)
        env["GITHUB_EVENT_NAME"] = "merge_group"
        env["GITHUB_REPOSITORY"] = QUEUE_REPO
        env["GITHUB_API_URL"] = self.api.url
        if token is None:
            env.pop("GITHUB_TOKEN", None)
        else:
            env["GITHUB_TOKEN"] = token
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(queue.repo.path), str(queue.event)],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_single_pr_group_passes(self):
        queue = self.build_stack(numbers=(69,))

        proc = self.run_gate(queue)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(
            "merge_group: PR #69 head %s is in group head %s"
            % (queue.entries[0]["head"][:12], queue.head[:12]),
            proc.stdout,
        )
        self.assertIn("lease-tamper: OK: 1 pull request(s)", proc.stdout)
        self.assertNotIn("::notice", proc.stdout)

    def test_stacked_group_checks_every_pull_request(self):
        queue = self.build_stack(numbers=(69, 70))

        proc = self.run_gate(queue)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PR #69", proc.stdout)
        self.assertIn("PR #70", proc.stdout)
        self.assertIn("2 pull request(s)", proc.stdout)
        self.assertTrue(any("pulls/69" in request for request in self.api.requests))
        self.assertTrue(any("pulls/70" in request for request in self.api.requests))

    def test_stacked_group_fails_when_an_earlier_entry_is_not_green(self):
        queue = self.build_stack(numbers=(69, 70), red=(69,))

        proc = self.run_gate(queue)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("reason=merge_group_pr_unresolved", proc.stdout)
        self.assertIn("[not-green-at-head] pull request #69", proc.stdout)

    def test_unresolvable_branch_name_fails_merge_group_pr_unresolved(self):
        queue = self.build_stack(
            numbers=(69,), head_ref="refs/heads/gh-readonly-queue/main/candidate-deadbeef"
        )

        proc = self.run_gate(queue)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("reason=merge_group_pr_unresolved", proc.stdout)
        self.assertIn("[no-pr-in-ref]", proc.stdout)
        self.assertIn("::error title=lease-tamper merge_group_pr_unresolved::", proc.stdout)
        self.assertNotIn("SKIPPED", proc.stdout)
        self.assertNotIn("::notice", proc.stdout)

    def test_pull_request_head_moved_after_its_pull_request_run_fails(self):
        queue = self.build_stack(numbers=(69,))
        repo = queue.repo
        repo.git("checkout", "pr-69")
        repo.write("src/slice_69.py", "pushed after the pull_request run\n")
        moved = repo.commit("push after the gate ran")
        self.api.pulls[69]["head"]["sha"] = moved

        proc = self.run_gate(queue)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("[head-moved] stacked entry", proc.stdout)
        self.assertIn("belongs to pull request #69", proc.stdout)
        self.assertIn("reason=merge_group_pr_unresolved", proc.stdout)

    def test_no_green_lease_tamper_at_the_reviewed_head_fails(self):
        queue = self.build_stack(numbers=(69,), red=(69,))

        proc = self.run_gate(queue)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("[not-green-at-head] pull request #69", proc.stdout)
        self.assertIn("reason=merge_group_pr_unresolved", proc.stdout)

    def test_api_failure_is_a_failure_not_a_skip(self):
        queue = self.build_stack(numbers=(69,))
        self.api.status["/repos/%s/pulls/69" % QUEUE_REPO] = 500
        self.api.status[
            "/repos/%s/commits/%s/pulls" % (QUEUE_REPO, queue.entries[0]["head"])
        ] = 502

        proc = self.run_gate(queue)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("reason=merge_group_pr_unresolved", proc.stdout)
        self.assertNotIn("SKIPPED", proc.stdout)

    def test_missing_token_fails_merge_group_pr_unresolved(self):
        queue = self.build_stack(numbers=(69,))

        proc = self.run_gate(queue, token=None)

        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("[no-credentials]", proc.stdout)
        self.assertIn("reason=merge_group_pr_unresolved", proc.stdout)


if __name__ == "__main__":
    unittest.main()
