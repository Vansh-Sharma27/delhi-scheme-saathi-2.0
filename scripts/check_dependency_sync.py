#!/usr/bin/env python3
"""Verify that package metadata and pip requirement entry points stay aligned."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _requirements(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-r "))
    ]


def main() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_runtime = project["project"]["dependencies"]
    project_dev = project["project"]["optional-dependencies"]["dev"]
    locked_runtime = _requirements(ROOT / "requirements.lock")
    pip_dev = _requirements(ROOT / "requirements-dev.txt")

    failures: list[str] = []
    if project_runtime != locked_runtime:
        failures.append("pyproject runtime dependencies differ from requirements.lock")
    if project_dev != pip_dev:
        failures.append("pyproject dev dependencies differ from requirements-dev.txt")
    if (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()[-1] != "-r requirements.lock":
        failures.append("requirements.txt must include requirements.lock")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("PASS: dependency declarations are synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
