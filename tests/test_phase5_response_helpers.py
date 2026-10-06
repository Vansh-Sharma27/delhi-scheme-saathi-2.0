"""Relocated deterministic responses retain the original implementation."""

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", ["localization", "templates", "currency"])
def test_response_helpers_preserve_original_ast(module: str) -> None:
    original = subprocess.check_output(
        ["git", "show", "a394923:src/services/response_generator.py"],
        cwd=ROOT,
    ).decode("utf-8")
    functions = {
        node.name: ast.dump(node)
        for node in ast.parse(original).body
        if isinstance(node, ast.FunctionDef)
    }
    relocated = ROOT / "src/dss/application/guidance" / f"{module}.py"
    moved = [
        node for node in ast.parse(relocated.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
    ]
    assert moved
    for node in moved:
        assert ast.dump(node) == functions[node.name], node.name
