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
from src.models import session
from src.utils.scheme_catalog import _load_catalog, get_required_profile_fields_for_life_event


def test_clock_port_keeps_identity() -> None:
    assert Clock is DomainClock


def test_expanded_models_work() -> None:
    profile = UserProfile(age=30, life_event="HOUSING", annual_income=100000)
    current = Session(user_id="synthetic", user_profile=profile)
    assert current.with_state(ConversationState.MATCHING).state is ConversationState.SCHEME_MATCHING
    assert current.user_profile.model_dump() == profile.model_dump()
    assert Session is session.Session
    assert Scheme.model_fields["is_active"].default is True
    assert Document.model_fields["prerequisites"].default_factory is list
    assert Office.model_fields["distance_km"].default is None


def test_pure_required_fields_matches_catalog_policy() -> None:
    catalog = _load_catalog()
    events = {event for scheme in catalog.values() for event in scheme.get("life_events", [])}
    for event in [None, "UNKNOWN", *sorted(events)]:
        assert required_profile_fields(event, catalog.values()) == get_required_profile_fields_for_life_event(event)
    assert required_profile_fields("SYNTHETIC", [{"life_events": ["SYNTHETIC"], "eligibility": {"genders": ["female"], "categories": ["SC"]}}]) == ("life_event", "age", "annual_income", "gender", "category")
