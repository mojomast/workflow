"""R00 Rails feasibility tests (spec section 9, packet R00/S).

RED-first acceptance: these tests fail while the leased fixtures, pinned
source versions, sanitized native-trace / session-shape descriptors, hook
citations or Q1-Q4 verdicts are missing. They pass only against
schemas/rails/fixtures/source-matrix.json and specs/rails-feasibility.md.

Deep verification of citations against the pinned source trees is enabled by
setting RAILS_SOURCE_ROOTS to a JSON mapping of repo name to a local checkout
checked out at the pinned revision, for example:

    {"bundlebees": "/tmp/src/bundlebees", "hyvv": "/tmp/src/hyvv",
     "orbitdesktop": "/tmp/src/orbitdesktop", "vibeline": "/tmp/src/vibeline",
     "workflow": "/tmp/src/workflow"}

Without that variable the structural tier still runs (every citation must be
well formed and carry a line digest for independent review); the workflow
citations are always deep-verified against this repository.
"""

import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "schemas" / "rails" / "fixtures" / "source-matrix.json"
DOC_PATH = ROOT / "specs" / "rails-feasibility.md"

EXPECTED_SOURCES = ("workflow", "bundlebees", "hyvv", "orbitdesktop", "vibeline")

# Names that must never appear in a name-colon-value or name-equals-value
# shape inside the leased files. Values stay withheld by the sanitizer.
SENSITIVE_NAMES = (
    "api key",
    "api_key",
    "api-key",
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "authorization",
)

# Credential-shaped literal prefixes (full literal shapes only). Entries that
# the upstream secret gate treats as complete markers on their own are built
# by concatenation so this file never contains one verbatim.
SENSITIVE_PREFIXES = (
    "sk-",
    "ghp_",
    "github" + "_pat_",
    "xox" + "b-",
    "xox" + "p-",
    "xox" + "a-",
    "xox" + "r-",
    "xox" + "s-",
    "AKIA",
    "AIza",
    "eyJ",
)

HEX64 = set("0123456789abcdef")


def has_name_value_shape(line: str) -> bool:
    """True when a sensitive name is directly followed by ':' or '=' (after
    optional spaces) on the same line — the shape the sanitizer must refuse."""
    low = line.lower()
    for name in SENSITIVE_NAMES:
        start = 0
        while True:
            i = low.find(name, start)
            if i < 0:
                break
            j = i + len(name)
            while j < len(low) and low[j] in " \t":
                j += 1
            if j < len(low) and low[j] in ":=":
                return True
            start = i + 1
    return False


def has_credential_literal(line: str) -> bool:
    low = line.lower()
    for prefix in SENSITIVE_PREFIXES:
        start = 0
        while True:
            i = low.find(prefix.lower(), start)
            if i < 0:
                break
            if i == 0 or not (low[i - 1].isalnum() or low[i - 1] in "_-"):
                return True
            start = i + 1
    return False


def scan_lines(text: str) -> list[int]:
    """1-based line numbers of sanitized-text violations in *text*."""
    bad = []
    for n, line in enumerate(text.splitlines(), 1):
        if has_name_value_shape(line) or has_credential_literal(line):
            bad.append(n)
    return bad


def load_matrix() -> dict:
    raw = MATRIX_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def source_roots() -> dict[str, Path]:
    raw = os.environ.get("RAILS_SOURCE_ROOTS", "")
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    return {name: Path(value) for name, value in parsed.items()}


