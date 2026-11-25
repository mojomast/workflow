"""DiskVault conformance tests for rizzstack.memory/1.

These are the oracle's ``Vault``-level scenarios ported onto a real vault
directory. All digest, validation, injection and expiry helpers come from the
normative oracle (``tests/test_memory_contract.py``); nothing is forked here.

Each scenario is a module-level helper that builds a ``tempfile``-backed vault
and returns the evidence (receipts, envelopes, parsed log lines, on-disk text).
The unittest classes assert the contract behavior, and ``HelperLevelTests``
exercises the same helpers plus the package's serialisation/digest/zone
primitives directly.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rizzstack_memory import (  # noqa: E402
    DiskVault,
    ContractError,
    memory_sha,
    parse_memory,
    serialize_memory,
)
from rizzstack_memory import vault as vault_mod  # noqa: E402
from tests.test_memory_contract import (  # noqa: E402
    CONTRACT,
    LATER,
    MAX_EXCERPT_CHARS,
    MAX_ITEMS,
    MAX_SNIPPET_CHARS,
    MAX_TOTAL_CHARS,
    MEMORY_TYPES,
    NOW,
    TYPE_DIR,
    TYPE_POLICY,
    WORKED_BODY,
    WRITER,
    ContractError as OracleContractError,
    Vault,
    base_record,
    excerpt_of as oracle_excerpt_of,
    grant,
    inject_brief,
    is_expired,
    quarantine_prefix,
    resolve_mode as oracle_resolve_mode,
    sealed,
    validate_injection,
    validate_query_op as oracle_validate_query_op,
    validate_query_result,
    write_op,
    zone_of,
)

QUERY_BODIES = (
    "# Workbench crash resume\n\nA workbench crash mid-wave leaves a stale lease behind.\n\n- Resume from the recovery digest, never from chat scrollback.\n",
    "# Lease recovery notes\n\nThe lease file must be re-read before the next wave; the workbench resumes cleanly.\n",
    "# Naming conventions\n\nA quiet note about naming conventions for receipts.\n",
)


# ---------------------------------------------------------------------------
# Helpers and scenarios (the "helper level").
# ---------------------------------------------------------------------------


def typed_record(memory_type: str, memory_id: str, body: str = None, **retention) -> dict:
    record = base_record(
        id=memory_id,
        type=memory_type,
        retention={"policy": TYPE_POLICY[memory_type], "expires": None, "superseded_by": None, **retention},
    )
    return sealed(record, body)


def read_log_lines(root) -> list:
    text = (Path(root) / "log.md").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def scenario_create_then_update(root) -> dict:
    vault = DiskVault(root)
    path = quarantine_prefix(WRITER) + "workbench-crash-resume.md"
    first = vault.write(write_op(path=path))
    first_read = vault.read(path, expected_sha=first["sha"])
    updated = sealed()
    updated["modified"] = LATER
    updated["sha"] = memory_sha(updated, WORKED_BODY)
    second = vault.write(write_op(path=path, expected=first["sha"], record=updated))
    second_read = vault.read(path)
    return {
        "vault": vault,
        "path": path,
        "first": first,
        "second": second,
        "first_read": first_read,
        "second_read": second_read,
        "raw": (Path(root) / path).read_text(encoding="utf-8"),
        "log": read_log_lines(root),
    }


def scenario_stale_digest(root) -> dict:
    vault = DiskVault(root)
    path = quarantine_prefix(WRITER) + "workbench-crash-resume.md"
    first = vault.write(write_op(path=path))
    stale = sealed()
    stale["modified"] = LATER
    stale["sha"] = memory_sha(stale, WORKED_BODY)
    envelope = vault.write_envelope(write_op(path=path, expected="1" * 64, record=stale, authority=grant()))
    return {
        "vault": vault,
        "path": path,
        "first": first,
        "envelope": envelope,
        "after": vault.read(path),
        "raw": (Path(root) / path).read_text(encoding="utf-8"),
        "log": read_log_lines(root),
    }


def scenario_duplicate_id(root) -> dict:
    vault = DiskVault(root)
    first_path = quarantine_prefix(WRITER) + "workbench-crash-resume.md"
    twin_path = quarantine_prefix(WRITER) + "twin.md"
    first = vault.write(write_op(path=first_path))
    envelope = vault.write_envelope(write_op(path=twin_path))
    return {
        "vault": vault,
        "first": first,
        "envelope": envelope,
        "twin_exists": (Path(root) / twin_path).exists(),
        "log": read_log_lines(root),
    }


def scenario_quarantine_and_grants(root) -> dict:
    vault = DiskVault(root)
    own_path = quarantine_prefix(WRITER) + "own-notes.md"
    own = vault.write(write_op(path=own_path, record=typed_record("learning", "own-notes")))
    ungranted = vault.write_envelope(
        write_op(path="learnings/ungranted.md", record=typed_record("learning", "ungranted"))
    )
    foreign = vault.write_envelope(
        write_op(path=quarantine_prefix("agent:bee-9") + "notes.md", record=typed_record("learning", "foreign-notes"))
    )
    reviewed_path = "learnings/granted-learning.md"
    reviewed = vault.write(
        write_op(
            path=reviewed_path,
            record=typed_record("learning", "granted-learning"),
            authority=grant(approved_by="orbit:coordinator"),
        )
    )
    return {
        "vault": vault,
        "own": own,
        "own_path": own_path,
        "ungranted": ungranted,
        "foreign": foreign,
        "reviewed": reviewed,
        "reviewed_path": reviewed_path,
        "log": read_log_lines(root),
    }


def curated_fixtures() -> dict:
    return {
        "concepts/retrieval-basics.md": sealed(
            base_record(
                id="retrieval-basics",
                type="reference",
                retention={"policy": "reference-refresh", "expires": LATER, "superseded_by": None},
            )
        ),
        "decisions/vault-zones.md": sealed(
            base_record(
                id="vault-zones",
                type="decision",
                retention={"policy": "decision-permanent", "expires": None, "superseded_by": None},
            )
        ),
        "hot.md": sealed(base_record(id="always-resume-from-digest")),
        "index.md": sealed(
            base_record(
                id="vault-index",
                type="reference",
                retention={"policy": "reference-refresh", "expires": LATER, "superseded_by": None},
            )
        ),
    }


def scenario_curated_grants(root) -> dict:
    vault = DiskVault(root)
    fixtures = curated_fixtures()
    bot_envelopes = {}
    accepted = {}
    bootstrap_hot = (Path(root) / "hot.md").read_text(encoding="utf-8")
    bootstrap_index = (Path(root) / "index.md").read_text(encoding="utf-8")
    for path, record in fixtures.items():
        bot_envelopes[path] = vault.write_envelope(
            write_op(path=path, record=record, authority=grant(approved_by="orbit:coordinator"))
        )
    hot_after_bot = (Path(root) / "hot.md").read_text(encoding="utf-8")
    index_after_bot = (Path(root) / "index.md").read_text(encoding="utf-8")
    for path, record in fixtures.items():
        accepted[path] = vault.write(write_op(path=path, record=record, authority=grant()))
    return {
        "vault": vault,
        "bot_envelopes": bot_envelopes,
        "accepted": accepted,
        "records": {path: vault.read(path)["record"] for path in fixtures},
        "bootstrap_hot": bootstrap_hot,
        "bootstrap_index": bootstrap_index,
        "hot_after_bot": hot_after_bot,
        "index_after_bot": index_after_bot,
        "log": read_log_lines(root),
    }


def scenario_service_owned(root) -> dict:
    vault = DiskVault(root)
    paths = ("log.md", "VAULT.md", "sessions/2026-11-14-workbench-crash.md")
    envelopes = {path: vault.write_envelope(write_op(path=path, authority=grant())) for path in paths}
    return {
        "vault": vault,
        "paths": paths,
        "envelopes": envelopes,
        "log_text": (Path(root) / "log.md").read_text(encoding="utf-8"),
    }


def scenario_type_and_path_refusals(root) -> dict:
    vault = DiskVault(root)
    wrong_dir = vault.write_envelope(
        write_op(
            path="decisions/workbench-crash-resume.md",
            record=typed_record("learning", "workbench-crash-resume"),
            authority=grant(),
        )
    )
    dot_segment = vault.write_envelope(
        write_op(path=quarantine_prefix(WRITER) + "../escape.md", record=typed_record("learning", "escape"))
    )
    mismatched = vault.write_envelope(
        write_op(path=quarantine_prefix(WRITER) + "bad.md", record=base_record(sha="0" * 64))
    )
    return {
        "vault": vault,
        "wrong_dir": wrong_dir,
        "dot_segment": dot_segment,
        "sha_mismatch": mismatched,
        "wrong_file_exists": (Path(root) / "decisions" / "workbench-crash-resume.md").exists(),
        "escape_exists": (Path(root) / ".quarantine" / "agent-bee-7" / "escape.md").exists(),
    }


def scenario_expiry(root) -> dict:
    vault = DiskVault(root)
    prefix = quarantine_prefix(WRITER)
    active = vault.write(
        write_op(path=prefix + "active.md", record=typed_record("learning", "active-learning"))
    )
    stale = vault.write(
        write_op(
            path=prefix + "stale.md",
            record=typed_record("reference", "stale-reference", expires="2026-01-01T00:00:00Z"),
        )
    )
    superseded = vault.write(
        write_op(
            path=prefix + "superseded.md",
            record=typed_record("learning", "superseded-learning", superseded_by="newer-learning"),
        )
    )
    active_default = vault.active_records(NOW)
    active_all = vault.active_records(NOW, include_expired=True)
    hidden = vault.query({"op": "query", "q": "workbench"}, now=NOW)
    shown = vault.query({"op": "query", "q": "workbench", "include_expired": True}, now=NOW)
    return {
        "vault": vault,
        "writes": (active, stale, superseded),
        "active_default": active_default,
        "active_all": active_all,
        "hidden": hidden,
        "shown": shown,
    }


def scenario_query_and_injection(root) -> dict:
    vault = DiskVault(root)
    prefix = quarantine_prefix(WRITER)
    receipts = []
    for index, body in enumerate(QUERY_BODIES):
        memory_id = f"query-memory-{index}"
        record = typed_record("learning", memory_id, body)
        receipts.append(vault.write(write_op(path=prefix + f"query-{index}.md", record=record, body=body)))
    result = vault.query({"op": "query", "q": "workbench crash lease", "k": 2, "mode": "hybrid"}, now=NOW)
    ranked = []
    for hit in result["hits"]:
        entry = vault.read(hit["path"])
        ranked.append({"record": entry["record"], "body": entry["body"], "path": hit["path"], "score": hit["score"]})
    payload = inject_brief(ranked, vault_rev=result["vault_rev"])
    filtered = vault.query({"op": "query", "q": "naming", "types": ["learning"], "k": 1}, now=NOW)
    semantic_fallback = vault.query({"op": "query", "q": "lease", "mode": "semantic"}, now=NOW)
    return {
        "vault": vault,
        "receipts": receipts,
        "result": result,
        "ranked": ranked,
        "payload": payload,
        "filtered": filtered,
        "semantic_fallback": semantic_fallback,
    }


def scenario_all_types(root) -> dict:
    vault = DiskVault(root)
    written = {}
    for memory_type in MEMORY_TYPES:
        memory_id = f"{memory_type}-fixture"
        retention = {"policy": TYPE_POLICY[memory_type], "expires": None, "superseded_by": None}
        if memory_type == "reference":
            retention["expires"] = LATER
        record = sealed(base_record(id=memory_id, type=memory_type, retention=retention))
        path = f"{TYPE_DIR[memory_type]}/{memory_id}.md"
        receipt = vault.write(write_op(path=path, record=record, authority=grant()))
        entry = vault.read(path)
        written[memory_type] = {
            "path": path,
            "record": record,
            "receipt": receipt,
            "read": entry,
            "raw": (Path(root) / path).read_text(encoding="utf-8"),
        }
    return {"vault": vault, "written": written, "log": read_log_lines(root)}


def scenario_reopen(root) -> dict:
    first_vault = DiskVault(root)
    path = quarantine_prefix(WRITER) + "durable.md"
    first = first_vault.write(write_op(path=path, record=typed_record("learning", "durable-memory")))
    rev_one = first_vault.vault_rev
    second_vault = DiskVault(root)
    rev_reopened = second_vault.vault_rev
    updated = typed_record("learning", "durable-memory")
    updated["modified"] = LATER
    updated["sha"] = memory_sha(updated, WORKED_BODY)
    second = second_vault.write(write_op(path=path, expected=first["sha"], record=updated))
    return {
        "first_vault": first_vault,
        "second_vault": second_vault,
        "first": first,
        "second": second,
        "rev_one": rev_one,
        "rev_reopened": rev_reopened,
        "log": read_log_lines(root),
    }


def scenario_read_drift(root) -> dict:
    vault = DiskVault(root)
    path = quarantine_prefix(WRITER) + "drift.md"
    receipt = vault.write(write_op(path=path, record=typed_record("learning", "drift-memory")))
    fresh = vault.read(path, expected_sha=receipt["sha"])
    drifted = vault.read(path, expected_sha="f" * 64)
    try:
        vault.read(quarantine_prefix(WRITER) + "missing.md")
    except ContractError as err:
        missing = err
    else:  # pragma: no cover - a missing memory must refuse
        missing = None
    return {"vault": vault, "receipt": receipt, "fresh": fresh, "drifted": drifted, "missing": missing}


def scenario_bootstrap(root) -> dict:
    vault = DiskVault(root)
    return {
        "vault": vault,
        "exists": {name: (Path(root) / name).exists() for name in ("VAULT.md", "index.md", "hot.md", "log.md")},
        "log_text": (Path(root) / "log.md").read_text(encoding="utf-8"),
        "rev": vault.vault_rev,
        "rulebook": (Path(root) / "VAULT.md").read_text(encoding="utf-8"),
    }


def scenario_oracle_parity(root) -> dict:
    """Run the same write sequence against the in-memory oracle and DiskVault."""
    oracle = Vault()
    disk = DiskVault(root)
    own_path = quarantine_prefix(WRITER) + "parity.md"
    reference = typed_record("reference", "parity-ref", expires=LATER)
    first_record = typed_record("learning", "parity-memory")
    steps = [
        (
            "own-create",
            write_op(path=own_path, record=first_record),
        ),
        (
            "ungranted-reviewed",
            write_op(path="learnings/parity-ungranted.md", record=typed_record("learning", "parity-ungranted")),
        ),
        ("service-owned", write_op(path="log.md", record=typed_record("learning", "parity-log"), authority=grant())),
        (
            "curated-bot-grant",
            write_op(path="concepts/parity-ref.md", record=reference, authority=grant(approved_by="orbit:coordinator")),
        ),
        (
            "type-dir-mismatch",
            write_op(path="decisions/parity-wrong.md", record=typed_record("learning", "parity-wrong"), authority=grant()),
        ),
        (
            "blind-overwrite",
            write_op(path=own_path, record=first_record),
        ),
    ]
    comparisons = []
    for label, op in steps:
        expected = oracle.write_envelope(op)
        actual = disk.write_envelope(op)
        comparisons.append((label, expected, actual))
    updated = typed_record("learning", "parity-memory")
    updated["modified"] = LATER
    updated["sha"] = memory_sha(updated, WORKED_BODY)
    first_sha = oracle.files[own_path]["record"]["sha"]
    for label, op in (
        ("granted-update", write_op(path=own_path, expected=first_sha, record=updated)),
        (
            "duplicate-id",
            write_op(path=quarantine_prefix(WRITER) + "twin.md", expected=None, record=updated),
        ),
        (
            "id-mismatch",
            write_op(
                path=own_path,
                expected=updated["sha"],
                record=typed_record("learning", "other-memory"),
            ),
        ),
        (
            "self-inconsistent-digest",
            write_op(path=own_path, record=base_record(sha="0" * 64)),
        ),
    ):
        expected = oracle.write_envelope(op)
        actual = disk.write_envelope(op)
        comparisons.append((label, expected, actual))
    return {
        "oracle": oracle,
        "disk": disk,
        "comparisons": comparisons,
        "oracle_log": oracle.log,
        "disk_log": disk.receipts(),
    }


# ---------------------------------------------------------------------------
# Unittest-class level: the oracle's Vault-level scenarios on disk.
# ---------------------------------------------------------------------------


class BootstrapDiskTests(unittest.TestCase):
    def test_an_empty_root_bootstraps_the_service_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_bootstrap(tmp)
            self.assertTrue(all(evidence["exists"].values()))
            self.assertEqual(evidence["log_text"], "")
            self.assertEqual(evidence["rev"], "gen-0")
            self.assertIn("rizzstack.memory/1", evidence["rulebook"])
            self.assertIn("service-owned", evidence["rulebook"])

    def test_bootstrap_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = scenario_bootstrap(tmp)
            second = scenario_bootstrap(tmp)
            self.assertEqual(first["rulebook"], second["rulebook"])
            self.assertEqual(first["rev"], second["rev"])


class ShaGuardDiskTests(unittest.TestCase):
    def test_create_then_update_round_trips_at_the_contract_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_create_then_update(tmp)
            self.assertTrue(evidence["first"]["accepted"])
            self.assertEqual(evidence["first"]["log_seq"], 1)
            self.assertEqual(evidence["second"]["log_seq"], 2)
            self.assertTrue(Path(tmp, evidence["path"]).is_file())
            record, body = parse_memory(evidence["raw"])
            self.assertEqual(record["id"], "workbench-crash-resume")
            self.assertEqual(record["type"], "learning")
            self.assertEqual(body, WORKED_BODY)
            self.assertEqual(record["sha"], memory_sha(record, body))
            self.assertEqual(evidence["second_read"]["record"]["sha"], record["sha"])
            self.assertEqual(evidence["vault"].vault_rev, "gen-2")
            self.assertEqual([entry["seq"] for entry in evidence["log"]], [1, 2])

    def test_a_stale_digest_is_refused_with_current_sha_and_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_stale_digest(tmp)
            envelope = evidence["envelope"]
            self.assertFalse(envelope["accepted"])
            self.assertEqual(envelope["code"], "sha_conflict")
            self.assertTrue(envelope["reread_required"])
            self.assertEqual(envelope["current_sha"], evidence["first"]["sha"])
            self.assertEqual(evidence["after"]["record"]["sha"], evidence["first"]["sha"])
            self.assertEqual(len(evidence["log"]), 1)
            self.assertEqual(evidence["vault"].vault_rev, "gen-1")

    def test_a_blind_overwrite_and_a_create_with_a_digest_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            path = quarantine_prefix(WRITER) + "blind.md"
            first = vault.write(write_op(path=path, record=typed_record("learning", "blind-memory")))
            blind = vault.write_envelope(write_op(path=path, record=typed_record("learning", "blind-memory")))
            self.assertEqual(blind["code"], "sha_conflict")
            self.assertTrue(blind["reread_required"])
            self.assertEqual(blind["current_sha"], first["sha"])
            create_with_digest = vault.write_envelope(
                write_op(
                    path=quarantine_prefix(WRITER) + "new.md",
                    record=typed_record("learning", "new-memory"),
                    expected="0" * 64,
                )
            )
            self.assertEqual(create_with_digest["code"], "sha_conflict")
            self.assertIsNone(create_with_digest["current_sha"])

    def test_duplicate_ids_are_refused_across_the_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_duplicate_id(tmp)
            self.assertEqual(evidence["envelope"]["code"], "duplicate_id")
            self.assertFalse(evidence["twin_exists"])
            self.assertEqual(len(evidence["log"]), 1)

    def test_a_self_inconsistent_digest_is_refused_before_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = DiskVault(tmp)
            path = quarantine_prefix(WRITER) + "bad.md"
            envelope = vault.write_envelope(write_op(path=path, record=base_record(sha="0" * 64)))
            self.assertEqual(envelope["code"], "sha_mismatch")
            self.assertFalse(Path(tmp, path).exists())
            self.assertEqual(vault.receipts(), [])


class QuarantineGrantDiskTests(unittest.TestCase):
    def test_quarantine_subtrees_and_grants_match_the_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_quarantine_and_grants(tmp)
            self.assertTrue(evidence["own"]["accepted"])
            self.assertTrue(Path(tmp, evidence["own_path"]).is_file())
            self.assertEqual(evidence["ungranted"]["code"], "write_quarantined")
            self.assertEqual(evidence["foreign"]["code"], "write_quarantined")
            self.assertTrue(evidence["reviewed"]["accepted"])
            self.assertTrue(Path(tmp, evidence["reviewed_path"]).is_file())
            self.assertTrue(evidence["log"][-1]["granted"])
            self.assertEqual([entry["seq"] for entry in evidence["log"]], [1, 2])

    def test_curated_zones_require_a_human_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_curated_grants(tmp)
            for path, envelope in evidence["bot_envelopes"].items():
                self.assertEqual(envelope["code"], "write_bad_grant", path)
            self.assertEqual(evidence["hot_after_bot"], evidence["bootstrap_hot"])
            self.assertEqual(evidence["index_after_bot"], evidence["bootstrap_index"])
            for path, record in evidence["records"].items():
                self.assertEqual(record["id"], curated_fixtures()[path]["id"], path)
            self.assertEqual(evidence["vault"].vault_rev, "gen-4")

    def test_service_owned_paths_are_never_written_through_the_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_service_owned(tmp)
            for path, envelope in evidence["envelopes"].items():
                self.assertEqual(envelope["code"], "service_owned", path)
            self.assertFalse((Path(tmp) / "sessions" / "2026-11-14-workbench-crash.md").exists())
            self.assertEqual(evidence["log_text"], "")
            self.assertEqual(evidence["vault"].vault_rev, "gen-0")

    def test_type_dir_mismatch_dot_segments_and_digests_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_type_and_path_refusals(tmp)
            self.assertEqual(evidence["wrong_dir"]["code"], "schema_invalid")
            self.assertEqual(evidence["dot_segment"]["code"], "schema_invalid")
            self.assertEqual(evidence["sha_mismatch"]["code"], "sha_mismatch")
            self.assertFalse(evidence["wrong_file_exists"])
            self.assertFalse(evidence["escape_exists"])


class RetentionDiskTests(unittest.TestCase):
    def test_expiry_hides_superseded_and_deadline_passed_memories(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_expiry(tmp)
            self.assertEqual([record["id"] for record in evidence["active_default"]], ["active-learning"])
            self.assertEqual(len(evidence["active_all"]), 3)
            self.assertEqual([hit["id"] for hit in evidence["hidden"]["hits"]], ["active-learning"])
            self.assertEqual(len(evidence["shown"]["hits"]), 3)

    def test_active_records_uses_the_oracle_expiry_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_expiry(tmp)
            by_id = {record["id"]: record for record in evidence["active_all"]}
            self.assertFalse(is_expired(by_id["active-learning"], NOW))
            self.assertTrue(is_expired(by_id["stale-reference"], NOW))
            self.assertTrue(is_expired(by_id["superseded-learning"], NOW))
            self.assertEqual(len(evidence["vault"].active_records(LATER)), 1)
            self.assertEqual(len(evidence["vault"].active_records(LATER, include_expired=True)), 3)


class QueryDiskTests(unittest.TestCase):
    def test_query_returns_a_validated_grep_result_and_feeds_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_query_and_injection(tmp)
            result = evidence["result"]
            self.assertEqual(validate_query_result(result), result)
            self.assertEqual(result["op"], "query-result")
            self.assertEqual(result["mode_used"], "grep")
            self.assertEqual(result["vault_rev"], evidence["vault"].vault_rev)
            self.assertEqual(len(result["hits"]), 2)
            self.assertEqual(result["hits"][0]["id"], "query-memory-0")
            for hit in result["hits"]:
                self.assertLessEqual(len(hit["snippet"]), MAX_SNIPPET_CHARS)
                self.assertEqual(hit["sha"], evidence["vault"].read(hit["path"])["record"]["sha"])
            payload = evidence["payload"]
            self.assertEqual(validate_injection(payload), payload)
            self.assertEqual(payload["vault_rev"], result["vault_rev"])
            self.assertLessEqual(len(payload["items"]), MAX_ITEMS)
            self.assertLessEqual(sum(len(item["excerpt"]) for item in payload["items"]), MAX_TOTAL_CHARS)
            for item in payload["items"]:
                self.assertLessEqual(len(item["excerpt"]), MAX_EXCERPT_CHARS)
                self.assertTrue(item["excerpt"])

    def test_query_filters_types_and_semantic_falls_back_to_grep(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_query_and_injection(tmp)
            self.assertEqual(evidence["filtered"]["mode_used"], "grep")
            self.assertEqual(len(evidence["filtered"]["hits"]), 1)
            self.assertEqual(evidence["filtered"]["hits"][0]["id"], "query-memory-2")
            self.assertEqual(evidence["semantic_fallback"]["mode_used"], "grep")
            self.assertTrue(all(hit["type"] == "learning" for hit in evidence["filtered"]["hits"]))


class EveryTypeDiskTests(unittest.TestCase):
    def test_every_memory_type_round_trips_at_its_contract_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_all_types(tmp)
            for memory_type, item in evidence["written"].items():
                path = item["path"]
                self.assertEqual(path, f"{TYPE_DIR[memory_type]}/{memory_type}-fixture.md")
                self.assertTrue(Path(tmp, path).is_file(), path)
                self.assertEqual(item["receipt"]["path"], path)
                self.assertEqual(item["receipt"]["sha"], memory_sha(item["record"], WORKED_BODY))
                self.assertEqual(item["read"]["record"], item["record"])
                self.assertEqual(item["read"]["body"], WORKED_BODY)
                stored, body = parse_memory(item["raw"])
                self.assertEqual(stored["sha"], memory_sha(stored, body))
                self.assertEqual(stored["type"], memory_type)
                self.assertEqual(stored["retention"]["policy"], TYPE_POLICY[memory_type])
            self.assertEqual([item["receipt"]["log_seq"] for item in evidence["written"].values()], list(range(1, 7)))
            self.assertEqual(evidence["vault"].vault_rev, "gen-6")
            self.assertEqual([entry["seq"] for entry in evidence["log"]], list(range(1, 7)))


class ReopenDiskTests(unittest.TestCase):
    def test_log_sequence_and_vault_rev_survive_a_fresh_vault_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_reopen(tmp)
            self.assertEqual(evidence["rev_one"], "gen-1")
            self.assertEqual(evidence["rev_reopened"], "gen-1")
            self.assertEqual(evidence["second"]["log_seq"], 2)
            self.assertEqual(evidence["second_vault"].vault_rev, "gen-2")
            self.assertEqual([entry["seq"] for entry in evidence["log"]], [1, 2])
            self.assertEqual(evidence["log"][0]["sha"], evidence["first"]["sha"])


class ReadDiskTests(unittest.TestCase):
    def test_read_warns_when_expected_sha_drifted(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_read_drift(tmp)
            self.assertFalse(evidence["fresh"]["drift"])
            self.assertIsNone(evidence["fresh"]["warning"])
            self.assertTrue(evidence["drifted"]["drift"])
            self.assertIn("changed", evidence["drifted"]["warning"])
            self.assertEqual(evidence["drifted"]["current_sha"], evidence["receipt"]["sha"])
            self.assertEqual(evidence["drifted"]["record"]["id"], "drift-memory")
            self.assertIsNotNone(evidence["missing"])
            self.assertEqual(evidence["missing"].code, "not_found")


class OracleParityDiskTests(unittest.TestCase):
    def test_write_envelopes_receipts_and_log_match_the_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_oracle_parity(tmp)
            for label, expected, actual in evidence["comparisons"]:
                self.assertEqual(actual["accepted"], expected["accepted"], label)
                if expected["accepted"]:
                    for key in ("id", "sha", "path", "log_seq"):
                        self.assertEqual(actual[key], expected[key], f"{label}:{key}")
                else:
                    self.assertEqual(actual["code"], expected["code"], label)
                    self.assertEqual(actual["reread_required"], expected["reread_required"], label)
                    self.assertEqual(actual["current_sha"], expected["current_sha"], label)
            self.assertEqual(evidence["disk_log"], evidence["oracle_log"])


# ---------------------------------------------------------------------------
# Helper level: the same scenarios plus the package primitives, directly.
# ---------------------------------------------------------------------------


class HelperLevelTests(unittest.TestCase):
    def test_scenario_helpers_return_disk_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_all_types(tmp)
            self.assertEqual(set(evidence["written"]), set(MEMORY_TYPES))
            self.assertEqual(len(evidence["log"]), len(MEMORY_TYPES))
            for item in evidence["written"].values():
                self.assertEqual(set(item), {"path", "record", "receipt", "read", "raw"})
                self.assertEqual(item["receipt"]["accepted"], True)

    def test_the_package_digest_matches_the_oracle(self):
        for i, memory_type in enumerate(MEMORY_TYPES):
            record = typed_record(memory_type, f"digest-{i}", body=WORKED_BODY)
            self.assertEqual(memory_sha(record, WORKED_BODY), record["sha"])
            self.assertEqual(vault_mod.memory_sha(record, WORKED_BODY), record["sha"])

    def test_frontmatter_round_trip_is_byte_stable(self):
        record = sealed()
        record["sources"][0]["note"] = 'operator: diagnosis "narration"\nsecond line'
        record["sha"] = memory_sha(record, WORKED_BODY)
        text = serialize_memory(record, WORKED_BODY)
        parsed_record, parsed_body = parse_memory(text)
        self.assertEqual(parsed_record, record)
        self.assertEqual(parsed_body, WORKED_BODY)
        self.assertEqual(serialize_memory(parsed_record, parsed_body), text)

    def test_zone_and_quarantine_helpers_match_the_oracle(self):
        paths = (
            "concepts/x.md",
            "decisions/x.md",
            "hot.md",
            "index.md",
            "entities/x.md",
            "learnings/x.md",
            "pitfalls/x.md",
            "projects/x.md",
            ".quarantine/agent-bee-7/x.md",
            "sessions/x.md",
            "VAULT.md",
            "log.md",
            "notes.md",
        )
        for path in paths:
            self.assertEqual(vault_mod.zone_of(path), zone_of(path), path)
        self.assertEqual(vault_mod.quarantine_prefix(WRITER), quarantine_prefix(WRITER))

    def test_expiry_helper_matches_the_oracle(self):
        cases = (
            (typed_record("decision", "a-decision"), NOW),
            (
                typed_record("learning", "a-learning", superseded_by="newer-learning"),
                NOW,
            ),
            (typed_record("reference", "a-reference", expires=LATER), NOW),
            (typed_record("pitfall", "a-pitfall", expires=NOW), LATER),
        )
        for record, now in cases:
            self.assertEqual(vault_mod.is_expired(record, now), is_expired(record, now), record["id"])

    def test_scenario_limit_and_cap_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_query_and_injection(tmp)
            payload = evidence["payload"]
            self.assertLessEqual(payload["caps"]["max_items"], MAX_ITEMS)
            self.assertLessEqual(payload["caps"]["max_excerpt_chars"], MAX_EXCERPT_CHARS)
            self.assertLessEqual(payload["caps"]["max_total_chars"], MAX_TOTAL_CHARS)
            self.assertEqual(payload["contract"], CONTRACT)

    def test_query_result_hits_carry_the_contract_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = scenario_query_and_injection(tmp)
            for hit in evidence["result"]["hits"]:
                self.assertEqual(set(hit), {"id", "type", "path", "title", "sha", "score", "snippet"})
                self.assertIsInstance(hit["score"], float)
                self.assertGreater(hit["score"], 0)

    def test_resolve_mode_and_excerpt_match_the_oracle(self):
        for requested in ("hybrid", "semantic", "keyword", "grep"):
            for has_fts5 in (False, True):
                for has_embeddings in (False, True):
                    self.assertEqual(
                        vault_mod.resolve_mode(requested, has_fts5, has_embeddings),
                        oracle_resolve_mode(requested, has_fts5, has_embeddings),
                        (requested, has_fts5, has_embeddings),
                    )
        long_body = "# Long tail\n" + ("A long confirmed observation. " * 60) + "\n"
        for body in (WORKED_BODY, long_body):
            for cap in (1, 10, MAX_EXCERPT_CHARS):
                self.assertEqual(vault_mod.excerpt_of(body, cap), oracle_excerpt_of(body, cap), cap)

    def test_query_op_and_result_refusals_match_the_oracle(self):
        bad_ops = (
            {},
            {"op": "query", "q": ""},
            {"op": "query", "q": "lease", "k": 99},
            {"op": "query", "q": "lease", "mode": "telepathy"},
            {"op": "query", "q": "lease", "types": ["bogus"]},
            {"op": "query", "q": "lease", "include_expired": "yes"},
        )
        for op in bad_ops:
            with self.assertRaises(OracleContractError) as expected:
                oracle_validate_query_op(op)
            with self.assertRaises(ContractError) as actual:
                vault_mod.validate_query_op(op)
            self.assertEqual(actual.exception.code, expected.exception.code, op)
        bad_result = {"op": "query-result", "mode_used": "telepathy", "hits": [], "vault_rev": "gen-0"}
        with self.assertRaises(OracleContractError) as expected:
            validate_query_result(bad_result)
        with self.assertRaises(ContractError) as actual:
            vault_mod.validate_query_result(bad_result)
        self.assertEqual(actual.exception.code, expected.exception.code)


if __name__ == "__main__":
    unittest.main()
