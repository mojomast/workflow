"""Contract tests for the owner-held resolver (scripts/owner_held.py).

Both events are covered with fixtures:

- ``pull_request``: labels come from the payload, with and without the
  ``owner-held`` label (plus a near-miss label that must not match);
- ``pull_request_review``: the same payload read on a submitted review, which
  re-runs ``ci-gate`` and therefore must re-evaluate the hold;
- ``merge_group``: the queued pull request is resolved from
  ``github.event.merge_group.head_sha`` through the commit -> pulls API, with and
  without the ``owner-held`` label, plus the fail-closed paths (API error,
  missing token, no pull request and no queue ref);
- a ``push`` to main is a no-op pass, so ``ci-gate`` still passes on main.

The module under test is ``scripts/owner_held.py`` by default. Set
``OWNER_HELD_SCRIPT`` to point the same suite at a vendored copy
(``.github/scripts/owner_held.py``) in another repository.
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(os.environ.get("OWNER_HELD_SCRIPT") or ROOT / "scripts" / "owner_held.py").resolve()
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "owner_held"
COMMIT_API = "https://api.github.com/repos/mojomast/fixture/commits/%s/pulls?per_page=100"
HELD_SHA = "3f7c1a9d2b4e5f60718293a4b5c6d7e8f9012345"
CLEAR_SHA = "4a8d2b0e3c5f6172839405a6b7c8d9e0f0123456"
FALLBACK_SHA = "6c0f4d2a5e718293a4b5c6d7e8f9012345678abc"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_path(name):
    return FIXTURES / name


def cli_env(event_name, extra_env=None):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_REPOSITORY": "mojomast/fixture",
        "GITHUB_TOKEN": "fixture-token",
    }
    env.update(extra_env or {})
    return env


def run_cli(payload_path, event_name, extra_env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(payload_path)],
        capture_output=True,
        text=True,
        timeout=60,
        env=cli_env(event_name, extra_env),
    )


def load_module():
    spec = importlib.util.spec_from_file_location("owner_held_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeApi:
    """Fixture-backed transport: maps URL -> payload (or an exception to raise)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, token):
        self.calls.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected API call: {url}")
        payload = self.routes[url]
        if isinstance(payload, Exception):
            raise payload
        return payload, ""


def run_merge_group(payload_path, api, token="fixture-token"):
    module = load_module()
    env = cli_env("merge_group")
    env["GITHUB_TOKEN"] = token
    return module.main([str(payload_path)], env=env, http=api)


class PullRequestEventTests(unittest.TestCase):
    def test_owner_held_label_fails_and_prints_labels(self):
        proc = run_cli(fixture_path("pull_request_held.json"), "pull_request")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("pull_request #42 labels: ci, owner-held", proc.stdout)
        self.assertIn("owner-held is present", proc.stdout)

    def test_without_owner_held_label_passes(self):
        proc = run_cli(fixture_path("pull_request_clear.json"), "pull_request")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("pull_request #43 labels: ci, docs", proc.stdout)
        self.assertIn("pass; no owner-held label", proc.stdout)

    def test_label_match_is_exact_not_a_substring(self):
        proc = run_cli(fixture_path("pull_request_similar_label.json"), "pull_request")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("owner-held-adjacent", proc.stdout)
        self.assertIn("pass; no owner-held label", proc.stdout)

    def test_missing_payload_fails_closed(self):
        proc = run_cli(FIXTURES / "does-not-exist.json", "pull_request")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot read event payload", proc.stderr)


