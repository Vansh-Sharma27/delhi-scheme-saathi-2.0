"""Canonical settings ownership, cache behavior, and original-definition invariants."""

import ast
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.dss import settings
from src.dss.settings import get_settings


@pytest.fixture
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep developer environment files and cached test values out of assertions."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.lower() in settings.Settings.model_fields:
            monkeypatch.delenv(name)
    settings.get_settings.cache_clear()
    try:
        yield
    finally:
        settings.get_settings.cache_clear()


def test_canonical_settings_owns_singleton() -> None:
    assert get_settings is settings.get_settings
    assert settings.Settings.__module__ == "src.dss.settings"
    assert settings.get_settings.__module__ == "src.dss.settings"
    assert settings.get_settings.cache_parameters() == {"maxsize": 1, "typed": False}


def test_settings_environment_and_cache_are_shared(
    isolated_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Module and direct imports share the singleton and its invalidation."""
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("AI_INLINE_CONCURRENCY", "7")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " https://one.example, ,https://two.example ")
    first = get_settings()
    assert type(first) is settings.Settings
    assert settings.get_settings() is first
    assert first.debug is True
    assert first.is_production is False
    assert first.ai_inline_concurrency == 7
    assert first.cors_origins == ["https://one.example", "https://two.example"]

    monkeypatch.setenv("DEBUG", "false")
    assert settings.get_settings() is first
    assert get_settings().debug is True
    get_settings.cache_clear()
    second = settings.get_settings()
    assert get_settings() is second
    assert second is not first
    assert second.is_production is True

    settings.get_settings.cache_clear()
    third = get_settings()
    assert third is not second
    assert settings.get_settings() is third


def test_settings_defaults_validation_and_freezing(isolated_settings: None) -> None:
    value = settings.Settings()
    assert value.debug is False
    assert value.is_production is True
    assert value.cors_origins == ["http://localhost:3000"]
    assert value.session_table_name == "dss-sessions"
    assert value.use_bedrock is False
    assert value.chat_api_key == ""
    with pytest.raises(ValidationError, match="frozen_instance"):
        value.debug = True
    with pytest.raises(ValidationError, match="int_parsing"):
        settings.Settings(ai_inline_concurrency="invalid")


def test_settings_dotenv_and_environment_precedence(
    isolated_settings: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        "DEBUG=true\nAI_INLINE_CONCURRENCY=6\nXAI_MODEL=नमस्ते\nUNRELATED_SETTING=ignored\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_INLINE_CONCURRENCY", "9")
    value = settings.get_settings()
    assert value.debug is True
    assert value.ai_inline_concurrency == 9
    assert value.xai_model == "नमस्ते"
    assert "unrelated_setting" not in value.model_dump()
    assert settings.Settings(ai_inline_concurrency=3).ai_inline_concurrency == 3


@pytest.mark.parametrize("name", ["Settings", "get_settings"])
def test_settings_definition_matches_pre_migration_source(name: str) -> None:
    """Pin every field/default/description/property and the cache without a live facade."""
    original = subprocess.check_output(
        ["git", "show", "d8148ee:src/config.py"],
        cwd=Path(__file__).resolve().parents[1],
    ).decode("utf-8")
    current = Path(settings.__file__).read_text(encoding="utf-8")

    def definition(source: str) -> str:
        return ast.dump(next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.ClassDef | ast.FunctionDef) and node.name == name
        ))

    assert definition(current) == definition(original)
