"""Unit tests for the fail-closed mypy baseline comparator."""

from collections import Counter

import pytest

from scripts.check_mypy_delta import Diagnostic, new_diagnostics, parse_mypy_report


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
