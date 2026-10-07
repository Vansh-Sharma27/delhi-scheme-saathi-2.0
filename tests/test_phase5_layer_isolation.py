"""Keep completed application and interface boundaries enforced."""

import ast
import tomllib
from pathlib import Path


def test_phase5_port_boundary_contract_and_consumers() -> None:
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    contract = next(
        c
        for c in config["tool"]["importlinter"]["contracts"]
        if c["name"] == "Phase 5 application and interfaces depend on ports, not infrastructure"
    )
    assert contract["type"] == "forbidden"
    assert contract["forbidden_modules"] == ["src.dss.infrastructure"]
    assert contract["allow_indirect_imports"] is False
    for directory in [
        "application/conversation",
        "application/matching",
        "application/guidance",
        "interfaces",
    ]:
        for path in (root / "src/dss" / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("src.dss.infrastructure"), path
                if isinstance(node, ast.Import):
                    assert all(
                        not n.name.startswith("src.dss.infrastructure") for n in node.names
                    ), path
            if directory == "interfaces":
                assert not any(
                    isinstance(n, ast.Attribute)
                    and n.attr
                    in {
                        "api_key",
                        "sarvam_api_key",
                        "bhashini_api_key",
                        "acquire",
                        "fetch",
                        "fetchrow",
                        "fetchval",
                    }
                    for n in ast.walk(tree)
                ), path
