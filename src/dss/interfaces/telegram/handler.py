"""Telegram speech and payload helpers shared by constructed dispatch."""

import re

from src.dss.application.conversation import language
from src.dss.application.conversation.contracts import TelegramUpdate

# Minimum confidence threshold for STT
STT_CONFIDENCE_THRESHOLD = 0.5
TTS_MAX_TEXT_LENGTH = 900


# Deliberately narrower than the marker set used for typed messages. A
# transcript is the speech recogniser's guess, so a single common word is weak
# evidence; requiring two of these unambiguous ones keeps STT scoring from
# swinging to Hinglish on a mis-recognition.
_TRANSCRIPT_HINGLISH_MARKERS = (
    "mujhe",
    "chahiye",
    "batao",
    "batayiye",
    "madad",
    "sahayata",
)
_TRANSCRIPT_MARKER_THRESHOLD = 2


def _infer_transcript_language(text: str) -> str:
    """Infer transcript language using a light heuristic."""
    if language.devanagari_ratio(text) > language.DEVANAGARI_THRESHOLD:
        return "hi"

    marker_hits = language.count_markers(text.lower(), _TRANSCRIPT_HINGLISH_MARKERS)
    if marker_hits >= _TRANSCRIPT_MARKER_THRESHOLD:
        return "hinglish"
    return "en"


def _stt_language_candidates(session) -> list[str]:
    """Return STT probe order based on session language state."""
    if session.language_locked and session.language_preference == "en":
        return ["en", "hi"]
    if session.language_locked and session.language_preference == "hi":
        return ["hi", "en"]
    if session.language_locked and session.language_preference == "hinglish":
        return ["hi", "en"]

    # Unlocked language is only a soft observation from previous turns, so it
    # must not bias voice recognition on the next message.
    return ["en", "hi"]


def _guess_audio_format(update: TelegramUpdate) -> str:
    """Infer audio format from the Telegram update payload."""
    media = {}
    if update.message:
        media = update.message.get("voice") or update.message.get("audio") or {}
    mime_type = media.get("mime_type", "")
    if "mpeg" in mime_type or mime_type.endswith("/mp3"):
        return "mp3"
    if "mp4" in mime_type or "m4a" in mime_type:
        return "m4a"
    if "webm" in mime_type:
        return "webm"
    return "ogg"


def _tts_filename(content_type: str | None) -> str:
    """Choose a filename that matches the synthesized audio type."""
    extension_map = {
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
    }
    extension = extension_map.get(content_type or "", "bin")
    return f"response.{extension}"


def _transcript_echo_text(language: str, transcript: str) -> str:
    """Render the STT transcript back to the user for testing/debugging."""
    if language == "hi":
        return f"आपने कहा: {transcript}"
    if language == "hinglish":
        return f"Aapne kaha: {transcript}"
    return f"You said: {transcript}"


def _echo_language(session, transcript_language: str) -> str:
    """Choose the visible echo prefix language.

    The visible prefix should honor an explicit user language lock even when
    the best STT transcript candidate happened to be English.
    """
    locked_language = getattr(session, "language_preference", "auto")
    if getattr(session, "language_locked", False) and locked_language in {"hi", "en", "hinglish"}:
        return locked_language
    if transcript_language in {"hi", "en", "hinglish"}:
        return transcript_language
    return "en"


async def _transcribe_with_fallbacks(
    voice_client,
    audio_bytes: bytes,
    audio_format: str,
    language_candidates: list[str],
):
    """Run STT against one or more language candidates and pick the best result."""

    def _transcript_quality_score(text: str) -> float:
        """Prefer fuller transcripts over short/noisy recognitions."""
        stripped = text.strip()
        if not stripped:
            return -1.0
        if stripped.startswith("[") and stripped.endswith("]"):
            return -0.5

        tokens = re.findall(r"[A-Za-z0-9\u0900-\u097F]+", stripped)
        meaningful_tokens = [token for token in tokens if len(token) > 1]
        alpha_chars = sum(1 for char in stripped if char.isalpha())

        score = min(len(meaningful_tokens), 6) * 0.05
        if alpha_chars:
            score += min(alpha_chars / max(len(stripped), 1), 1.0) * 0.1
        return score

    best_result = None
    best_score = -1.0

    for candidate in language_candidates:
        result = await voice_client.speech_to_text(
            audio_bytes=audio_bytes,
            source_lang=candidate,
            audio_format=audio_format,
        )
        if not result.text:
            continue

        score = float(result.confidence or 0.0) + _transcript_quality_score(result.text)
        transcript_language = _infer_transcript_language(result.text)
        # Reward a transcript that reads like the language it was decoded as,
        # and penalise one the recogniser itself labels as a different one.
        if (candidate == "en" and transcript_language == "en") or (
            candidate == "hi" and transcript_language in {"hi", "hinglish"}
        ):
            score += 0.2

        detected_language = getattr(result, "language", None)
        if detected_language in {"en", "hi", "hinglish"}:
            score += 0.15 if detected_language == candidate else -0.2

        if score > best_score:
            best_result = result
            best_score = score

    return best_result


def extract_location(update: TelegramUpdate) -> tuple[float, float] | None:
    """Extract location from Telegram update if shared."""
    if update.message and update.message.get("location"):
        loc = update.message["location"]
        return (loc.get("latitude"), loc.get("longitude"))
    return None
