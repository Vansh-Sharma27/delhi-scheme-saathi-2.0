"""Required profile fields from supplied catalog values."""

from collections.abc import Iterable, Mapping
from typing import Any

_INCOME_SEGMENT_KEYS = {"EWS", "LIG", "MIG", "HIG"}


def required_profile_fields(
    life_event: str | None, catalog: Iterable[Mapping[str, Any]]
) -> tuple[str, ...]:
    """Keep the existing core fields and catalog-dependent gender/category policy."""
    if not life_event:
        return ("life_event",)

    required_fields = ["life_event", "age", "annual_income"]
    needs_category = False
    needs_gender = False
    for scheme in catalog:
        if life_event not in scheme.get("life_events", []):
            continue
        eligibility = scheme.get("eligibility") or {}
        raw_categories = {
            str(value).strip().upper()
            for value in eligibility.get("categories", [])
            if str(value).strip()
        }
        explicit_caste_categories = {
            str(value).strip().upper()
            for value in eligibility.get("caste_categories", [])
            if str(value).strip()
        }
        genders = {
            str(value).strip().lower()
            for value in eligibility.get("genders", ["all"])
            if str(value).strip()
        }
        income_by_category = {
            str(key).strip().upper()
            for key in (eligibility.get("income_by_category") or {})
            if str(key).strip()
        }
        income_segment_categories = (raw_categories | income_by_category) & _INCOME_SEGMENT_KEYS
        normalized_caste_categories = explicit_caste_categories
        if (
            not normalized_caste_categories
            and raw_categories
            and not income_segment_categories
            and raw_categories != {"ALL"}
        ):
            normalized_caste_categories = raw_categories
        if normalized_caste_categories:
            needs_category = True
        if genders and genders != {"all"}:
            needs_gender = True

    if needs_gender:
        required_fields.append("gender")
    if needs_category:
        required_fields.append("category")
    return tuple(required_fields)
