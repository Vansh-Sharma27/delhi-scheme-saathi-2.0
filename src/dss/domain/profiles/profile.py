"""User profile values and catalog-supplied matching completeness."""

from collections.abc import Iterable, Mapping
from typing import Any, Self

from pydantic import BaseModel

from src.dss.domain.profiles.required_fields import required_profile_fields


class UserProfile(BaseModel):
    """User profile extracted from conversation (mutable for updates)."""

    age: int | None = None
    gender: str | None = None  # male, female, other
    category: str | None = None  # SC, ST, OBC, General, EWS
    annual_income: int | None = None
    employment_status: str | None = None  # employed, unemployed, self-employed, student
    marital_status: str | None = None  # single, married, widowed, divorced, separated
    life_event: str | None = None  # HOUSING, HEALTH_CRISIS, etc.
    district: str | None = None
    has_bpl_card: bool | None = None
    disability_percentage: int | None = None
    latitude: float | None = None
    longitude: float | None = None

    def merge_with(self, other: "UserProfile") -> Self:
        """Create new profile merging non-None values from other."""
        current_data = self.model_dump()
        other_data = other.model_dump()
        merged = {
            k: other_data[k] if other_data[k] is not None else current_data[k]
            for k in current_data
        }
        return type(self)(**merged)

    def required_fields_for_matching(
        self, catalog: Iterable[Mapping[str, Any]]
    ) -> tuple[str, ...]:
        """Return the scheme-aware fields from supplied catalog values."""
        return required_profile_fields(self.life_event, catalog)

    def complete_for_matching(self, catalog: Iterable[Mapping[str, Any]]) -> bool:
        """Check that every required matching field is present."""
        return all(getattr(self, field) is not None for field in self.required_fields_for_matching(catalog))

    @property
    def completeness_score(self) -> int:
        """Score 0-10 indicating profile completeness."""
        score = 0
        if self.age is not None:
            score += 2
        if self.gender is not None:
            score += 1
        if self.category is not None:
            score += 2
        if self.annual_income is not None:
            score += 2
        if self.employment_status is not None:
            score += 1
        if self.life_event is not None:
            score += 2
        return min(score, 10)