class PullRequestReviewEventTests(unittest.TestCase):
    """A submitted review re-runs ci-gate, so it must re-evaluate the hold.

    The review payload carries the same pull request object (labels included)
    plus a ``review.commit_id`` that is not the head; the hold is decided by the
    labels on ``pull_request``, and treating the event as "no pull request to
    hold" would let an owner-held pull request go green by adding a review.
    """

    def test_owner_held_label_on_a_review_event_fails(self):
        proc = run_cli(fixture_path("pull_request_review_held.json"), "pull_request_review")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("pull_request #42 labels: ci, owner-held", proc.stdout)
        self.assertIn("owner-held is present", proc.stdout)

    def test_review_event_without_owner_held_label_passes(self):
        proc = run_cli(fixture_path("pull_request_review_clear.json"), "pull_request_review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("pull_request #43 labels: ci, docs", proc.stdout)
        self.assertIn("pass; no owner-held label", proc.stdout)

    def test_event_name_is_inferred_from_a_review_payload_when_unset(self):
        env = cli_env("pull_request_review")
        env.pop("GITHUB_EVENT_NAME")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(fixture_path("pull_request_review_held.json"))],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("event=pull_request_review", proc.stdout)
        self.assertIn("owner-held is present", proc.stdout)


class MergeGroupEventTests(unittest.TestCase):
    def test_queued_pull_request_labelled_owner_held_fails(self):
        api = FakeApi({COMMIT_API % HELD_SHA: fixture("api_commit_pulls_held.json")})
        self.assertEqual(run_merge_group(fixture_path("merge_group_held.json"), api), 1)
        self.assertEqual(len(api.calls), 1)
        self.assertIn(f"commits/{HELD_SHA}/pulls", api.calls[0])

    def test_queued_pull_request_output_is_checked(self):
        api = FakeApi({COMMIT_API % HELD_SHA: fixture("api_commit_pulls_held.json")})
        module = load_module()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = module.main([str(fixture_path("merge_group_held.json"))], env=cli_env("merge_group"), http=api)
        self.assertEqual(code, 1)
        self.assertIn("merge_group #42 labels: ci, owner-held", buffer.getvalue())

    def test_queued_pull_request_without_owner_held_passes(self):
        api = FakeApi({COMMIT_API % CLEAR_SHA: fixture("api_commit_pulls_clear.json")})
        self.assertEqual(run_merge_group(fixture_path("merge_group_clear.json"), api), 0)

    def test_api_failure_fails_closed(self):
        url = COMMIT_API % HELD_SHA
        api = FakeApi({url: urllib.error.HTTPError(url, 500, "server error", Message(), None)})
        self.assertEqual(run_merge_group(fixture_path("merge_group_held.json"), api), 1)

    def test_unreachable_api_fails_closed(self):
        proc = run_cli(
            fixture_path("merge_group_clear.json"),
            "merge_group",
            extra_env={"GITHUB_API_URL": "http://127.0.0.1:9"},
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("fail closed", proc.stderr)

    def test_missing_token_fails_closed(self):
        api = FakeApi({})
        self.assertEqual(run_merge_group(fixture_path("merge_group_clear.json"), api, token=""), 1)
        self.assertEqual(api.calls, [])

    def test_commit_without_pull_requests_falls_back_to_the_queue_ref(self):
        api = FakeApi(
            {
                COMMIT_API % FALLBACK_SHA: fixture("api_commit_pulls_empty.json"),
                "https://api.github.com/repos/mojomast/fixture/pulls/45": fixture("api_pull_45_held.json"),
            }
        )
        self.assertEqual(run_merge_group(fixture_path("merge_group_fallback.json"), api), 1)
        self.assertEqual(len(api.calls), 2)

    def test_commit_without_pull_requests_or_queue_ref_fails_closed(self):
        api = FakeApi({COMMIT_API % FALLBACK_SHA: fixture("api_commit_pulls_empty.json")})
        payload = fixture("merge_group_fallback.json")
        payload["merge_group"]["head_ref"] = "refs/heads/gh-readonly-queue/main"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merge_group_no_ref.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(run_merge_group(path, api), 1)


class OtherEventTests(unittest.TestCase):
    def test_push_to_main_is_a_noop_pass(self):
        proc = run_cli(fixture_path("push_main.json"), "push")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no pull request to hold for event=push; pass", proc.stdout)


class VendoredCopyTests(unittest.TestCase):
    def test_vendored_copy_matches_the_canonical_script(self):
        canonical = (ROOT / "scripts" / "owner_held.py").read_bytes()
        vendored = (ROOT / ".github" / "scripts" / "owner_held.py").read_bytes()
        self.assertEqual(canonical, vendored, "re-vendor .github/scripts/owner_held.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
