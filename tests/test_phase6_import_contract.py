"""Exercise the legacy boundary with populated bootstrap, not just empty packages."""

import os
import subprocess
import tomllib
from pathlib import Path

import pytest


@pytest.mark.parametrize("legacy_import", ["", "from src import legacy", "from src import bridge"])
def test_bootstrap_legacy_contract_keeps_canonical_siblings(tmp_path, legacy_import) -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    contract = config["tool"]["importlinter"]["contracts"][2]
    assert contract["allow_indirect_imports"] is False
    assert not contract.get("ignore_imports")
    for package in ["src", "src/dss", "src/dss/bootstrap", "src/dss/observability"]:
        directory = tmp_path / package
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "__init__.py").write_text("", encoding="utf-8")
    for name, source in {
        "src/dss/bootstrap/runtime.py": "from src.dss import settings\nfrom src.dss.observability import logging\n" + legacy_import,
        "src/dss/settings.py": "VALUE = 1\n",
        "src/dss/observability/logging.py": "VALUE = 1\n",
        "src/bridge.py": "from src import legacy\n",
        "src/legacy.py": "VALUE = 1\n",
    }.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.importlinter]\nroot_package = "src"\n'
        '[[tool.importlinter.contracts]]\nname = "Legacy boundary"\ntype = "forbidden"\n'
        f'source_modules = {contract["source_modules"]!r}\n'
        f'forbidden_modules = {contract["forbidden_modules"]!r}\n'
        'allow_indirect_imports = false\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["lint-imports", "--no-cache"], cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True, text=True,
    )
    if legacy_import:
        assert result.returncode != 0, result.stdout + result.stderr
        assert "BROKEN" in result.stdout
        assert "src.dss.bootstrap.runtime" in result.stdout
        assert "src.legacy" in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "1 kept, 0 broken" in result.stdout
