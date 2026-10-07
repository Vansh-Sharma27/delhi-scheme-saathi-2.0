"""Pure helper relocation preserves the original function definitions."""

import ast
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("old,new", [
    ("utils/validators", "conversation/validators"),
    ("utils/keyboards", "conversation/keyboards"),
    ("services/conversation/language", "conversation/language"),
    ("services/life_event_classifier", "conversation/life_event_classifier"),
    ("services/scheme_relevance", "matching/scheme_relevance"),
])
def test_helper_definitions_match_original(old: str, new: str) -> None:
    root = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(
        ["git", "show", f"d8148ee:src/{old}.py"], cwd=root,
    ).decode("utf-8")
    current = (root / f"src/dss/application/{new}.py").read_text(encoding="utf-8")

    def definitions(source):
        return [ast.dump(node) for node in ast.parse(source).body if isinstance(
            node, ast.FunctionDef | ast.Assign | ast.AnnAssign,
        )]

    assert definitions(current) == definitions(original)
