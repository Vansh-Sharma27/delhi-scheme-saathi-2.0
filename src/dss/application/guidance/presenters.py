"""Format already-evaluated eligibility and matching facts."""

import re

from src.dss.application.guidance.currency import _format_currency
from src.dss.application.guidance.eligibility_rules import (
    _build_eligibility_rule_text,
    _eligibility_field_label,
)
from src.dss.application.guidance.localization import _pick_language_text
from src.dss.domain.eligibility.presentation_facts import EligibilityFacts
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme

ELIGIBILITY_QUESTION_PATTERNS = (
    r"\beligib(?:le|ility)\b",
    r"\bqualif(?:y|ies|ied)\b",
    r"\bcriteria\b",
    r"\bcan (?:i|we|she|he|they) apply\b",
    r"\bwho can apply\b",
    r"\bam i eligible\b",
    r"\bdo(?:es)? .* qualify\b",
    r"\bpatar(?:ta|ता)\b",
    r"\bयोग्य\b",
    r"\bपात्र\b",
    r"qualify",
)
JUSTIFICATION_QUESTION_PATTERNS = (
    r"\bjustify\b",
    r"\bwhy (?:this|that) scheme\b",
    r"\bwhy did you suggest\b",
    r"\bwhy did you recommend\b",
    r"\bwhy was this shown\b",
    r"क्यों सुझा",
    r"क्यों recommend",
)


def _is_eligibility_question(user_question: str) -> bool:
    """Return True when the user is asking about eligibility or qualification."""
    return any(
        re.search(pattern, user_question, re.IGNORECASE)
        for pattern in ELIGIBILITY_QUESTION_PATTERNS
    )


def _is_justification_question(user_question: str) -> bool:
    """Return True when the user asks why the scheme was suggested."""
    return any(
        re.search(pattern, user_question, re.IGNORECASE)
        for pattern in JUSTIFICATION_QUESTION_PATTERNS
    )


def _maybe_generate_eligibility_response(
    scheme: Scheme,
    profile: UserProfile,
    user_question: str,
    language: str,
    *,
    facts: EligibilityFacts,
) -> str | None:
    """Answer eligibility questions from structured scheme data without using the LLM."""
    if not _is_eligibility_question(user_question):
        return None

    rule_text = _build_eligibility_rule_text(scheme, language)
    if not rule_text:
        return None

    elig = scheme.eligibility
    failed_fields = facts.failed_fields
    missing_fields = facts.missing_fields
    checked_fields = facts.checked_fields
    has_category_restriction = facts.has_category_restriction

    checked_fields_text = ", ".join(
        _eligibility_field_label(field, language) for field in checked_fields
    )
    missing_fields_text = ", ".join(
        _eligibility_field_label(field, language) for field in missing_fields
    )
    failed_fields_text = ", ".join(
        _eligibility_field_label(field, language) for field in failed_fields
    )

    category_note = None
    if profile.category and not has_category_restriction:
        category_note = _pick_language_text(
            language,
            f"{profile.category} श्रेणी अपने-आप में समस्या नहीं है, क्योंकि मेरे पास जो scheme data है उसमें caste-category restriction नहीं दिख रही।",
            f"{profile.category} category does not disqualify the applicant because this scheme does not have a caste-category restriction in the data I have.",
            f"{profile.category} category se problem nahi hai, kyunki mere paas jo scheme data hai usmein caste-category restriction nahi dikh rahi.",
        )
    elif profile.category and has_category_restriction and "category" in failed_fields:
        allowed_categories = ", ".join(elig.caste_categories)
        category_note = _pick_language_text(
            language,
            f"मेरे पास जो data है उसके अनुसार यह scheme केवल {allowed_categories} श्रेणी के लिए है, इसलिए {profile.category} match नहीं करती।",
            f"In the scheme data I have, this scheme is limited to {allowed_categories}, so {profile.category} does not match the category rule.",
            f"Mere paas jo scheme data hai uske hisaab se yeh scheme sirf {allowed_categories} ke liye hai, isliye {profile.category} category match nahi karti.",
        )

    if failed_fields:
        status_text = _pick_language_text(
            language,
            f"अभी साझा की गई जानकारी के आधार पर applicant {failed_fields_text} check पर fit नहीं लगते।",
            f"Based on the details shared so far, the applicant does not appear eligible on the {failed_fields_text} check.",
            f"Ab tak ki details ke hisaab se applicant {failed_fields_text} check par fit nahi lagte.",
        )
    elif missing_fields:
        status_text = _pick_language_text(
            language,
            f"अभी तक की जानकारी के आधार पर applicant eligible हो सकते हैं, लेकिन {missing_fields_text} confirm करना बाकी है।",
            f"Based on the details shared so far, the applicant may qualify, but {missing_fields_text} still needs to be confirmed.",
            f"Ab tak ki details ke hisaab se applicant qualify kar sakte hain, lekin {missing_fields_text} abhi confirm karna baaki hai.",
        )
    else:
        status_text = _pick_language_text(
            language,
            f"अभी साझा की गई जानकारी के आधार पर applicant {checked_fields_text} checks पर eligible लगते हैं।",
            f"Based on the details shared so far, the applicant appears eligible on the available {checked_fields_text} checks.",
            f"Ab tak ki details ke hisaab se applicant available {checked_fields_text} checks par eligible lagte hain.",
        )

    final_note = _pick_language_text(
        language,
        "अंतिम मंजूरी दस्तावेज़ जाँच और विभाग की बाकी शर्तों पर भी निर्भर करेगी।",
        "Final approval will still depend on document verification and any other departmental checks.",
        "Final approval documents verification aur department ke baaki checks par bhi depend karega.",
    )

    lines = [
        _pick_language_text(
            language,
            f"मेरे पास जो scheme data है उसके अनुसार मुख्य eligibility checks हैं: {'; '.join(rule_text)}.",
            f"From the scheme data I have, the main eligibility checks are: {'; '.join(rule_text)}.",
            f"Mere paas jo scheme data hai uske hisaab se main eligibility checks hain: {'; '.join(rule_text)}.",
        ),
    ]
    if category_note:
        lines.append(category_note)
    lines.append(status_text)
    lines.append(final_note)
    return " ".join(lines)


