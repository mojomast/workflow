"""Tests for the umbrella modularity spec (docs/modularity.md + profiles/).

What these tests can verify offline, against THIS checkout only:

- the five install-profile manifests plus repos.json parse and carry the
  required structure (components, env, ports, auth posture, cannot-do list);
- every component named in a profile is one of the four elements listed in
  repos.json (workflow, hyvv, bundlebees, orbitdesktop);
- every in-repo path a profile references actually exists in this checkout;
- every revision pin recorded in repos.json is literally present in at least
  one cited source file in this checkout, so pins are recorded evidence, not
  aspiration;
- the five quickstarts exist, match their profile ids, and point back at the
  bundles;
- docs/modularity.md and docs/profiles.md exist and cross-link the bundles.

What these tests cannot verify offline: the content of the four element
repositories themselves (mojomast/hyvv, mojomast/bundlebees,
mojomast/orbitdesktop) is not checked out in this workspace. Cross-repo
module names and endpoints used by the profiles are cited from the workflow
chapters that were written against those trees (docs/13, docs/22, docs/23);
the citation paths are what this suite checks.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = REPO_ROOT / "profiles"
QUICKSTART_DIR = REPO_ROOT / "docs" / "quickstarts"

PROFILE_IDS = ["contracts", "full", "observer", "orchestrator", "worker"]
ELEMENT_NAMES = {"workflow", "hyvv", "bundlebees", "orbitdesktop"}

PROFILE_REQUIRED_KEYS = {
    "profile",
    "description",
    "components",
    "env",
    "ports",
    "auth_posture",
    "cannot_do",
    "refs",
}

COMPONENT_REQUIRED_KEYS = {"repo", "role", "required", "why"}
ENV_REQUIRED_KEYS = {"name", "set_by", "required"}
REF_REQUIRED_KEYS = {"path", "kind", "exists_in_repo"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def profile_path(profile_id: str) -> Path:
    return PROFILES_DIR / f"{profile_id}.json"


def iter_refs(refs):
    for ref in refs:
        yield ref


# ---------------------------------------------------------------- repos.json


def test_repos_json_parses_and_lists_exactly_the_four_elements():
    doc = load_json(PROFILES_DIR / "repos.json")
    repos = doc["repos"]
    assert set(repos) == ELEMENT_NAMES
    for name, entry in repos.items():
        assert entry["url"].startswith("https://github.com/mojomast/"), name
        assert entry["role"], name
        assert entry["depends_on"] is not None, name
        for pin in entry["pins"]:
            assert pin["ref"], name
            assert pin["source"], name


def test_dependency_direction_points_down_only():
    doc = load_json(PROFILES_DIR / "repos.json")
    repos = doc["repos"]
    # The protocol depends on nothing; the control surface depends on nothing
    # from the protocol at runtime; the executor depends on the protocol and
    # the worker host; nothing depends upward on Orbit.
    assert repos["workflow"]["depends_on"] == []
    assert "workflow" not in repos["hyvv"]["depends_on"]
    assert set(repos["bundlebees"]["depends_on"]) == {"workflow", "hyvv"}
    assert "orbitdesktop" not in json.dumps(repos["bundlebees"]["depends_on"])


# ------------------------------------------------------------ profile shapes


def test_all_five_profile_manifests_parse_with_required_keys():
    for profile_id in PROFILE_IDS:
        doc = load_json(profile_path(profile_id))
        assert doc["profile"] == profile_id, profile_id
        missing = PROFILE_REQUIRED_KEYS - set(doc)
        assert not missing, f"{profile_id} missing {sorted(missing)}"
        assert doc["components"], profile_id
        assert doc["cannot_do"], profile_id
        assert doc["ports"], profile_id
        assert doc["auth_posture"], profile_id
        assert doc["env"] is not None, profile_id


def test_every_component_is_a_known_element_and_shape_is_complete():
    for profile_id in PROFILE_IDS:
        doc = load_json(profile_path(profile_id))
        for component in doc["components"]:
            missing = COMPONENT_REQUIRED_KEYS - set(component)
            assert not missing, f"{profile_id}: {sorted(missing)}"
            assert component["repo"] in ELEMENT_NAMES, component["repo"]
            assert isinstance(component["required"], bool)
            assert component["role"]
            assert component["why"]


def test_every_env_entry_declares_its_source_and_no_env_value_is_inlined():
    for profile_id in PROFILE_IDS:
        doc = load_json(profile_path(profile_id))
        for entry in doc["env"]:
            missing = ENV_REQUIRED_KEYS - set(entry)
            assert not missing, f"{profile_id}: {sorted(missing)}"
            assert entry["name"] == entry["name"].upper()
            # Values are provided at runtime, never written into the manifest.
            assert "value" not in entry, entry


def test_profile_refs_carry_verifiable_existence_flags():
    for profile_id in PROFILE_IDS:
        doc = load_json(profile_path(profile_id))
        for ref in doc["refs"]:
            missing = REF_REQUIRED_KEYS - set(ref)
            assert not missing, f"{profile_id}: {sorted(missing)}"
            assert ref["kind"] in {"in_repo_path", "other_repo_module", "doc_chapter", "profile_bundle"}
            assert isinstance(ref["exists_in_repo"], bool)


def test_in_repo_refs_exist_in_this_checkout():
    for profile_id in PROFILE_IDS:
        doc = load_json(profile_path(profile_id))
        for ref in doc["refs"]:
            if ref["exists_in_repo"]:
                target = REPO_ROOT / ref["path"]
                assert target.exists(), f"{profile_id}: {ref['path']}"


def test_doc_citations_point_at_files_that_exist():
    for profile_id in PROFILE_IDS:
        doc = load_json(profile_path(profile_id))
        for ref in doc["refs"]:
            if ref["kind"] == "doc_chapter":
                target = REPO_ROOT / ref["path"]
                assert target.exists(), f"{profile_id}: {ref['path']}"


# --------------------------------------------------------------- pinned refs


def test_every_pin_is_literally_recorded_in_a_cited_source():
    doc = load_json(PROFILES_DIR / "repos.json")
    for name, entry in doc["repos"].items():
        for pin in entry["pins"]:
            ref = pin["ref"]
            source = REPO_ROOT / pin["source"]
            assert source.exists(), f"{name}/{ref}: source {pin['source']} missing"
            assert ref in source.read_text(encoding="utf-8", errors="replace"), (
                f"pin {ref} for {name} not found in {pin['source']}"
            )


def test_full_length_pins_are_well_formed_hex():
    doc = load_json(PROFILES_DIR / "repos.json")
    for entry in doc["repos"].values():
        for pin in entry["pins"]:
            ref = pin["ref"]
            if 7 < len(ref) <= 64:
                assert re.fullmatch(r"[0-9a-f]{8,64}", ref), ref


# --------------------------------------------------------------- quickstarts


def test_quickstart_exists_for_every_profile_and_links_its_bundle():
    for profile_id in PROFILE_IDS:
        path = QUICKSTART_DIR / f"{profile_id}.md"
        assert path.exists(), path
        text = path.read_text(encoding="utf-8")
        assert f"profiles/{profile_id}.json" in text, profile_id
        assert "cannot" in text.lower(), profile_id


def test_quickstarts_only_reference_in_repo_paths_that_exist():
    # Bare repo-relative paths mentioned in fenced shell blocks must exist,
    # when they name a file this checkout carries.
    known_prefixes = ("reference/", "acceptance/", "contrib/", "tools/", "docs/", "profiles/", "schemas/", "templates/", "observability/")
    for profile_id in PROFILE_IDS:
        text = (QUICKSTART_DIR / f"{profile_id}.md").read_text(encoding="utf-8")
        for token in re.findall(r"`([a-zA-Z0-9_./-]+)`", text):
            if token.startswith(known_prefixes) and not token.endswith("/"):
                candidate = REPO_ROOT / token
                if "." in Path(token).name or (REPO_ROOT / token).is_dir():
                    assert candidate.exists(), f"{profile_id}: {token}"


# ----------------------------------------------------------------- doc pages


def test_modularity_doc_exists_and_covers_the_four_elements():
    text = (REPO_ROOT / "docs" / "modularity.md").read_text(encoding="utf-8")
    for name in sorted(ELEMENT_NAMES):
        assert name in text, name
    for heading in ["requires", "optional", "minimum viable", "gaps"]:
        assert heading in text.lower(), heading


def test_profiles_doc_points_at_every_bundle():
    text = (REPO_ROOT / "docs" / "profiles.md").read_text(encoding="utf-8")
    for profile_id in PROFILE_IDS:
        assert f"../profiles/{profile_id}.json" in text, profile_id


def test_every_profile_bundle_links_back_to_docs():
    for profile_id in PROFILE_IDS:
        doc = load_json(profile_path(profile_id))
        assert any(
            ref["kind"] == "doc_chapter" or ref["kind"] == "profile_bundle"
            for ref in doc["refs"]
        ), profile_id
