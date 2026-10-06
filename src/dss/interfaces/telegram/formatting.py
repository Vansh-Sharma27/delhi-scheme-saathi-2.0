"""Telegram text and speech formatting."""

import re

_TG_MAX_LEN = 4000


def _clean_for_telegram(text: str) -> str:
    """Normalize markdown-heavy LLM output for plain Telegram text rendering."""
    if not text:
        return ""

    # Remove markdown headers and emphasis/code markers that appear raw in Telegram.
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"`{1,3}([^`]+)`{1,3}", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)

    # Convert markdown links [text](url) to "text (url)" for readability.
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

    # Normalize spacing while preserving readable line breaks.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_message(text: str) -> list[str]:
    """Split a long message into parts that fit Telegram's length limit.

    Splits between paragraphs so a card is never cut mid-line. A single
    paragraph longer than the limit is emitted as its own oversized part
    rather than being chopped, because breaking mid-sentence in Hindi reads
    worse than one long message; the caller sends it and lets Telegram
    complain if it truly cannot fit.
    """
    if len(text) <= _TG_MAX_LEN:
        return [text]

    parts: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= _TG_MAX_LEN:
            current = candidate
            continue
        if current:
            parts.append(current.strip())
        current = paragraph

    if current:
        parts.append(current.strip())

    return parts or [text[:_TG_MAX_LEN]]


def _clean_for_tts(text: str) -> str:
    """Clean text for TTS by removing emojis and markdown."""
    # Remove emojis
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map
        "\U0001f700-\U0001f77f"  # alchemical
        "\U0001f780-\U0001f7ff"  # geometric
        "\U0001f800-\U0001f8ff"  # arrows
        "\U0001f900-\U0001f9ff"  # supplemental
        "\U0001fa00-\U0001fa6f"  # chess
        "\U0001fa70-\U0001faff"  # symbols
        "\U00002702-\U000027b0"  # dingbats
        "\U000024c2-\U0001f251"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)

    # Remove markdown formatting
    text = re.sub(r"\*+", "", text)  # bold
    text = re.sub(r"_+", "", text)  # italic
    text = re.sub(r"`+", "", text)  # code
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links

    # Remove multiple spaces/newlines
    text = re.sub(r"\s+", " ", text)

    return text.strip()
