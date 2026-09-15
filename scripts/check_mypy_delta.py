#!/usr/bin/env python3
"""Fail CI on new mypy diagnostics relative to a Git baseline.

Both revisions are checked with the exact same installed mypy and dependency
environment. Diagnostics are compared as a multiset of stable
``(path, error-code, message)`` fingerprints, so unrelated fixes cannot hide a
new error and harmless line movement does not invalidate the baseline.

File relocations complicate the path component of the fingerprint: moving a
module that carries baseline errors does not create new defects, but the path
changes and the moved errors surface as additions. The migration spec calls
this exact situation out (spec 5.1: "the errors sit almost entirely in the
layers Phase 3 relocates ... a per-file comparison will therefore look
catastrophic at Phase 3 while nothing has actually regressed"). To keep this
gate a detector rather than a blocker, reviewed file moves are recorded in
``scripts/mypy_delta_path_map.json`` as ``{old path: new path}`` POSIX-path
pairs. The map is applied to the *baseline* side only: a moved error cancels
against itself, while a genuinely new error at the new path, a changed message,
or an error left behind at the old path still fails. Each entry must be added
in the same commit as the move it records, so the ledger is reviewable and
there is never a window where a move is unaccounted for.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PATH_MAP_FILE = "scripts/mypy_delta_path_map.json"

_DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+)(?::(?P<column>\d+))?: "
    r"error: (?P<message>.*?)(?:\s+\[(?P<code>[^]]+)\])?$"
)


@dataclass(frozen=True, order=True)
class Diagnostic:
    path: str
    code: str
    message: str


def parse_mypy_report(report: str) -> Counter[Diagnostic]:
    """Parse mypy's plain output into line-independent diagnostic identities."""
    diagnostics: Counter[Diagnostic] = Counter()
    unparsed_errors: list[str] = []
    for raw_line in report.splitlines():
        if ": error:" not in raw_line:
            continue
        match = _DIAGNOSTIC_RE.match(raw_line)
        if match is None:
            unparsed_errors.append(raw_line)
            continue
        path = Path(match.group("path")).as_posix()
        while path.startswith("./"):
            path = path[2:]
        diagnostics[
            Diagnostic(
                path=path,
                code=match.group("code") or "unclassified",
                message=match.group("message").strip(),
            )
        ] += 1

    if unparsed_errors:
        rendered = "\n".join(f"  {line}" for line in unparsed_errors)
        raise ValueError(f"Unparseable mypy error output:\n{rendered}")
    return diagnostics


def _run_mypy(repository: Path) -> tuple[Counter[Diagnostic], str]:
    command = [
        sys.executable,
        "-m",
        "mypy",
        "src",
        "--show-error-codes",
        "--no-pretty",
        "--no-color-output",
    ]
    completed = subprocess.run(
        command,
        cwd=repository,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    report = completed.stdout
    diagnostics = parse_mypy_report(report)

    # mypy uses 0 for clean and 1 for type errors. Any other status is an
    # invocation/internal failure. A status of 1 without parseable errors is
    # also an unusable report and must never be interpreted as zero.
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            f"mypy failed with status {completed.returncode}:\n{report}"
        )
    if completed.returncode == 1 and not diagnostics:
        raise RuntimeError(
            "mypy returned status 1 without parseable diagnostics; refusing to pass\n"
            + report
        )
    if completed.returncode == 0 and diagnostics:
        raise RuntimeError("mypy returned status 0 while reporting errors")
    return diagnostics, report


def new_diagnostics(
    baseline: Counter[Diagnostic],
    current: Counter[Diagnostic],
) -> Counter[Diagnostic]:
    """Return diagnostic occurrences added by the current revision."""
    return current - baseline


def load_path_map(repository: Path) -> dict[str, str]:
    """Load the reviewed file-move ledger as ``{old path: new path}``.

    The file is optional so the gate works on trees that predate it. Entries
    must be POSIX paths relative to the repository root, matching the
    normalization ``parse_mypy_report`` applies to diagnostics.
    """
    map_path = repository / PATH_MAP_FILE
    if not map_path.is_file():
        return {}
    raw = json.loads(map_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not all(
        isinstance(old, str) and isinstance(new, str) for old, new in raw.items()
    ):
        raise ValueError(f"{PATH_MAP_FILE} must be a JSON object of path strings")
    return raw


def remap_paths(
    diagnostics: Counter[Diagnostic],
    path_map: dict[str, str],
) -> Counter[Diagnostic]:
    """Rewrite baseline diagnostic paths through the reviewed move ledger."""
    if not path_map:
        return diagnostics
    remapped: Counter[Diagnostic] = Counter()
    for diagnostic, count in diagnostics.items():
        mapped = path_map.get(diagnostic.path, diagnostic.path)
        remapped[Diagnostic(mapped, diagnostic.code, diagnostic.message)] += count
    return remapped


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def check_delta(repository: Path, baseline_ref: str) -> int:
    """Run and compare mypy at ``baseline_ref`` and the current worktree."""
    verify = _git("rev-parse", "--verify", f"{baseline_ref}^{{commit}}", cwd=repository)
    if verify.returncode != 0:
        raise RuntimeError(
            f"Cannot resolve mypy baseline ref {baseline_ref!r}:\n{verify.stdout}"
        )

    with tempfile.TemporaryDirectory(prefix="mypy-baseline-") as temporary_dir:
        baseline_tree = Path(temporary_dir) / "worktree"
        add = _git(
            "worktree",
            "add",
            "--detach",
            str(baseline_tree),
            baseline_ref,
            cwd=repository,
        )
        if add.returncode != 0:
            raise RuntimeError(f"Cannot create baseline worktree:\n{add.stdout}")
        try:
            baseline_diagnostics, baseline_report = _run_mypy(baseline_tree)
            current_diagnostics, current_report = _run_mypy(repository)
        finally:
            remove = _git(
                "worktree",
                "remove",
                "--force",
                str(baseline_tree),
                cwd=repository,
            )
            if remove.returncode != 0:
                print(remove.stdout, file=sys.stderr)

    path_map = load_path_map(repository)
    baseline_diagnostics = remap_paths(baseline_diagnostics, path_map)

    print("=== mypy baseline report ===")
    print(baseline_report, end="" if baseline_report.endswith("\n") else "\n")
    print("=== mypy current report ===")
    print(current_report, end="" if current_report.endswith("\n") else "\n")
    print(
        "mypy diagnostics: "
        f"baseline={sum(baseline_diagnostics.values())}, "
        f"current={sum(current_diagnostics.values())}"
    )
    if path_map:
        print(f"applied move ledger: {len(path_map)} entr"
              f"{'y' if len(path_map) == 1 else 'ies'}")

    additions = new_diagnostics(baseline_diagnostics, current_diagnostics)
    if not additions:
        print("PASS: no new mypy diagnostic fingerprints")
        return 0

    print("FAIL: new mypy diagnostics:", file=sys.stderr)
    for diagnostic, count in sorted(additions.items()):
        suffix = f" (x{count})" if count > 1 else ""
        print(
            f"  {diagnostic.path}: error: {diagnostic.message} "
            f"[{diagnostic.code}]{suffix}",
            file=sys.stderr,
        )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline-ref",
        required=True,
        help="Git commit/ref whose mypy diagnostics are allowed",
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args()

    try:
        return check_delta(args.repository.resolve(), args.baseline_ref)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
