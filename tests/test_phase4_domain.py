"""Domain compatibility and dependency-boundary checks."""

from src.dss.application.ports.clock import Clock
from src.dss.domain.conversations.clock import Clock as DomainClock
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.profiles.required_fields import required_profile_fields
from src.dss.domain.schemes.document import Document
from src.dss.domain.schemes.office import Office
from src.dss.domain.schemes.scheme import Scheme
from src.dss.infrastructure.database.scheme_codec import scheme_from_row
from src.dss.infrastructure.sessions.codec import session_from_item
from src.models import session
from src.models.api import SchemeDetailResponse
from src.models.scheme import Scheme as LegacyScheme
from src.utils.scheme_catalog import _load_catalog, get_required_profile_fields_for_life_event


def test_clock_port_keeps_identity() -> None:
    assert Clock is DomainClock


def test_expanded_models_work() -> None:
    profile = UserProfile(age=30, life_event="HOUSING", annual_income=100000)
    current = Session(user_id="synthetic", user_profile=profile)
    assert current.with_state(ConversationState.MATCHING).state is ConversationState.SCHEME_MATCHING
    assert current.user_profile.model_dump() == profile.model_dump()
    assert issubclass(session.Session, Session)
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
    original = Session(user_id="synthetic").to_dynamodb_item()
    for state in [None, "UNKNOWN", "UNDERSTANDING", "MATCHING", "PRESENTING", "DETAILS", "APPLICATION", "HANDOFF", *[s.value for s in ConversationState]]:
        for profile in [{}, {"life_event": "HOUSING"}]:
            item = {**original, "state": state, "user_profile": profile}
            assert session_from_item(Session, item).model_dump() == session.Session.from_dynamodb_item(item).model_dump()


def test_legacy_profile_and_session_copies_keep_helpers() -> None:
    legacy = session.Session(user_id="synthetic", user_profile={"life_event": "HOUSING", "age": 30, "annual_income": 100000})
    copied = legacy.copy_with()
    assert type(copied) is session.Session
    assert copied.user_profile.is_complete_for_matching is True
    merged = copied.user_profile.merge_with(session.UserProfile(gender="female"))
    assert type(merged) is session.UserProfile
    assert merged.required_fields_for_matching() == ("life_event", "age", "annual_income")
    assert session.ConversationState is ConversationState
    updated = legacy.with_profile(UserProfile(life_event="HOUSING", age=40, annual_income=100000))
    assert type(updated) is session.Session
    assert type(updated.user_profile) is session.UserProfile
    assert updated.user_profile.age == 40


def test_scheme_codec_matches_legacy_hydration() -> None:
    row = {"id": "SCH-DELHI-001", "name": "Synthetic", "name_hindi": "Synthetic", "department": "Synthetic", "department_hindi": "Synthetic", "level": "state", "description": "Synthetic", "description_hindi": "Synthetic", "eligibility": '{"categories": ["EWS", "LIG"]}', "helpline": '{"phone": ["100", "200"]}', "metadata": '{"synthetic": true}', "life_events": ["STALE"], "tags": ["STALE"]}
    assert scheme_from_row(Scheme, row).model_dump() == LegacyScheme.from_db_row(row).model_dump()
    hydrated = scheme_from_row(Scheme, row)
    assert SchemeDetailResponse(scheme=hydrated).scheme is hydrated
