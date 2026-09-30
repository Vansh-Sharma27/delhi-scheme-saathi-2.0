"""Legacy model conveniences, retained until Phase 6."""

from collections.abc import Iterable, Mapping
from typing import Any, Self

from pydantic import Field

from src.dss.domain.conversations.clock import Clock
from src.dss.domain.conversations.session import ConversationMemory as ConversationMemory
from src.dss.domain.conversations.session import Message as Message
from src.dss.domain.conversations.session import Session as DomainSession
from src.dss.domain.conversations.states import ConversationState as ConversationState
from src.dss.domain.profiles.profile import UserProfile as DomainProfile
from src.dss.infrastructure.database.catalog import _load_catalog
from src.dss.infrastructure.sessions.codec import (
    _normalize_persisted_state as _normalize_persisted_state,
)
from src.dss.infrastructure.sessions.codec import session_from_item


class UserProfile(DomainProfile):
    """Preserve no-argument catalog-aware profile helpers."""

    def required_fields_for_matching(
        self, catalog: Iterable[Mapping[str, Any]] | None = None
    ) -> tuple[str, ...]:
        values = catalog if catalog is not None else (_load_catalog().values() if self.life_event else ())
        return super().required_fields_for_matching(values)

    @property
    def is_complete_for_matching(self) -> bool:
        return all(getattr(self, field) is not None for field in self.required_fields_for_matching())


class Session(DomainSession):
    """Preserve legacy hydration and nested profile convenience methods."""

    user_profile: UserProfile = Field(default_factory=UserProfile)

    @classmethod
    def from_dynamodb_item(
        cls, item: dict[str, Any], *, clock: Clock | None = None
    ) -> Self:
        return session_from_item(cls, item, clock=clock, profile_type=UserProfile)
