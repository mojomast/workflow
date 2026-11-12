"""Scripted patch generators. These stand in for model-backed workers."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from .toy import run_git, write


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export_clone(source: Path, source_rev: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--quiet", str(source), str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(dest, "checkout", "-q", source_rev)
    run_git(dest, "config", "user.name", "Reference Worker")
    run_git(dest, "config", "user.email", "worker@example.invalid")
    run_git(dest, "config", "commit.gpgsign", "false")


def _diff_against(repo: Path, source_rev: str) -> str:
    return run_git(repo, "diff", "--binary", source_rev).stdout


def _changed_files(repo: Path, source_rev: str) -> list[dict]:
    names = run_git(repo, "diff", "--name-only", source_rev).stdout.splitlines()
    files = []
    for name in names:
        path = repo / name
        files.append({
            "path": name,
            "sha256": _sha256_file(path) if path.exists() else None,
        })
    return files


def make_manifest(task_id: str, source_rev: str, assigned_files: list[str],
                  repo: Path, claimed_files: list[str] | None = None,
                  cost_units: int = 1) -> dict:
    """Build a result manifest. claimed_files may lie; verify must ignore them."""
    patch = _diff_against(repo, source_rev)
    observed = _changed_files(repo, source_rev)
    return {
        "task_id": task_id,
        "source_rev": source_rev,
        "cost_units": cost_units,
        "worker_claims": {
            "assigned_files": list(claimed_files if claimed_files is not None else assigned_files),
            "summary": f"scripted worker for {task_id}",
        },
        "observed": {"files": observed},
        "patch": patch,
    }


# --- in-scope implementations -------------------------------------------------

PRICING_WITH_TAX = '''def apply_discount(price_cents: int, percent: int) -> int:
    """Return the discounted price in cents, rounding down."""
    if price_cents < 0:
        raise ValueError("price must be non-negative")
    if percent < 0 or percent > 100:
        raise ValueError("percent out of range")
    return price_cents * (100 - percent) // 100


def apply_tax(price_cents: int, rate_percent: int) -> int:
    """Return the price with tax added, rounding down."""
    if price_cents < 0:
        raise ValueError("price must be non-negative")
    if rate_percent < 0:
        raise ValueError("rate must be non-negative")
    return price_cents * (100 + rate_percent) // 100
'''

TEST_PRICING_WITH_TAX = '''import unittest

from shop.pricing import apply_discount, apply_tax


class PricingTests(unittest.TestCase):
    def test_ten_percent_off(self):
        self.assertEqual(apply_discount(1000, 10), 900)

    def test_rejects_negative_price(self):
        with self.assertRaises(ValueError):
            apply_discount(-1, 10)

    def test_rejects_bad_percent(self):
        with self.assertRaises(ValueError):
            apply_discount(100, 150)

    def test_apply_tax(self):
        self.assertEqual(apply_tax(1000, 10), 1100)

    def test_apply_tax_rejects_negative_rate(self):
        with self.assertRaises(ValueError):
            apply_tax(100, -1)


if __name__ == "__main__":
    unittest.main()
'''

LABELS_WITH_RECEIPT = '''def format_price(cents: int) -> str:
    """Format a non-negative cent amount as a dollar string."""
    if cents < 0:
        raise ValueError("cents must be non-negative")
    return f"${cents // 100}.{cents % 100:02d}"


def format_receipt_line(name: str, cents: int) -> str:
    """Format a single receipt line as 'name: $x.yy'."""
    if not name or name.strip() != name or not name.strip():
        raise ValueError("name must be a non-empty stripped string")
    return f"{name}: {format_price(cents)}"
'''

TEST_LABELS_WITH_RECEIPT = '''import unittest

from shop.labels import format_price, format_receipt_line


class LabelTests(unittest.TestCase):
    def test_formats_cents(self):
        self.assertEqual(format_price(199), "$1.99")

    def test_formats_zero(self):
        self.assertEqual(format_price(0), "$0.00")

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            format_price(-5)

    def test_receipt_line(self):
        self.assertEqual(format_receipt_line("Tea", 199), "Tea: $1.99")

    def test_receipt_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            format_receipt_line("  ", 100)


if __name__ == "__main__":
    unittest.main()
'''


def work_pricing(source: Path, source_rev: str, work_root: Path, task_id: str,
                 assigned_files: list[str]) -> dict:
    clone = work_root / task_id
    _export_clone(source, source_rev, clone)
    write(clone / "shop" / "pricing.py", PRICING_WITH_TAX)
    write(clone / "tests" / "test_pricing.py", TEST_PRICING_WITH_TAX)
    return make_manifest(task_id, source_rev, assigned_files, clone, cost_units=1)


def work_labels(source: Path, source_rev: str, work_root: Path, task_id: str,
                assigned_files: list[str]) -> dict:
    clone = work_root / task_id
    _export_clone(source, source_rev, clone)
    write(clone / "shop" / "labels.py", LABELS_WITH_RECEIPT)
    write(clone / "tests" / "test_labels.py", TEST_LABELS_WITH_RECEIPT)
    return make_manifest(task_id, source_rev, assigned_files, clone, cost_units=1)


def work_out_of_scope(source: Path, source_rev: str, work_root: Path, task_id: str,
                      assigned_files: list[str]) -> dict:
    """Deliberately patch a file outside the lease, and claim the lease was wider."""
    clone = work_root / task_id
    _export_clone(source, source_rev, clone)
    # In-scope change (so the patch is not empty) plus an out-of-scope edit.
    write(clone / "shop" / "pricing.py", PRICING_WITH_TAX)
    write(
        clone / "shop" / "labels.py",
        (clone / "shop" / "labels.py").read_text(encoding="utf-8")
        + "\nMARK = \"out-of-scope\"\n",
    )
    # The worker lies about its lease. Verify must use the coordinator record.
    claimed = list(assigned_files) + ["shop/labels.py"]
    return make_manifest(
        task_id, source_rev, assigned_files, clone,
        claimed_files=claimed, cost_units=1,
    )


def work_wrong_revision(source: Path, source_rev: str, work_root: Path, task_id: str,
                        assigned_files: list[str], fake_rev: str) -> dict:
    """Produce a pricing patch but stamp a different source_rev."""
    manifest = work_pricing(source, source_rev, work_root, task_id, assigned_files)
    manifest["source_rev"] = fake_rev
    return manifest
