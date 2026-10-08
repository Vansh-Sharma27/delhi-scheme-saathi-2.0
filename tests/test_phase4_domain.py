"""Domain compatibility and dependency-boundary checks."""

import ast
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from src.dss.application.conversation.contracts import SchemeDetailResponse
from src.dss.application.ports.clock import Clock
from src.dss.domain.conversations.clock import Clock as DomainClock
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.profiles.required_fields import required_profile_fields
from src.dss.domain.schemes.document import Document
from src.dss.domain.schemes.office import Office
from src.dss.domain.schemes.scheme import Scheme
from src.dss.infrastructure.database.catalog import (
    _load_catalog,
    get_required_profile_fields_for_life_event,
)
from src.dss.infrastructure.database.scheme_codec import scheme_from_row
from src.dss.infrastructure.sessions.codec import session_from_item


@lru_cache(maxsize=2)
def _historical_model(name: str) -> ModuleType:
    """Load independent pre-extraction models, remapping only catalog imports."""
    source_ref = f"e7f8ae0:src/models/{name}.py"
    source = subprocess.check_output(
        ["git", "show", source_ref], cwd=Path(__file__).resolve().parents[1],
        encoding="utf-8",
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.utils.scheme_catalog":
            node.module = "src.dss.infrastructure.database.catalog"
    module = ModuleType(f"historical_{name}_models")
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree, source_ref, "exec"), module.__dict__)
    finally:
        del sys.modules[module.__name__]
    return module


def test_clock_port_keeps_identity() -> None:
    assert Clock is DomainClock


def test_expanded_models_work() -> None:
    profile = UserProfile(age=30, life_event="HOUSING", annual_income=100000)
    current = Session(user_id="synthetic", user_profile=profile)
    assert current.with_state(ConversationState.MATCHING).state is ConversationState.SCHEME_MATCHING
    assert current.user_profile.model_dump() == profile.model_dump()
    assert type(current) is Session
    assert current.user_profile is profile
    assert Scheme.model_fields["is_active"].default is True
    assert Document.model_fields["prerequisites"].default_factory is list
    assert Office.model_fields["distance_km"].default is None


def test_pure_required_fields_matches_catalog_policy() -> None:
    catalog = _load_catalog()
    events = {event for scheme in catalog.values() for event in scheme.get("life_events", [])}
    for event in [None, "UNKNOWN", *sorted(events)]:
        assert required_profile_fields(event, catalog.values()) == get_required_profile_fields_for_life_event(event)
    assert required_profile_fields("SYNTHETIC", [{"life_events": ["SYNTHETIC"], "eligibility": {"genders": ["female"], "categories": ["SC"]}}]) == ("life_event", "age", "annual_income", "gender", "category")


def test_session_codec_matches_legacy_repair() -> None:
    historical = _historical_model("session")
    original = Session(user_id="synthetic").to_dynamodb_item()
    for state in [None, "UNKNOWN", "UNDERSTANDING", "MATCHING", "PRESENTING", "DETAILS", "APPLICATION", "HANDOFF", *[s.value for s in ConversationState]]:
        for profile in [{}, {"life_event": "HOUSING"}]:
            item = {**original, "state": state, "user_profile": profile}
            hydrated = session_from_item(Session, item)
            assert type(hydrated) is Session
            assert type(hydrated.user_profile) is UserProfile
            assert hydrated.model_dump(mode="json") == historical.Session.from_dynamodb_item(item).model_dump(mode="json")


def test_profile_and_session_copies_keep_canonical_types() -> None:
    current = Session(user_id="synthetic", user_profile={"life_event": "HOUSING", "age": 30, "annual_income": 100000})
    copied = current.copy_with()
    assert type(copied) is Session
    assert copied.user_profile is not current.user_profile
    assert copied.user_profile.complete_for_matching(_load_catalog().values()) is True
    merged = copied.user_profile.merge_with(UserProfile(gender="female"))
    assert type(merged) is UserProfile
    assert merged.required_fields_for_matching(_load_catalog().values()) == ("life_event", "age", "annual_income")
    updated = current.with_profile(UserProfile(life_event="HOUSING", age=40, annual_income=100000))
    assert type(updated) is Session
    assert type(updated.user_profile) is UserProfile
    assert updated.user_profile.age == 40


def test_scheme_codec_matches_legacy_hydration() -> None:
    row = {"id": "SCH-DELHI-001", "name": "Synthetic", "name_hindi": "Synthetic", "department": "Synthetic", "department_hindi": "Synthetic", "level": "state", "description": "Synthetic", "description_hindi": "Synthetic", "eligibility": '{"categories": ["EWS", "LIG"]}', "helpline": '{"phone": ["100", "200"]}', "metadata": '{"synthetic": true}', "life_events": ["STALE"], "tags": ["STALE"]}
    assert scheme_from_row(Scheme, row).model_dump() == _historical_model("scheme").Scheme.from_db_row(row).model_dump()
    hydrated = scheme_from_row(Scheme, row)
    assert type(hydrated) is Scheme
    assert SchemeDetailResponse(scheme=hydrated).scheme is hydrated


def test_domain_imports_stay_below_application() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "dss" / "domain"
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
                assert node.module.startswith("src.dss.domain."), (path, node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("src."):
                        assert alias.name.startswith("src.dss.domain."), (path, alias.name)


def test_enum_and_persisted_repair_are_original_ast() -> None:
    original = subprocess.check_output(["git", "show", "e7f8ae0:src/models/session.py"], text=True)
    root = Path(__file__).resolve().parents[1]
    for name, path in [
        ("ConversationState", "src/dss/domain/conversations/states.py"),
        ("_normalize_persisted_state", "src/dss/infrastructure/sessions/codec.py"),
    ]:
        def definition(source: str, name: str = name) -> str:
            return ast.dump(next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef | ast.FunctionDef) and node.name == name))
        assert definition(original) == definition((root / path).read_text(encoding="utf-8"))
    assert "class ConversationState(str, Enum):  # noqa: UP042" in (root / "src/dss/domain/conversations/states.py").read_text(encoding="utf-8")
