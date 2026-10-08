"""Shared plain-text formatting for conversation scheme views."""

from src.dss.application.conversation.language import text_variant
from src.dss.domain.profiles.profile import UserProfile
from src.dss.domain.schemes.scheme import EligibilityCriteria, SchemeMatch

LIFE_EVENT_ICONS = {
    "HOUSING": "🏠", "HEALTH_CRISIS": "🏥", "EDUCATION": "📚", "DEATH_IN_FAMILY": "🙏",
    "MARITAL_DISTRESS": "🙏", "BUSINESS_STARTUP": "💼", "JOB_LOSS": "💼",
    "WOMEN_EMPOWERMENT": "👩", "CHILDBIRTH": "👶", "MARRIAGE": "💒",
}
SEVERITY_ICONS = {"critical": "🔴", "high": "🟠", "warning": "🟡"}
DEFAULT_SCHEME_ICON = "📋"
MAX_LISTED_SCHEMES = 5
MAX_LISTED_DOCUMENTS = 5
MAX_LISTED_WARNINGS = 5
MAX_LISTED_OFFICES = 3
MAX_DESCRIPTION_LEN = 380
MAX_DEPARTMENT_LEN = 40
MAX_AUTHORITY_LEN = 80
MAX_WARNING_LEN = 220
MAX_ADDRESS_LEN = 60
_LAKH = 100_000
_CRORE = 10_000_000
_SENTENCE_ENDINGS = (". ", "! ", "? ", ".\n", "!\n", "?\n", "। ", "।\n", "।")
_MIN_BOUNDARY_RATIO = 0.5


def format_currency_plain(amount: int | float | None, language: str = "hi") -> str:
    """Format an amount in Indian lakh/crore notation."""
    if amount is None:
        return ""
    if amount >= _CRORE:
        crores = amount / _CRORE
        label = "करोड़" if language == "hi" else "Cr"
        return f"₹{crores:.1f} {label}" if crores != int(crores) else f"₹{int(crores)} {label}"
    if amount >= _LAKH:
        lakhs = amount / _LAKH
        label = "लाख" if language == "hi" else "lakh"
        return f"₹{lakhs:.1f} {label}" if lakhs != int(lakhs) else f"₹{int(lakhs)} {label}"
    return f"₹{amount:,.0f}"


def truncate_at_word(text: str, max_len: int, ellipsis: str = "...") -> str:
    """Truncate at a word boundary so the last word is not cut in half."""
    if len(text) <= max_len:
        return text
    truncated = text[: max_len - len(ellipsis)]
    last_space = truncated.rfind(" ")
    if last_space > max_len * _MIN_BOUNDARY_RATIO:
        truncated = truncated[:last_space]
    return truncated.rstrip() + ellipsis


def truncate_at_sentence(text: str, max_len: int, ellipsis: str = "...") -> str:
    """Prefer sentence boundaries when shortening long text for chat output.

    Recognises the Devanagari danda alongside Latin sentence endings, and
    falls back to word truncation when no boundary is late enough to be worth
    using.
    """
    if len(text) <= max_len:
        return text
    sentence_end = max(
        (text.rfind(marker, 0, max_len) + 1 for marker in _SENTENCE_ENDINGS
         if text.rfind(marker, 0, max_len) != -1), default=-1,
    )
    if sentence_end >= max_len * _MIN_BOUNDARY_RATIO:
        return text[:sentence_end].rstrip()
    return truncate_at_word(text, max_len, ellipsis)


def _scheme_icon(life_events: list[str], preferred_life_event: str | None) -> str:
    """Pick the icon for a scheme, preferring the user's own life event.

    A scheme often covers several life events; showing the icon for the one
    the user actually asked about makes the list easier to scan.
    """
    ordered = list(life_events)
    if preferred_life_event and preferred_life_event in ordered:
        ordered = [preferred_life_event] + [event for event in ordered if event != preferred_life_event]
    for event in ordered:
        if event in LIFE_EVENT_ICONS:
            return LIFE_EVENT_ICONS[event]
    return DEFAULT_SCHEME_ICON


