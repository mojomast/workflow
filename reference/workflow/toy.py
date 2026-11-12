"""Create the tiny shop git repository used by the demo."""

from __future__ import annotations

import subprocess
from pathlib import Path

PRICING = '''def apply_discount(price_cents: int, percent: int) -> int:
    """Return the discounted price in cents, rounding down."""
    if price_cents < 0:
        raise ValueError("price must be non-negative")
    if percent < 0 or percent > 100:
        raise ValueError("percent out of range")
    return price_cents * (100 - percent) // 100
'''

LABELS = '''def format_price(cents: int) -> str:
    """Format a non-negative cent amount as a dollar string."""
    if cents < 0:
        raise ValueError("cents must be non-negative")
    return f"${cents // 100}.{cents % 100:02d}"
'''

TEST_PRICING = '''import unittest

from shop.pricing import apply_discount


class PricingTests(unittest.TestCase):
    def test_ten_percent_off(self):
        self.assertEqual(apply_discount(1000, 10), 900)

    def test_rejects_negative_price(self):
        with self.assertRaises(ValueError):
            apply_discount(-1, 10)

    def test_rejects_bad_percent(self):
        with self.assertRaises(ValueError):
            apply_discount(100, 150)


if __name__ == "__main__":
    unittest.main()
'''

TEST_LABELS = '''import unittest

from shop.labels import format_price


class LabelTests(unittest.TestCase):
    def test_formats_cents(self):
        self.assertEqual(format_price(199), "$1.99")

    def test_formats_zero(self):
        self.assertEqual(format_price(0), "$0.00")

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            format_price(-5)


if __name__ == "__main__":
    unittest.main()
'''

INIT = ""

README = """# toy-shop

A tiny two-module library used by the workflow reference demo.
"""

GITIGNORE = "__pycache__/\n*.pyc\n"


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_toy_repo(root: Path) -> str:
    """Initialize a committed toy shop repo and return the full source_rev."""
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True)
    run_git(root, "init", "-q", "-b", "main")
    run_git(root, "config", "user.name", "Reference Demo")
    run_git(root, "config", "user.email", "demo@example.invalid")
    run_git(root, "config", "commit.gpgsign", "false")
    write(root / "shop" / "__init__.py", INIT)
    write(root / "shop" / "pricing.py", PRICING)
    write(root / "shop" / "labels.py", LABELS)
    write(root / "tests" / "__init__.py", INIT)
    write(root / "tests" / "test_pricing.py", TEST_PRICING)
    write(root / "tests" / "test_labels.py", TEST_LABELS)
    write(root / "README.md", README)
    write(root / ".gitignore", GITIGNORE)
    run_git(root, "add", ".")
    run_git(root, "commit", "-q", "-m", "initial toy shop")
    rev = run_git(root, "rev-parse", "HEAD").stdout.strip()
    if len(rev) != 40:
        raise RuntimeError(f"expected a full SHA, got {rev!r}")
    return rev
