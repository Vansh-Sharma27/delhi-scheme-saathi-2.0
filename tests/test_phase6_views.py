"""Canonical view formatting retains every original pure helper definition."""

import ast
import subprocess
from pathlib import Path

from src.dss.application.conversation import view_formatting


def test_view_formatters_match_original_ast() -> None:
    root = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(
        ["git", "show", "d8148ee:src/services/conversation/views.py"], cwd=root,
    ).decode("utf-8")
    definitions = {
        node.name: ast.dump(node) for node in ast.parse(original).body
        if isinstance(node, ast.FunctionDef)
    }
    current = ast.parse(Path(view_formatting.__file__).read_text(encoding="utf-8"))
    for node in current.body:
        if isinstance(node, ast.FunctionDef):
            assert ast.dump(node) == definitions[node.name], node.name
