"""Pure helper relocation preserves the original function definitions."""

import ast
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["validators", "keyboards"])
def test_helper_definitions_match_original(name: str) -> None:
    root = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(
        ["git", "show", f"d8148ee:src/utils/{name}.py"], cwd=root,
    ).decode("utf-8")
    current = (root / f"src/dss/application/conversation/{name}.py").read_text(encoding="utf-8")

    def definitions(source):
        return [ast.dump(node) for node in ast.parse(source).body if isinstance(
            node, ast.FunctionDef | ast.Assign | ast.AnnAssign,
        )]

    assert definitions(current) == definitions(original)
