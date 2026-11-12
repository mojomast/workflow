"""Fill HANDOFF.md and RETURN.md from the repository templates."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    # reference/workflow/packets.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def templates_dir() -> Path:
    return repo_root() / "templates"


def _require_template(name: str) -> str:
    path = templates_dir() / name
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise FileNotFoundError(path)
    return text


def _replace_bullet(text: str, label: str, value: str) -> str:
    needle = f"- {label}"
    lines = text.splitlines()
    out = []
    found = False
    for line in lines:
        if line.startswith(needle) and not found:
            # Keep the label, replace anything after the colon if present.
            if ":" in line:
                out.append(f"- {label} {value}")
            else:
                out.append(f"- {label} {value}")
            found = True
        else:
            out.append(line)
    if not found:
        raise ValueError(f"template is missing field: {label}")
    return "\n".join(out) + "\n"


def write_handoff(dest: Path, fields: dict) -> Path:
    """Write a HANDOFF.md derived from templates/HANDOFF.md."""
    text = _require_template("HANDOFF.md")
    mapping = {
        "Project and receiving owner:": fields["project_owner"],
        "User-visible result:": fields["user_visible"],
        "Why this matters:": fields["why"],
        "Acceptance criteria, each with an observable check:": fields["acceptance"],
        "Repository and full base commit, or source-pack version and checksum:": fields["baseline"],
        "Target branch or destination:": fields["target"],
        "Current spec and revision:": fields["spec"],
        "Required inputs with accessible links or archive-relative paths:": fields["inputs"],
        "Relevant prior findings and evidence:": fields["prior"],
        "Chosen direction and constraints:": fields["direction"],
        "Superseded decisions and their replacements:": fields["superseded"],
        "Work already authorized by Kyle, with original instruction reference:": fields["authorized"],
        "Actions not authorized or explicitly held:": fields["not_authorized"],
        "Assigned files/interfaces and dependencies:": fields["assigned"],
        "Budget, tools/environment and stop conditions:": fields["budget"],
        "Assumptions that could materially change the result:": fields["assumptions"],
        "Deliverable format and editable source requirements:": fields["deliverable"],
        "Checks to run, inputs/settings and expected outcomes:": fields["checks"],
        "Failure cases and invariants to preserve:": fields["invariants"],
        "Visual or real-host acceptance, when relevant:": fields["visual"],
        "Checks unavailable in this environment:": fields["unavailable"],
    }
    for label, value in mapping.items():
        text = _replace_bullet(text, label, value)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def write_return(dest: Path, fields: dict, evidence_rows: list[dict]) -> Path:
    """Write a RETURN.md derived from templates/RETURN.md."""
    text = _require_template("RETURN.md")
    mapping = {
        "Outcome: complete / partial / blocked": fields["outcome"],
        "Deliverable links or archive-relative paths:": fields["deliverable"],
        "Base and resulting revision, or source/export checksums:": fields["revisions"],
        "Changed paths and scope deviations:": fields["paths"],
        "Decisions made within scope:": fields["decisions"],
        "Remaining defects, unproven claims and unavailable checks:": fields["limits"],
        "Deferred work and reason:": fields["deferred"],
        "Active jobs/checkpoint if interrupted:": fields["checkpoint"],
        "Next action and owner:": fields["next_action"],
        "Any new authorization required:": fields["new_auth"],
        "Reviewed revision/artifact:": fields["reviewed"],
        "Decision: accept / request changes / blocked": fields["decision"],
        "Evidence independently reproduced:": fields["reproduced"],
        "Findings: expected behavior, observed behavior, reproduction, required check:": fields["findings"],
        "Integrated revision and post-integration evidence, if integration is authorized:": fields["integrated"],
        "Reusable lesson and destination:": fields["lesson"],
    }
    for label, value in mapping.items():
        text = _replace_bullet(text, label, value)

    # Replace the placeholder evidence row with real rows, keeping the header.
    rows = [
        "| Acceptance criterion | Check and input/settings | Revision/environment | Result | Evidence location | Who ran it |",
        "|---|---|---|---|---|---|",
    ]
    for row in evidence_rows:
        rows.append(
            "| {criterion} | {check} | {revision} | {result} | {location} | {who} |".format(**row)
        )
    old = (
        "| Acceptance criterion | Check and input/settings | Revision/environment | Result | Evidence location | Who ran it |\n"
        "|---|---|---|---|---|---|\n"
        "| Replace this row | Exact command or manual procedure | Pin the tested artifact | passed / failed / not run / blocked | Log, capture or report | Producer / reviewer |"
    )
    new = "\n".join(rows)
    if old not in text:
        raise ValueError("RETURN template table not found")
    text = text.replace(old, new)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest
