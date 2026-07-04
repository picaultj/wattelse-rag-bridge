#!/usr/bin/env python3
"""Bump the `[project].version` field in pyproject.toml in place.

Usage: bump_version.py [major|minor|patch]   (defaults to patch)
Prints the new version to stdout.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
VERSION_RE = re.compile(r'(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"')


def bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if part not in {"major", "minor", "patch"}:
        raise SystemExit(f"Unknown bump part: {part!r} (expected major, minor, or patch)")

    text = PYPROJECT.read_text()
    match = VERSION_RE.search(text)
    if not match:
        raise SystemExit('Could not find a `version = "X.Y.Z"` line in pyproject.toml')

    current = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    new_version = bump(current, part)
    new_version_str = ".".join(map(str, new_version))

    new_text = VERSION_RE.sub(f'version = "{new_version_str}"', text, count=1)
    PYPROJECT.write_text(new_text)
    print(new_version_str)


if __name__ == "__main__":
    main()
