"""Response language selection and script detection."""

import re
from typing import Any, cast

from src.dss.domain.conversations.session import Session
from src.dss.infrastructure.ai.fallback_client import FallbackLLMClient


def _pick_language_text(
    language: str,
    hi: str,
    en: str,
    hinglish: str | None = None,
) -> str:
    """Pick a text variant for the requested language."""
    if language == "hi":
        return hi
    if language == "hinglish":
        return hinglish or en
    return en


def _count_latin_tokens(text: str) -> int:
    """Count meaningful Latin-script words in a response."""
    return len(re.findall(r"[A-Za-z]{3,}", text))


def _count_devanagari_tokens(text: str) -> int:
    """Count meaningful Devanagari-script words in a response."""
    return len(re.findall(r"[\u0900-\u097F]{2,}", text))


def _count_hinglish_markers(text: str) -> int:
    """Count common Roman Hindi / Hinglish markers."""
    text_lower = text.lower()
    markers = (
        "aap",
        "apni",
        "apna",
        "hai",
        "hain",
        "kya",
        "kaise",
        "kyon",
        "kyu",
        "batayiye",
        "madad",
        "liye",
        "ke",
        "ki",
        "ka",
        "kar",
        "karna",
        "pooch",
        "dekhiye",
        "chahein",
        "yojana",
        "scheme",
    )
    return sum(
        1 for marker in markers if re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text_lower)
    )


def _needs_grounded_translation(text: str, language: str) -> bool:
    """Return True when deterministic grounded text still leaks source language."""
    if language not in {"hi", "en", "hinglish"}:
        return False

    stripped = text.strip()
    if not stripped:
        return False

    latin_tokens = _count_latin_tokens(stripped)
    devanagari_tokens = _count_devanagari_tokens(stripped)

    if language == "hi":
        return latin_tokens > 0
    if language == "en":
        return devanagari_tokens > 0
    if devanagari_tokens > 0:
        return True
    return latin_tokens >= 4 and _count_hinglish_markers(stripped) < 2


def _needs_language_normalization(text: str, language: str) -> bool:
    """Return True when reply text drifts away from the requested language/script."""
    if language not in {"hi", "en", "hinglish"}:
        return False

    stripped = text.strip()
    if not stripped:
        return False

    latin_tokens = _count_latin_tokens(stripped)
    devanagari_tokens = _count_devanagari_tokens(stripped)

    if language == "hi":
        if latin_tokens == 0:
            return False
        if devanagari_tokens == 0:
            return True
        return latin_tokens > devanagari_tokens

    if language == "en":
        return devanagari_tokens > 0

    if devanagari_tokens > 0:
        return True
    if latin_tokens == 0:
        return False

    hinglish_markers = _count_hinglish_markers(stripped)
    return latin_tokens >= 6 and hinglish_markers < 2


LANGUAGE_NORMALIZATION_PROMPT = """
You rewrite Delhi government welfare bot replies into the requested output language.

Rules:
- Rewrite only the text provided in context.source_text.
- Preserve all facts, numbers, rupee amounts, URLs, phone numbers, office names, addresses, and IDs.
- Keep the same order, bullets, and step structure.
- Do not add advice, omissions, or new facts.
- If a term is already a proper noun or official title, keep it intact and rewrite the surrounding text.
- For Hindi, output natural Hindi in Devanagari script.
- For Hinglish, output natural Roman-script Hinglish only. Do not use Devanagari.
- For English, output plain English only.
- Return only the rewritten reply text.
""".strip()


async def _rewrite_response_language(
    session: Session,
    text: str,
    language: str,
    *,
    get_ai_orchestrator: Any,
) -> str:
    """Rewrite a response using the shared Bedrock/Grok translation path."""
    if not text.strip():
        return text

    translated = await get_ai_orchestrator().generate_response(
        session=session,
        context={
            "response_mode": "language_normalization",
            "source_text": text,
        },
        system_prompt=LANGUAGE_NORMALIZATION_PROMPT,
        user_language=language,
    )

    if not translated.strip():
        return text

    safe_fallback = FallbackLLMClient._safe_generation_text(language)
    if translated.strip() == safe_fallback.strip():
        return text

    return cast(str, translated.strip())


async def ensure_response_language(
    session: Session,
    text: str,
    language: str,
    *,
    rewrite: Any,
) -> str:
    """Rewrite a reply into the requested language when it drifted off target."""
    if not text.strip() or not _needs_language_normalization(text, language):
        return text

    return cast(str, await rewrite(session, text, language))


async def translate_grounded_text_if_needed(
    session: Session,
    text: str,
    language: str,
    *,
    rewrite: Any,
) -> str:
    """Faithfully translate grounded text when the target language needs it.

    This is only for already-grounded deterministic text. If the translation
    path is unavailable, we keep the original grounded text instead of
    returning an error stub.
    """
    if not text.strip() or not _needs_grounded_translation(text, language):
        return text
    return cast(str, await rewrite(session, text, language))
