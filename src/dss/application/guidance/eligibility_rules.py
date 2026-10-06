"""Localized labels and structured eligibility rule descriptions."""

from src.dss.application.guidance.currency import _format_currency
from src.dss.application.guidance.localization import _pick_language_text
from src.dss.domain.schemes.scheme import Scheme


def _eligibility_field_label(field: str, language: str) -> str:
    """Render a field label in the response language."""
    labels = {
        "age": {"hi": "उम्र", "en": "age", "hinglish": "age"},
        "gender": {"hi": "लिंग", "en": "gender", "hinglish": "gender"},
        "income": {"hi": "आय", "en": "income", "hinglish": "income"},
        "category": {"hi": "श्रेणी", "en": "category", "hinglish": "category"},
    }
    field_labels = labels.get(field, labels["age"])
    return field_labels.get(language, field_labels["en"])


def _build_eligibility_rule_text(scheme: Scheme, language: str) -> list[str]:
    """Build concise human-readable rule bullets from structured eligibility data."""
    elig = scheme.eligibility
    rules: list[str] = []

    if elig.min_age is not None and elig.max_age is not None:
        rules.append(
            _pick_language_text(
                language,
                f"उम्र {elig.min_age} से {elig.max_age} वर्ष के बीच",
                f"age between {elig.min_age} and {elig.max_age}",
                f"age {elig.min_age} se {elig.max_age} ke beech",
            )
        )
    elif elig.min_age is not None:
        rules.append(
            _pick_language_text(
                language,
                f"उम्र कम से कम {elig.min_age} वर्ष",
                f"age {elig.min_age} or above",
                f"age kam se kam {elig.min_age} years",
            )
        )
    elif elig.max_age is not None:
        rules.append(
            _pick_language_text(
                language,
                f"उम्र {elig.max_age} वर्ष तक",
                f"age up to {elig.max_age}",
                f"age {elig.max_age} tak",
            )
        )

    restricted_genders = [gender for gender in elig.genders if gender.lower() != "all"]
    if restricted_genders:
        if len(restricted_genders) == 1 and restricted_genders[0].lower() == "female":
            rules.append(
                _pick_language_text(
                    language,
                    "महिला आवेदक",
                    "women applicants",
                    "female applicants",
                )
            )
        elif len(restricted_genders) == 1 and restricted_genders[0].lower() == "male":
            rules.append(
                _pick_language_text(
                    language,
                    "पुरुष आवेदक",
                    "male applicants",
                    "male applicants",
                )
            )
        else:
            gender_text = ", ".join(restricted_genders)
            rules.append(
                _pick_language_text(
                    language,
                    f"लिंग शर्त: {gender_text}",
                    f"gender condition: {gender_text}",
                    f"gender condition: {gender_text}",
                )
            )

    if elig.max_income is not None:
        income_text = _format_currency(elig.max_income)
        rules.append(
            _pick_language_text(
                language,
                f"वार्षिक पारिवारिक आय {income_text} तक",
                f"annual family income up to {income_text}",
                f"annual family income {income_text} tak",
            )
        )
    elif elig.income_by_category:
        limits = ", ".join(
            f"{segment.upper()} {_format_currency(limit)}"
            for segment, limit in sorted(
                ((str(segment), int(limit)) for segment, limit in elig.income_by_category.items()),
                key=lambda item: item[1],
            )
        )
        rules.append(
            _pick_language_text(
                language,
                f"आय सीमा band के अनुसार: {limits}",
                f"income limits depend on the band: {limits}",
                f"income limit band ke hisaab se hai: {limits}",
            )
        )

    if elig.caste_categories and not any(
        category.upper() == "ALL" for category in elig.caste_categories
    ):
        category_text = ", ".join(elig.caste_categories)
        rules.append(
            _pick_language_text(
                language,
                f"श्रेणी शर्त: {category_text}",
                f"category condition: {category_text}",
                f"category condition: {category_text}",
            )
        )

    return rules
