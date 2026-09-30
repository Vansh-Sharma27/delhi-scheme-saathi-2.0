"""Unit tests for the fail-closed mypy baseline comparator."""

from collections import Counter
from pathlib import Path

import pytest

from scripts.check_mypy_delta import (
    Diagnostic,
    load_path_map,
    new_diagnostics,
    parse_mypy_report,
    remap_paths,
)


def test_parse_mypy_report_uses_stable_line_independent_fingerprint() -> None:
    report = (
        "src/example.py:10:5: error: Incompatible return value type  [return-value]\n"
        "src/example.py:99: error: Incompatible return value type  [return-value]\n"
        "Found 2 errors in 1 file (checked 1 source file)\n"
    )

    assert parse_mypy_report(report) == Counter(
        {
            Diagnostic(
                path="src/example.py",
                code="return-value",
                message="Incompatible return value type",
            ): 2
        }
    )


def test_parse_mypy_report_rejects_unparseable_error_line() -> None:
    with pytest.raises(ValueError, match="Unparseable mypy error output"):
        parse_mypy_report("src/example.py: error: missing line number [misc]")


def test_new_diagnostics_is_a_multiset_delta() -> None:
    existing = Diagnostic("src/example.py", "assignment", "Bad assignment")
    added = Diagnostic("src/new.py", "arg-type", "Bad argument")
    baseline = Counter({existing: 2})
    current = Counter({existing: 2, added: 1})

    assert new_diagnostics(baseline, current) == Counter({added: 1})


def test_unrelated_fix_cannot_hide_a_new_diagnostic() -> None:
    removed = Diagnostic("src/old.py", "assignment", "Old error")
    added = Diagnostic("src/new.py", "arg-type", "New error")

    assert new_diagnostics(Counter({removed: 1}), Counter({added: 1})) == Counter(
        {added: 1}
    )


def test_remap_paths_rewrites_only_ledgered_paths() -> None:
    moved = Diagnostic("src/integrations/embedding_client.py", "no-any-return", "E")
    untouched = Diagnostic("src/webhook/handler.py", "arg-type", "Other")
    path_map = {"src/integrations/embedding_client.py": "src/dss/infrastructure/embeddings/fallback_client.py"}

    remapped = remap_paths(Counter({moved: 1, untouched: 1}), path_map)

    assert remapped == Counter(
        {
            Diagnostic("src/dss/infrastructure/embeddings/fallback_client.py", "no-any-return", "E"): 1,
            untouched: 1,
        }
    )


def test_remap_paths_empty_map_is_identity() -> None:
    diagnostics = Counter({Diagnostic("src/a.py", "misc", "E"): 1})
    assert remap_paths(diagnostics, {}) == diagnostics


def test_ledgered_move_cancels_but_new_error_still_fails() -> None:
    """A reviewed file move must not mask an error introduced by the move.

    The moved pre-existing error cancels against its remapped baseline
    fingerprint; an error newly introduced in the same commit still surfaces
    in the delta because no baseline fingerprint matches it.
    """
    path_map = {"src/integrations/grok_client.py": "src/dss/infrastructure/ai/grok_client.py"}
    baseline = Counter(
        {
            Diagnostic("src/integrations/grok_client.py", "arg-type", "Old call"): 1,
        }
    )
    current = Counter(
        {
            Diagnostic("src/dss/infrastructure/ai/grok_client.py", "arg-type", "Old call"): 1,
            Diagnostic("src/dss/infrastructure/ai/grok_client.py", "misc", "New mistake"): 1,
        }
    )

    assert new_diagnostics(remap_paths(baseline, path_map), current) == Counter(
        {Diagnostic("src/dss/infrastructure/ai/grok_client.py", "misc", "New mistake"): 1}
    )


def test_unledgered_move_still_fails_the_delta() -> None:
    """A move without a ledger entry is a delta by definition.

    This is what forces every relocation to land in the same commit as its
    ledger entry: skipping the ledger entry cannot be used to silence a
    regression, and forgetting it fails the gate instead of passing quietly.
    """
    baseline = Counter({Diagnostic("src/integrations/grok_client.py", "arg-type", "Old call"): 1})
    current = Counter(
        {Diagnostic("src/dss/infrastructure/ai/grok_client.py", "arg-type", "Old call"): 1}
    )

    assert new_diagnostics(remap_paths(baseline, {}), current) == current


def test_load_path_map_reads_repository_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "scripts"
    ledger.mkdir()
    (ledger / "mypy_delta_path_map.json").write_text(
        '{"src/a.py": "src/b.py"}', encoding="utf-8"
    )

    assert load_path_map(tmp_path) == {"src/a.py": "src/b.py"}


def test_load_path_map_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_path_map(tmp_path) == {}


def test_load_path_map_rejects_non_path_entries(tmp_path: Path) -> None:
    ledger = tmp_path / "scripts"
    ledger.mkdir()
    (ledger / "mypy_delta_path_map.json").write_text('{"src/a.py": 12}', encoding="utf-8")

    with pytest.raises(ValueError, match="path strings"):
        load_path_map(tmp_path)