def _scheme_not_found(language: str) -> str:
    """Message shown when a scheme id no longer resolves."""
    return text_variant(language, "योजना नहीं मिली।", "Scheme not found.", "Scheme nahi mili.")


def build_presented_scheme_selection_text(
    presented_schemes: list[dict[str, str]], language: str,
) -> str | None:
    """Render stored presented schemes without needing full match payloads."""
    if not presented_schemes:
        return None
    header = text_variant(language, "🎯 आपने ये योजना विकल्प देखे थे:", "🎯 You were viewing these scheme options:", "🎯 Aap ye scheme options dekh rahe the:")
    footer = text_variant(language, "नीचे बटन दबाकर योजना चुनें।", "Tap a button below to open a scheme.", "Neeche button dabakar scheme kholiye.")
    lines = [header, ""]
    for index, scheme in enumerate(presented_schemes[:MAX_LISTED_SCHEMES], 1):
        name = scheme.get("name_hindi") if language == "hi" else scheme.get("name")
        display_name = name or scheme.get("name") or scheme.get("name_hindi") or "Scheme"
        lines.append(f"{index}. {display_name}")
    lines.extend(["", footer])
    return "\n".join(lines)


def build_multi_beneficiary_scope_response(language: str) -> str:
    """Explain how to handle self-plus-child support questions during collection."""
    return text_variant(
        language,
        "मैं आपकी और आपकी बेटी दोनों की मदद कर सकता हूँ, लेकिन सही योजना मिलाने के लिए "
        "एक समय में एक आवेदक पर ध्यान देना बेहतर रहेगा। अभी बताइए कि पहले योजनाएँ "
        "किसके लिए देखनी हैं, आपके लिए या आपकी बेटी के लिए?",
        "I can help both you and your daughter, but it is more accurate to check "
        "schemes for one applicant at a time. Please tell me whose schemes you want "
        "to focus on first: yours or your daughter's?",
        "Main aapki aur aapki beti dono ki madad kar sakta hoon, lekin sahi matching "
        "ke liye ek time par ek applicant par focus karna better rahega. Ab batayiye "
        "pehle schemes kiske liye dekhni hain, aapke liye ya aapki beti ke liye?",
    )


def build_select_scheme_first_text(language: str) -> str:
    """Prompt shown when a scheme view is requested with no scheme selected."""
    return text_variant(language, "कृपया पहले एक योजना चुनें।", "Please select a scheme first.", "Please pehle ek scheme select kijiye.")


def build_scheme_list_text(schemes: list[SchemeMatch], profile: UserProfile, language: str) -> str:
    """Build a numbered, plain-text scheme list with eligibility info."""
    if not schemes:
        return text_variant(language, "कोई योजना नहीं मिली।", "No matching schemes found.", "Koi matching scheme nahi mili.")
    header = text_variant(language, "🎯 आपके लिए ये योजनाएं मिली हैं:", "🎯 Found these schemes for you:", "🎯 Aapke liye ye schemes mili hain:")
    lines = [header, ""]
    for index, match in enumerate(schemes[:MAX_LISTED_SCHEMES], 1):
        scheme = match.scheme
        icon = _scheme_icon(scheme.life_events, profile.life_event)
        name = scheme.name_hindi if language == "hi" else scheme.name
        lines.append(f"{index}. {icon} {name}")
        if scheme.benefits_amount:
            amount_str = format_currency_plain(scheme.benefits_amount, language)
            freq_map = {
                "monthly": text_variant(language, "मासिक", "/month", "per month"),
                "yearly": text_variant(language, "वार्षिक", "/year", "per year"),
                "one-time": text_variant(language, "एकमुश्त", "one-time", "one-time"),
                "installments": text_variant(language, "किश्तों में", "in installments", "installments mein"),
            }
            freq_display = freq_map.get(scheme.benefits_frequency or "", "")
            benefit_label = text_variant(language, "लाभ", "Benefit", "Benefit")
            lines.append(f"   💰 {benefit_label}: {amount_str} {freq_display}".rstrip())
        dept = scheme.department_hindi if language == "hi" else scheme.department
        if len(dept) > MAX_DEPARTMENT_LEN:
            dept = dept[: MAX_DEPARTMENT_LEN - 3] + "..."
        dept_label = text_variant(language, "विभाग", "Dept", "Dept")
        lines.append(f"   🏛️ {dept_label}: {dept}")
        if match.eligibility_match:
            lines.append(f"   {_eligibility_summary(match.eligibility_match, language)}")
        lines.append("")
    lines.append(text_variant(language, "👆 नीचे बटन दबाएं या नंबर बताएं।", "👆 Tap a button below or type the number.", "👆 Neeche button dabaiye ya number type kijiye."))
    return "\n".join(lines)


