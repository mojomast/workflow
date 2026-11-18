"""Read-only inventory of the checked-out Rails packet deliverables.

Run with four sibling working trees in place. Exits 1 if a packet is missing
a leased file or a vendored Python module doesn't match the canonical source.
This is an inventory gate, not an acceptance verdict or live queue reader.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

# <siblings>/workflow/contrib/core-review/<script>
ROOT = Path(__file__).resolve().parents[3]
REPOS = {"hyvv", "bundlebees", "orbitdesktop", "workflow"}
PACKAGE = Path('contrib/rizzstack_rails')


def vendor_drift(root: Path) -> list[str]:
    """Check the complete installed package, including modules shared across leases."""
    drift = set()
    for repo in ('bundlebees', 'hyvv', 'orbitdesktop'):
        directory = root / repo / PACKAGE
        manifest = directory / 'vendor-manifest.json'
        try:
            doc = json.loads(manifest.read_bytes())
            entries = {e['path']: (e['sha256'], e['bytes']) for e in doc['files']}
            if (doc['schema'] != 'rizzstack.vendor-manifest/1' or doc['source_package'] != PACKAGE.as_posix()
                    or len(entries) != len(doc['files']) or not entries):
                raise ValueError('invalid manifest')
        except (ValueError, KeyError, TypeError, OSError):
            drift.add(f'{repo}/{PACKAGE}/vendor-manifest.json')
            continue
        actual = {(PACKAGE / f.name).as_posix() for f in directory.glob('*.py')}
        for name in sorted(actual | set(entries)):
            # Only dereference ordinary, immediate, reviewed Python modules.
            if name not in actual or name not in entries:
                drift.add(f'{repo}/{name}')
                continue
            path = root / repo / name
            source = root / 'bundlebees' / name
            if path.is_symlink() or not path.is_file() or source.is_symlink() or not source.is_file():
                drift.add(f'{repo}/{name}')
                continue
            data = path.read_bytes()
            if entries[name] != (hashlib.sha256(data).hexdigest(), len(data)) or data != source.read_bytes():
                drift.add(f'{repo}/{name}')
    return sorted(drift)


def check(root: Path) -> dict:
    backlog = json.loads((root / "workflow/plans/backlog.json").read_text())
    packages = {}
    mismatches = vendor_drift(root)
    for item in backlog["slices"]:
        if not item["id"].startswith("RAILS-"):
            continue
        repo = item["project"]
        if repo not in REPOS:
            raise ValueError("unexpected repository in Rails backlog")
        missing = []
        for name in item["brief"]["assigned_files"]:
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("unexpected packet path")
            path = root / repo / rel
            if not path.is_file():
                missing.append(name)
        packages[item["id"]] = {"repo": repo, "missing": missing}
    if len(packages) != 22:
        raise ValueError("expected the 22 Rails packages in the frozen backlog")
    return {"packages": packages, "vendor_mismatches": mismatches,
            "inventory_complete": not mismatches and not any(p["missing"] for p in packages.values())}


if __name__ == "__main__":
    report = check(ROOT)
    print(json.dumps(report, sort_keys=True, indent=2))
    sys.exit(0 if report["inventory_complete"] else 1)
