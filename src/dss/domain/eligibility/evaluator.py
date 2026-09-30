"""Deterministic eligibility evaluation, preserving the current omissions."""

from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme

INCOME_SEGMENT_ORDER = ("EWS", "LIG", "MIG", "HIG")


def _lookup_case_insensitive(mapping: dict[str, int], key: str) -> int | None:
    """Return the matching numeric value for a case-insensitive key."""
    target = key.upper()
    for candidate, value in mapping.items():
        if candidate.upper() == target:
            return value
    return None


def _infer_income_segment(
    annual_income: int,
    income_limits: dict[str, int],
) -> str | None:
    """Infer the user's income band from ordered segment thresholds."""
    normalized_limits: list[tuple[str, int]] = []
    for segment, raw_limit in income_limits.items():
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            continue
        normalized_limits.append((segment.upper(), limit))
    if not normalized_limits:
        return None
    ordered: list[tuple[str, int]] = []
    seen: set[str] = set()
    sorted_limits = sorted(normalized_limits, key=lambda item: item[1])
    for segment_name in INCOME_SEGMENT_ORDER:
        for segment, limit in sorted_limits:
            if segment == segment_name and segment not in seen:
                ordered.append((segment, limit))
                seen.add(segment)
    for segment, limit in sorted_limits:
        if segment not in seen:
            ordered.append((segment, limit))
            seen.add(segment)
    for segment, limit in ordered:
        if annual_income <= limit:
            return segment
    return None


def calculate_eligibility_match(scheme: Scheme, profile: UserProfile) -> dict[str, bool]:
    """Calculate which eligibility criteria the user matches."""
    match = {}
    elig = scheme.eligibility
    # Age check
    if profile.age is not None:
        age_ok = True
        if elig.min_age is not None and profile.age < elig.min_age:
            age_ok = False
        if elig.max_age is not None and profile.age > elig.max_age:
            age_ok = False
        match["age"] = age_ok
    # Gender check
    if profile.gender is not None:
        match["gender"] = (
            "all" in elig.genders
            or profile.gender.lower() in [g.lower() for g in elig.genders]
        )
    # Category check
    if (
        profile.category is not None
        and elig.caste_categories
        and not any(category.upper() == "ALL" for category in elig.caste_categories)
    ):
        match["category"] = (
            profile.category.upper() in [c.upper() for c in elig.caste_categories]
        )
    # Income check
    if profile.annual_income is not None:
        income_ok = True
        if elig.max_income is not None and profile.annual_income > elig.max_income:
            income_ok = False
        if elig.has_income_segment_restrictions and elig.income_by_category:
            inferred_segment = _infer_income_segment(
                profile.annual_income,
                elig.income_by_category,
            )
            allowed_segments = [segment.upper() for segment in elig.income_segments]
            segment_ok = inferred_segment in allowed_segments if inferred_segment else False
            match["income_segment"] = segment_ok
            income_ok = income_ok and segment_ok
        elif profile.category and elig.income_by_category:
            cat_limit = _lookup_case_insensitive(
                elig.income_by_category,
                profile.category,
            )
            if cat_limit is not None and profile.annual_income > cat_limit:
                income_ok = False
        match["income"] = income_ok
    return match