def _build_matching_reason_context(
    scheme: Scheme, profile: UserProfile, eligibility_match: dict[str, bool]
) -> list[str]:
    """Collect grounded reasons the scheme could fit the current profile."""
    reasons: list[str] = []
    elig = scheme.eligibility
    scheme_text = " ".join(
        [
            scheme.name,
            scheme.name_hindi,
            scheme.description[:400],
            scheme.description_hindi[:400],
            " ".join(scheme.tags[:12]),
        ]
    ).lower()

    if profile.life_event and profile.life_event in scheme.life_events:
        reasons.append(f"The scheme is tagged for the same need area: {profile.life_event}.")

    if profile.marital_status == "widowed" and any(
        keyword in scheme_text for keyword in ("widow", "widowed", "vidhwa", "विधवा")
    ):
        reasons.append("The scheme itself is specifically framed for widowed women.")

    if (
        profile.gender
        and eligibility_match.get("gender")
        and elig.genders
        and "all" not in [gender.lower() for gender in elig.genders]
    ):
        reasons.append(
            f"The scheme is gender-restricted and the user profile says {profile.gender}."
        )

    if (
        profile.age is not None
        and eligibility_match.get("age")
        and (elig.min_age is not None or elig.max_age is not None)
    ):
        reasons.append(
            f"Age rule in context: {elig.min_age or 18}-{elig.max_age or 'no upper limit'}; user age: {profile.age}."
        )

    if profile.annual_income is not None and eligibility_match.get("income"):
        income_text = _format_currency(profile.annual_income)
        if elig.max_income is not None:
            reasons.append(
                f"Scheme max income in context: {_format_currency(elig.max_income)}; user income: {income_text}."
            )
        elif elig.income_by_category and eligibility_match.get("income_segment"):
            reasons.append(
                f"User income: {income_text}; the scheme uses income bands {', '.join(sorted(elig.income_by_category))}."
            )

    if (
        profile.category
        and eligibility_match.get("category")
        and elig.caste_categories
        and not any(category.upper() == "ALL" for category in elig.caste_categories)
    ):
        reasons.append(
            f"Scheme category condition in context: {', '.join(elig.caste_categories)}; user category: {profile.category}."
        )

    if elig.special_focus_groups:
        reasons.append(
            f"Special focus groups in context: {', '.join(elig.special_focus_groups[:8])}."
        )

    return reasons


def _maybe_generate_scheme_justification_response(
    scheme: Scheme,
    profile: UserProfile,
    user_question: str,
    language: str,
    *,
    reasons: list[str],
) -> str | None:
    """Answer grounded why-this-scheme questions without free-form generation."""
    if not _is_justification_question(user_question):
        return None

    if not reasons:
        return _pick_language_text(
            language,
            "मैं इस scheme के बारे में सिर्फ वही कारण बताना चाहता हूँ जो data में साफ़ दिखते हैं। अभी मेरे पास इतना grounded match data नहीं है कि मैं भरोसे से reason बता सकूँ। अगर आप चाहें तो मैं उम्र, आय, श्रेणी या दूसरी eligibility details दोबारा check कर सकता हूँ।",
            "I only want to explain this scheme using grounded facts from the data. Right now I do not have enough matched rule evidence to justify it confidently. If you want, I can re-check the age, income, category, or other eligibility details.",
            "Main is scheme ko sirf grounded data ke basis par explain karna chahta hoon. Abhi mere paas itna matched rule evidence nahi hai ki main confidently reason bata sakoon. Agar chahein to main age, income, category ya doosri eligibility details dobara check kar sakta hoon.",
        )

    reasons_text = "; ".join(reasons[:3])
    return _pick_language_text(
        language,
        f"मैंने यह scheme इन grounded कारणों से दिखाई: {reasons_text} अगर चाहें तो मैं इसमें documents या application steps भी समझा सकता हूँ।",
        f"I suggested this scheme for grounded reasons from the current data: {reasons_text} If you want, I can also explain the documents or application steps.",
        f"Maine yeh scheme current data ke grounded reasons ki wajah se dikhayi: {reasons_text} Agar chahein to main documents ya application steps bhi samjha sakta hoon.",
    )
