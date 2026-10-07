"""Catalog-bound profile questions and extraction for one application graph."""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from src.dss.application.conversation import profile_extractor
from src.dss.domain.profiles.profile import UserProfile

CatalogValues = Iterable[Mapping[str, Any]]


class ProfileFields:
    def __init__(self, catalog: Callable[[], CatalogValues]) -> None:
        self.catalog = catalog

    def _values(self, profile: UserProfile) -> CatalogValues:
        return self.catalog() if profile.life_event else ()

    def get_required_matching_fields(self, profile: UserProfile) -> tuple[str, ...]:
        return profile_extractor.get_required_matching_fields(profile, catalog=self._values(profile))

    def is_complete_for_matching(self, profile: UserProfile) -> bool:
        return profile_extractor.is_complete_for_matching(profile, catalog=self._values(profile))

    def get_missing_fields(self, profile: UserProfile) -> list[str]:
        return profile_extractor.get_missing_fields(profile, catalog=self._values(profile))

    def get_next_missing_field(
        self, profile: UserProfile, skipped_fields: list[str] | None = None,
    ) -> str | None:
        return profile_extractor.get_next_missing_field(
            profile, skipped_fields, catalog=self._values(profile),
        )

    def get_next_question(
        self, profile: UserProfile, language: str = "hi",
        skipped_fields: list[str] | None = None,
    ) -> str | None:
        return profile_extractor.get_next_question(
            profile, language, skipped_fields, catalog=self._values(profile),
        )
