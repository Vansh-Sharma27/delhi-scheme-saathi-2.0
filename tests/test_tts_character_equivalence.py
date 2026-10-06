"""TTS character filtering preserves the pre-fix behavior across Unicode."""

import ast
import re
import subprocess
from pathlib import Path

from src.dss.interfaces.telegram.formatting import _clean_for_tts


def test_tts_filter_matches_original_for_every_unicode_code_point() -> None:
    source = subprocess.check_output(
        ["git", "show", "9fc9d8e:src/dss/interfaces/telegram/formatting.py"],
        cwd=Path(__file__).resolve().parents[1],
    ).decode("utf-8")
    original = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "_clean_for_tts"
    )
    namespace = {"re": re}
    exec(compile(ast.Module(body=[original], type_ignores=[]), "<original-tts>", "exec"), namespace)
    text = "".join(map(chr, range(0x110000)))
    assert _clean_for_tts(text) == namespace["_clean_for_tts"](text)
