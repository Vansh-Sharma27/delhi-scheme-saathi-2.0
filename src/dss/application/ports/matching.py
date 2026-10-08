"""Typed deterministic matching capability shared with conversation rendering."""

from typing import Protocol

from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import SchemeMatch


class MatchSchemes(Protocol):
    async def __call__(
        self, *, profile: UserProfile, query_text: str | None,
    ) -> list[SchemeMatch]: ...
