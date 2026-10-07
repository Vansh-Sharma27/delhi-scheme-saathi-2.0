"""Facts needed by guidance, preserving the existing inference order."""

from dataclasses import dataclass

from src.dss.domain.eligibility.evaluator import calculate_eligibility_match
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme


def _infer_income_segment(income_limits: dict[str, int], annual_income: int | None) -> str | None:
    """Infer the first matching income band from configured cutoffs."""
    if annual_income is None:
        return None

    normalized_limits: list[tuple[str, int]] = []
    for segment, raw_limit in income_limits.items():
        try:
            normalized_limits.append((str(segment).upper(), int(raw_limit)))
        except (TypeError, ValueError):
            continue

    for segment, limit in sorted(normalized_limits, key=lambda item: item[1]):
        if annual_income <= limit:
            return segment
    return None


@dataclass(frozen=True)
class EligibilityFacts:
    match: dict[str, bool]
    failed_fields: list[str]
    missing_fields: list[str]
    checked_fields: list[str]
    has_category_restriction: bool


def eligibility_facts(scheme: Scheme, profile: UserProfile) -> EligibilityFacts:
    elig = scheme.eligibility
    match = calculate_eligibility_match(scheme, profile)

    failed_fields: list[str] = []
    missing_fields: list[str] = []
    checked_fields: list[str] = []

    if elig.min_age is not None or elig.max_age is not None:
        if profile.age is None:
            missing_fields.append("age")
        else:
            checked_fields.append("age")
            if not match.get("age", True):
                failed_fields.append("age")

    restricted_genders = [gender for gender in elig.genders if gender.lower() != "all"]
    if restricted_genders:
        if profile.gender is None:
            missing_fields.append("gender")
        else:
            checked_fields.append("gender")
            if not match.get("gender", True):
                failed_fields.append("gender")

    if elig.max_income is not None or elig.income_by_category:
        if profile.annual_income is None:
            missing_fields.append("income")
        else:
            checked_fields.append("income")
            if not match.get("income", True):
                failed_fields.append("income")

    has_category_restriction = bool(elig.caste_categories) and not any(
        category.upper() == "ALL" for category in elig.caste_categories
    )
    if has_category_restriction:
        if profile.category is None:
            missing_fields.append("category")
        else:
            checked_fields.append("category")
            if not match.get("category", True):
                failed_fields.append("category")
    return EligibilityFacts(
        match, failed_fields, missing_fields, checked_fields, has_category_restriction
    )
