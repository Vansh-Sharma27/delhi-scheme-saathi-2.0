"""Domain compatibility and dependency-boundary checks."""

from src.dss.application.ports.clock import Clock
from src.dss.domain.conversations.clock import Clock as DomainClock
from src.dss.domain.conversations.session import Session
from src.dss.domain.conversations.states import ConversationState
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.document import Document
from src.dss.domain.schemes.office import Office
from src.dss.domain.schemes.scheme import Scheme
from src.models import session


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
