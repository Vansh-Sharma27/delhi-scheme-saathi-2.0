"""Format scheme income-band explanations from supplied facts."""

from src.dss.application.guidance.currency import _format_currency
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import Scheme


def _maybe_generate_scheme_term_response(
    scheme: Scheme,
    profile: UserProfile,
    user_question: str,
    language: str,
    *,
    income_segment: str | None,
) -> str | None:
    """Answer common deterministic scheme-term questions without repeating the card."""
    text_lower = user_question.lower()
    asks_income_band = any(
        phrase in text_lower for phrase in ("income band", "lig", "mig", "ews", "income category")
    )
    if not asks_income_band:
        return None

    income_limits = scheme.eligibility.income_by_category
    if not income_limits:
        return None

    ordered_limits = []
    for segment, raw_limit in income_limits.items():
        try:
            ordered_limits.append((str(segment).upper(), int(raw_limit)))
        except (TypeError, ValueError):
            continue
    if not ordered_limits:
        return None

    ordered_limits.sort(key=lambda item: item[1])
    limit_text = ", ".join(
        f"{segment} up to {_format_currency(limit)}" for segment, limit in ordered_limits
    )
    user_segment = income_segment
    user_segment_text = None
    if user_segment and profile.annual_income is not None:
        user_segment_text = f"At about {_format_currency(profile.annual_income)} annual income, you fit the {user_segment} band."

    variants = {
        "hi": (
            "इस योजना में income band का मतलब वार्षिक पारिवारिक आय के आधार पर वर्ग है। "
            f"यहाँ bands हैं: {limit_text}. "
            + (
                f"आपकी करीब {_format_currency(profile.annual_income)} आय के हिसाब से आप {user_segment} band में आते हैं."
                if user_segment_text and profile.annual_income is not None
                else "अगर आप चाहें तो मैं बता सकता हूँ कि आपके लिए कौन सा band लागू होता है।"
            )
        ),
        "hinglish": (
            "Is scheme mein income band ka matlab annual family income ke hisaab se group hota hai. "
            f"Yahan bands hain: {limit_text}. "
            + (
                f"Aapki roughly {_format_currency(profile.annual_income)} income ke hisaab se aap {user_segment} band mein aate hain."
                if user_segment_text and profile.annual_income is not None
                else "Agar chahein to main aapke income ke hisaab se relevant band bhi bata sakta hoon."
            )
        ),
        "en": (
            "In this scheme, income band means the annual family income bracket used to decide which segment applies. "
            f"Here the bands are: {limit_text}. "
            + (
                user_segment_text
                if user_segment_text
                else "If you want, I can also tell you which band your income falls into."
            )
        ),
    }
    return variants.get(language, variants["en"])