def _eligibility_summary(eligibility_match: dict[str, bool], language: str) -> str:
    """Render the per-field eligibility ticks for one scheme."""
    field_labels = {"age": ("आयु", "Age"), "income": ("आय", "Income"), "income_segment": ("आय वर्ग", "Income band"), "category": ("श्रेणी", "Category"), "gender": ("लिंग", "Gender")}
    parts = []
    for field, is_match in eligibility_match.items():
        hi_label, en_label = field_labels.get(field, (field, field))
        label = hi_label if language == "hi" else en_label
        parts.append(f"{label} {'✓' if is_match else '✗'}")
    prefix = (text_variant(language, "✅ पात्र", "✅ Eligible", "✅ Eligible") if all(eligibility_match.values()) else text_variant(language, "⚠️ जाँचें", "⚠️ Check", "⚠️ Check"))
    return f"{prefix}: {' • '.join(parts)}"


def _eligibility_rule_parts(elig: EligibilityCriteria, language: str) -> list[str]:
    """Summarise a scheme's own eligibility rules, independent of the user."""
    parts = []
    if elig.min_age or elig.max_age:
        age_label = text_variant(language, "आयु", "Age", "Age")
        parts.append(f"{age_label}: {elig.min_age or 18}-{elig.max_age or '∞'}")
    if elig.max_income:
        income_label = text_variant(language, "अधिकतम आय", "Max income", "Max income")
        parts.append(f"{income_label}: {format_currency_plain(elig.max_income, language)}")
    if elig.caste_categories:
        cat_label = text_variant(language, "श्रेणी", "Category", "Category")
        parts.append(f"{cat_label}: {', '.join(elig.caste_categories)}")
    if elig.income_segments:
        band_label = text_variant(language, "आय वर्ग", "Income band", "Income band")
        parts.append(f"{band_label}: {', '.join(elig.income_segments)}")
    return parts


def _match_reason_lines(match_details: dict[str, bool], profile: UserProfile, language: str) -> list[str]:
    """Explain which of the user's own values satisfied the scheme's rules."""
    lines = []
    for field, is_match in match_details.items():
        if not is_match:
            continue
        if field == "age" and profile.age is not None:
            label = text_variant(language, "आयु मेल खाती है", "Age matches", "Age match karti hai")
            lines.append(f"• {label}: {profile.age}")
        elif field == "category" and profile.category:
            label = text_variant(language, "श्रेणी मेल खाती है", "Category matches", "Category match karti hai")
            lines.append(f"• {label}: {profile.category}")
        elif field == "gender" and profile.gender:
            label = text_variant(language, "लिंग मेल खाता है", "Gender matches", "Gender match karta hai")
            lines.append(f"• {label}: {profile.gender}")
        elif field == "income" and profile.annual_income is not None:
            label = text_variant(language, "आय सीमा के भीतर है", "Income is within range", "Income range ke andar hai")
            lines.append(f"• {label}: {format_currency_plain(profile.annual_income, language)}")
        elif field == "income_segment" and profile.annual_income is not None:
            label = text_variant(language, "आय वर्ग उपयुक्त है", "Income band fits", "Income band fit hota hai")
            lines.append(f"• {label}: {format_currency_plain(profile.annual_income, language)}")
    return lines
