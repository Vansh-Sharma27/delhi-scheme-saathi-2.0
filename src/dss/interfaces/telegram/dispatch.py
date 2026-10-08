"""Constructed Telegram delivery over speech, notifier and application ports."""

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, cast

from src.dss.application.conversation.contracts import ChatRequest, ChatResponse, TelegramUpdate
from src.dss.application.conversation.sessions import get_or_create_session
from src.dss.application.ports.clock import Clock
from src.dss.application.ports.notifier import Notifier
from src.dss.application.ports.session_repository import SessionStore
from src.dss.application.ports.speech import SpeechProvider, STTResult
from src.dss.domain.conversations.session import Session
from src.dss.interfaces.telegram.formatting import (
    _clean_for_telegram,
    _clean_for_tts,
    _split_message,
)
from src.dss.interfaces.telegram.handler import (
    STT_CONFIDENCE_THRESHOLD,
    TTS_MAX_TEXT_LENGTH,
    _echo_language,
    _guess_audio_format,
    _infer_transcript_language,
    _stt_language_candidates,
    _transcribe_with_fallbacks,
    _transcript_echo_text,
    _tts_filename,
)

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(
        self, notifier: Notifier, speech: SpeechProvider, store: SessionStore, clock: Clock,
        conversation: Callable[[ChatRequest], Awaitable[ChatResponse]],
    ) -> None:
        self.notifier = notifier
        self.speech = speech
        self.store = store
        self.clock = clock
        self.conversation = conversation

    async def handle(self, update_data: dict[str, Any]) -> dict[str, str]:
        telegram = self.notifier
        update = TelegramUpdate(**update_data)
        chat_id = update.chat_id
        user_id = update.user_id
        if not chat_id or not user_id:
            logger.warning("Invalid update, missing chat_id or user_id")
            return {"status": "ignored", "reason": "missing_ids"}
        await telegram.send_chat_action(chat_id, "typing")
        session = await get_or_create_session(user_id, store=self.store, clock=self.clock)
        is_voice_input = update.is_voice or update.is_audio
        text: str | None
        if is_voice_input:
            caption_text = update.text
            transcript_text = await self.voice(update, chat_id, session)
            text = "\n".join(part for part in (caption_text, transcript_text) if part)
            if not text:
                return {"status": "ok", "message": "voice_processed"}
        else:
            text = update.text
        if not text:
            logger.warning("No text in update for chat_id=%s", chat_id)
            return {"status": "ignored", "reason": "no_text"}
        request = ChatRequest(
            user_id=user_id, message=text,
            message_type="voice" if is_voice_input else ("callback" if update.is_callback else "text"),
            callback_data=cast(dict[str, Any], update.callback_query).get("data") if update.is_callback else None,
        )
        if update.is_callback:
            callback_id = cast(dict[str, Any], update.callback_query).get("id")
            if callback_id:
                await telegram.answer_callback_query(callback_id)
        try:
            response = await self.conversation(request)
        except Exception as exc:
            logger.error("Conversation error for chat_id=%s: %s", chat_id, exc, exc_info=True)
            await telegram.send_text(chat_id,
                "माफ़ कीजिए, कुछ तकनीकी समस्या है। कृपया थोड़ी देर बाद प्रयास करें।\n\n"
                "Sorry, there was a technical issue. Please try again later.")
            return {"status": "error", "message": "internal_error"}
        try:
            await self.send_response(chat_id, response, is_voice_input)
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc, exc_info=True)
            with suppress(Exception):
                await telegram.send_text(chat_id, _clean_for_telegram(response.text)[:4000])
        return {"status": "ok"}

    async def voice(self, update: TelegramUpdate, chat_id: int | str, session: Session) -> str | None:
        telegram = self.notifier
        voice_client = self.speech
        if not voice_client.is_available():
            await telegram.send_text(chat_id,
                "🎤 Voice messages will be supported soon! Please type your message for now.\n\n"
                "🎤 जल्द ही आवाज़ संदेश समर्थित होंगे! अभी कृपया टाइप करें।")
            return None
        try:
            file_id = update.media_file_id
            if not file_id:
                logger.warning("No file_id in voice message")
                await telegram.send_text(chat_id, "Voice message could not be processed.")
                return None
            logger.info("Downloading voice file: %s", file_id)
            audio_bytes = await telegram.download_voice(file_id)
            if not audio_bytes:
                logger.warning("Failed to download voice file")
                await telegram.send_text(chat_id, "कृपया दोबारा बोलें। आवाज़ स्पष्ट नहीं थी।\nPlease speak again. The audio wasn't clear.")
                return None
            audio_format = _guess_audio_format(update)
            language_candidates = _stt_language_candidates(session)
            logger.info("Processing voice through STT (%s bytes, candidates=%s)", len(audio_bytes), language_candidates)
            result = cast(STTResult | None, await _transcribe_with_fallbacks(voice_client, audio_bytes, audio_format, language_candidates))
            if not result or not result.text or (result.confidence or 0.0) < STT_CONFIDENCE_THRESHOLD:
                logger.warning("Low STT confidence after probing: %s", result.confidence if result else None)
                await telegram.send_text(chat_id,
                    "🔊 आवाज़ स्पष्ट नहीं थी। कृपया दोबारा बोलें या टाइप करें।\n"
                    "🔊 Audio wasn't clear. Please speak again or type your message.")
                return None
            logger.info("STT result: '%s' (confidence: %s)", result.text, result.confidence)
            transcript_language = result.language
            if transcript_language not in {"en", "hi", "hinglish"}:
                transcript_language = _infer_transcript_language(result.text)
            echo_language = _echo_language(session, transcript_language)
            await telegram.send_text(chat_id, _transcript_echo_text(echo_language, result.text))
            return result.text
        except Exception as exc:
            logger.error("Voice processing error: %s", exc, exc_info=True)
            await telegram.send_text(chat_id,
                "माफ़ कीजिए, आवाज़ प्रोसेस नहीं हो सकी। कृपया टाइप करें।\n"
                "Sorry, couldn't process voice. Please type your message.")
            return None

    async def send_response(self, chat_id: int | str, response: ChatResponse, is_voice: bool = False) -> None:
        telegram, voice_client = self.notifier, self.speech
        clean_text = _clean_for_telegram(response.text)
        parts = _split_message(clean_text)
        for part in parts[:-1]:
            await telegram.send_text(chat_id, part)
        last_part = parts[-1] if parts else clean_text
        if response.inline_keyboard:
            await telegram.send_inline_keyboard(chat_id=chat_id, text=last_part, buttons=response.inline_keyboard)
        else:
            await telegram.send_text(chat_id, last_part)
        if is_voice and voice_client.is_available():
            try:
                clean_tts_text = _clean_for_tts(clean_text)
                if response.language == "hinglish":
                    logger.info("Skipping TTS for Hinglish response")
                    return
                if len(parts) > 1 or len(clean_tts_text) > TTS_MAX_TEXT_LENGTH:
                    logger.info("Skipping TTS for long structured response")
                    return
                tts_result = await voice_client.text_to_speech(text=clean_tts_text, target_lang=response.language)
                if tts_result.audio_bytes:
                    filename = _tts_filename(tts_result.content_type)
                    if tts_result.content_type == "audio/ogg":
                        await telegram.send_voice(chat_id, tts_result.audio_bytes, filename=filename, content_type=tts_result.content_type)
                    else:
                        await telegram.send_audio(chat_id, tts_result.audio_bytes, filename=filename, content_type=tts_result.content_type)
            except Exception as exc:
                logger.warning("TTS failed, skipping voice response: %s", exc)