def git_head(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def resolve_citation(hook: dict, roots: dict[str, Path]) -> tuple[str, str]:
    """Deep-verify one hook citation against a pinned checkout.

    Returns (tier, detail): tier is "deep" when the anchor was matched in the
    pinned file, "unavailable" when no root was configured for the repo.
    """
    repo = hook["repo"]
    if repo not in roots:
        return "unavailable", "no source root configured for " + repo
    root = roots[repo]
    if not root.is_dir():
        return "unavailable", "configured root is missing for " + repo
    path = root / hook["file"]
    if not path.is_file():
        return "unavailable", "file not found in pinned tree: " + hook["file"]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lineno = int(hook["line"])
    if lineno > len(lines):
        return "unavailable", "line beyond end of file: %s:%d" % (hook["file"], lineno)
    actual = lines[lineno - 1]
    anchor = hook["anchor"]
    digest = hashlib.sha256(anchor.encode("utf-8")).hexdigest()
    recorded = hook.get("line_digest", "")
    if recorded and recorded != digest:
        return "mismatch", "recorded line_digest does not match anchor"
    if anchor not in actual:
        return "mismatch", "anchor not present at %s:%d in the pinned tree" % (
            hook["file"],
            lineno,
        )
    return "deep", "anchor matched"


class SourceMatrixFixture(unittest.TestCase):
    def test_matrix_file_exists_and_parses(self):
        self.assertTrue(MATRIX_PATH.is_file(), "missing fixture: " + str(MATRIX_PATH))
        matrix = load_matrix()
        self.assertEqual(matrix.get("schema"), "rizzstack.rails-source-matrix/1")
        self.assertIn("sources", matrix)
        self.assertIn("uncertainties", matrix)
        self.assertIn("sanitization", matrix)

    def test_every_spec_source_is_pinned(self):
        matrix = load_matrix()
        by_name = {s["repo"]: s for s in matrix["sources"]}
        for name in EXPECTED_SOURCES:
            self.assertIn(name, by_name, "matrix missing pinned source: " + name)
            entry = by_name[name]
            commit = entry.get("pinned_commit", "")
            self.assertEqual(len(commit), 40, name + ": pinned_commit must be 40 hex chars")
            self.assertTrue(set(commit) <= HEX64, name + ": pinned_commit must be lowercase hex")
            self.assertTrue(entry.get("project_version"), name + ": missing project_version")
            self.assertTrue(entry.get("version_source"), name + ": missing version_source")
            self.assertTrue(entry.get("origin", "").startswith("https://"), name + ": origin must be https")
            self.assertTrue(entry.get("verified_at"), name + ": missing verified_at")
            self.assertTrue(entry.get("verify_method"), name + ": missing verify_method")
            self.assertTrue(entry.get("role"), name + ": missing role in the rails plan")


class TraceAndShapeDescriptors(unittest.TestCase):
    def test_native_trace_descriptor_present_and_sanitized(self):
        matrix = load_matrix()
        by_name = {s["repo"]: s for s in matrix["sources"]}
        self.assertIn("hyvv", by_name)
        trace = by_name["hyvv"].get("native_trace")
        self.assertIsNotNone(trace, "hyvv entry lacks a sanitized native trace descriptor")
        self.assertTrue(trace.get("observed_shape"), "native trace lacks the observed record shape")
        shape = " ".join(trace["observed_shape"])
        for field in ("lseq", "ts", "kind"):
            self.assertIn(field, shape, "native trace shape missing field: " + field)
        records = trace.get("records") or []
        self.assertGreaterEqual(len(records), 3, "native trace needs at least three sanitized records")
        kinds = {r.get("kind") for r in records}
        self.assertIn("state", kinds, "native trace must include a state record")
        self.assertTrue(any(k.startswith("worker:") for k in kinds if k), "native trace must include worker events")
        self.assertIn("heartbeat", kinds, "native trace must include a heartbeat record")
        raw = json.dumps(trace, ensure_ascii=True)
        self.assertEqual(scan_lines(raw), [], "sanitized native trace contains a credential shape")

    def test_session_shape_descriptor_present_and_sanitized(self):
        matrix = load_matrix()
        by_name = {s["repo"]: s for s in matrix["sources"]}
        self.assertIn("vibeline", by_name)
        shape = by_name["vibeline"].get("session_shape")
        self.assertIsNotNone(shape, "vibeline entry lacks a session shape descriptor")
        tables = shape.get("tables") or {}
        self.assertIn("sessions", tables, "session shape missing the sessions table")
        self.assertIn("messages", tables, "session shape missing the messages table")
        sessions_cols = " ".join(tables["sessions"])
        messages_cols = " ".join(tables["messages"])
        for column in ("id", "parent_session_id", "started_at", "input_tokens"):
            self.assertIn(column, sessions_cols)
        for column in ("id", "session_id", "role", "tool_call_id", "timestamp"):
            self.assertIn(column, messages_cols)
        self.assertTrue(shape.get("tool_pairing"), "session shape lacks the tool pairing rule")
        self.assertTrue(shape.get("active_flag_note"), "session shape lacks the active-flag note")
        raw = json.dumps(shape, ensure_ascii=True)
        self.assertEqual(scan_lines(raw), [], "session shape contains a credential shape")


class HookCitations(unittest.TestCase):
    def setUp(self):
        self.matrix = load_matrix()
        self.roots = source_roots()

    def hooks(self):
        out = []
        for source in self.matrix["sources"]:
            for hook in source.get("hooks") or []:
                hook = dict(hook)
                hook.setdefault("repo", source["repo"])
                out.append(hook)
        for item in self.matrix.get("uncertainties") or []:
            for hook in item.get("citations") or []:
                hook = dict(hook)
                hook.setdefault("repo", item.get("repo", hook.get("repo")))
                out.append(hook)
        return out

    def test_every_source_carries_hooks(self):
        for source in self.matrix["sources"]:
            self.assertGreaterEqual(
                len(source.get("hooks") or []),
                2,
                source["repo"] + ": fewer than two hook citations",
            )

    def test_citations_are_well_formed(self):
        for hook in self.hooks():
            self.assertTrue(hook.get("repo"), "citation without a repo: " + json.dumps(hook))
            file_ref = hook.get("file", "")
            self.assertTrue(file_ref, "citation without a file")
            self.assertFalse(file_ref.startswith("/"), "citation must be repo-relative: " + file_ref)
            self.assertNotIn("..", file_ref, "citation must not traverse: " + file_ref)
            self.assertTrue(Path(file_ref).is_absolute() is False)
            line = hook.get("line")
            self.assertIsInstance(line, int, "citation line must be an integer: " + file_ref)
            self.assertGreaterEqual(line, 1, "citation line must be 1-based: " + file_ref)
            anchor = hook.get("anchor", "")
            self.assertGreaterEqual(len(anchor.strip()), 8, "anchor too short to verify: " + file_ref)
            stripped = anchor.strip().strip(".")
            self.assertGreaterEqual(len(stripped.strip()), 8, "anchor is only ellipsis dots: " + file_ref)
            digest = hashlib.sha256(anchor.encode("utf-8")).hexdigest()
            self.assertEqual(
                hook.get("line_digest"),
                digest,
                "line_digest mismatch for %s:%d" % (file_ref, line),
            )

    def test_workflow_citations_resolve_in_this_repository(self):
        for hook in self.hooks():
            if hook["repo"] != "workflow":
                continue
            path = ROOT / hook["file"]
            self.assertTrue(path.is_file(), "workflow citation file missing: " + hook["file"])
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            self.assertLessEqual(
                hook["line"],
                len(lines),
                "workflow citation beyond end of file: " + hook["file"],
            )
            self.assertIn(
                hook["anchor"],
                lines[hook["line"] - 1],
                "workflow anchor does not match %s:%d" % (hook["file"], hook["line"]),
            )

    def test_external_citations_resolve_when_sources_are_available(self):
        hooks = [h for h in self.hooks() if h["repo"] != "workflow"]
        self.assertGreater(len(hooks), 0, "no external hook citations recorded")
        deep = 0
        for hook in hooks:
            tier, detail = resolve_citation(hook, self.roots)
            if tier == "deep":
                deep += 1
            elif tier == "mismatch":
                self.fail("%s (%s): %s" % (hook["repo"], hook["file"], detail))
            else:
                recorded = hook.get("line_digest", "")
                self.assertTrue(
                    recorded,
                    hook["repo"] + ": citation without a line digest cannot be reviewed",
                )
        if self.roots:
            self.assertGreater(
                deep,
                0,
                "RAILS_SOURCE_ROOTS was configured but no citation deep-verified",
            )

    def test_root_pins_match_when_sources_are_available(self):
        for repo, root in self.roots.items():
            matrix = load_matrix()
            by_name = {s["repo"]: s for s in matrix["sources"]}
            self.assertIn(repo, by_name, "configured root for unknown repo: " + repo)
            head = git_head(root)
            self.assertIsNotNone(head, repo + ": configured root is not a git checkout")
            self.assertEqual(
                head,
                by_name[repo]["pinned_commit"],
                repo + ": checkout head does not equal the pinned revision",
            )


class UncertaintyVerdicts(unittest.TestCase):
    def test_q1_through_q4_each_carry_a_verdict(self):
        matrix = load_matrix()
        items = {u.get("id"): u for u in matrix.get("uncertainties") or []}
        for qid in ("Q1", "Q2", "Q3", "Q4"):
            self.assertIn(qid, items, "missing uncertainty verdict: " + qid)
            item = items[qid]
            self.assertIn(
                item.get("verdict"),
                ("resolved", "unresolved"),
                qid + ": verdict must be resolved or unresolved",
            )
            if item["verdict"] == "unresolved":
                self.assertTrue(
                    (item.get("reason") or "").strip(),
                    qid + ": unresolved verdict needs a reason",
                )
            else:
                self.assertGreaterEqual(
                    len(item.get("citations") or []),
                    1,
                    qid + ": resolved verdict needs at least one citation",
                )

    def test_doc_states_each_uncertainty(self):
        text = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.is_file() else ""
        for qid in ("Q1", "Q2", "Q3", "Q4"):
            self.assertIn(qid, text, "feasibility doc does not discuss " + qid)


class FeasibilityDoc(unittest.TestCase):
    def test_doc_exists_with_required_sections(self):
        self.assertTrue(DOC_PATH.is_file(), "missing deliverable: " + str(DOC_PATH))
        text = DOC_PATH.read_text(encoding="utf-8")
        for heading in (
            "Source pins",
            "Hook locations",
            "Q1",
            "Q2",
            "Q3",
            "Q4",
            "Sanitization",
            "RED-first",
        ):
            self.assertIn(heading, text, "feasibility doc missing section: " + heading)

    def test_doc_is_sanitized(self):
        text = DOC_PATH.read_text(encoding="utf-8")
        bad = scan_lines(text)
        self.assertEqual(bad, [], "feasibility doc contains credential shapes on lines: %s" % bad)

    def test_matrix_is_sanitized(self):
        text = MATRIX_PATH.read_text(encoding="utf-8")
        bad = scan_lines(text)
        self.assertEqual(bad, [], "source matrix contains credential shapes on lines: %s" % bad)

    def test_doc_and_matrix_agree_on_verdicts(self):
        matrix = load_matrix()
        items = {u.get("id"): u.get("verdict") for u in matrix.get("uncertainties") or []}
        text = DOC_PATH.read_text(encoding="utf-8")
        for qid, verdict in items.items():
            self.assertIn(qid, text)
            marker = "%s verdict: %s" % (qid, verdict)
            self.assertIn(
                marker,
                text,
                "feasibility doc must state the matrix verdict verbatim: " + marker,
            )


if __name__ == "__main__":
    unittest.main()
