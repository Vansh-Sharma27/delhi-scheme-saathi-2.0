"""Port: speech provider (STT and TTS).

Defines the speech surface the webhook handler consumes so that when Phase
5 moves the handler into `src.dss.interfaces.telegram` it can depend on the
port instead of the Sarvam or Bhashini adapter directly. The legacy
`src.integrations.sarvam.SarvamClient` and
`src.integrations.bhashini.BhashiniClient` both satisfy this protocol
structurally.

`STTResult` and `TTSResult` are the canonical result types. They were
duplicated byte-for-byte in `sarvam.py` and `bhashini.py`; this port is now
their single home, and both legacy modules re-export them so the existing
test imports and isinstance checks keep working with one class identity.

`speech_to_text` carries the common three-parameter surface the handler
calls (`audio_bytes`, `source_lang`, `audio_format`). Sarvam's `mode`
parameter is adapter-specific and stays on `SarvamClient`, not the port,
because Bhashini does not accept it and the handler never passes it.
`text_to_speech` is identical across both adapters. `close` and
`detect_language` are lifecycle or adapter concerns the handler does not
call, so they stay off the port.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class STTResult:
    """Speech-to-text result."""

    text: str
    confidence: float
    language: str = "hi"


@dataclass
class TTSResult:
    """Text-to-speech result."""

    audio_bytes: bytes
    content_type: str = "audio/wav"
    duration_seconds: float = 0.0


@runtime_checkable
class SpeechProvider(Protocol):
    """Provider contract for speech transcription and synthesis."""

    async def speech_to_text(
        self,
        audio_bytes: bytes,
        source_lang: str = "hi",
        audio_format: str = "ogg",
    ) -> STTResult: ...

    async def text_to_speech(
        self,
        text: str,
        target_lang: str = "hi",
        voice: str = "female",
    ) -> TTSResult: ...
