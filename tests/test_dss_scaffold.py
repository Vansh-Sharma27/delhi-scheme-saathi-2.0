"""Pin the src/dss scaffold tree from spec Section 6.

Every layer package created in Phase 1 must stay a regular package with an
``__init__.py``. A stray deletion of an empty leaf package in any later phase
commit would otherwise pass every gate: import-linter does not require unlisted
packages to exist, and Python 3.3+ namespace packages (PEP 420) let a
directory without ``__init__.py`` import silently. Asserting ``__file__``
points at an ``__init__.py`` makes the 23-package tree a hard boundary that a
deletion breaks. The list is the spec Section 6 tree verbatim; update it only
when a phase intentionally adds or removes a package.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

DSS_LAYER_PACKAGES: list[str] = [
    "src.dss",
    "src.dss.bootstrap",
    "src.dss.domain",
    "src.dss.domain.profiles",
    "src.dss.domain.schemes",
    "src.dss.domain.eligibility",
    "src.dss.domain.conversations",
    "src.dss.application",
    "src.dss.application.conversation",
    "src.dss.application.matching",
    "src.dss.application.guidance",
    "src.dss.application.ports",
    "src.dss.infrastructure",
    "src.dss.infrastructure.database",
    "src.dss.infrastructure.ai",
    "src.dss.infrastructure.ai.prompts",
    "src.dss.infrastructure.embeddings",
    "src.dss.infrastructure.speech",
    "src.dss.infrastructure.sessions",
    "src.dss.infrastructure.queues",
    "src.dss.interfaces",
    "src.dss.interfaces.api",
    "src.dss.interfaces.telegram",
    "src.dss.observability",
]


@pytest.mark.parametrize("module_name", DSS_LAYER_PACKAGES)
def test_dss_layer_package_is_regular_package(module_name: str) -> None:
    """Every spec Section 6 layer package must be a regular package, not a
    namespace package: ``__init__.py`` must exist and be its origin."""
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"{module_name} is not importable"
    assert spec.origin is not None, (
        f"{module_name} resolved as a namespace package "
        f"(no __init__.py); spec.origin is None"
    )
    assert Path(spec.origin).name == "__init__.py", (
        f"{module_name} origin {spec.origin} is not an __init__.py"
    )


def test_dss_settings_module_importable() -> None:
    """The src/dss/settings.py placeholder must stay present (spec 7.7 home)."""
    module = importlib.import_module("src.dss.settings")
    assert hasattr(module, "__file__")
    assert Path(module.__file__).name == "settings.py"  # type: ignore[arg-type]


def test_dss_layer_package_count() -> None:
    """Guard against a silent shrink or grow of the scaffold tree.

    If a phase adds or removes a package, the count changes and this test
    forces a deliberate edit to the list above, which a reviewer sees.
    Phase 3 added src.dss.infrastructure.ai.prompts (spec 7.4): the prompt
    loader and the .txt templates move together into infrastructure/ai.
    """
    assert len(DSS_LAYER_PACKAGES) == 24
