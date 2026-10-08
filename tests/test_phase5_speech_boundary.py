"""Speech consumers require capabilities, not provider credentials."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.dss.application.conversation.contracts import ChatResponse, TelegramUpdate
from src.dss.application.ports.speech import SpeechProvider
from src.dss.bootstrap import runtime
from src.dss.domain.conversations.session import Session
from src.dss.infrastructure.sessions.session_store import InMemorySessionStore
from src.dss.infrastructure.speech.bhashini import BhashiniClient
from src.dss.infrastructure.speech.sarvam import SarvamClient
from src.dss.interfaces.telegram.dispatch import TelegramHandler
from src.dss.settings import Settings
from tests.test_dss_ports import FakeSpeechProvider
from tests.test_phase6_sessions import FixedClock


class CredentialFreeSpeech(FakeSpeechProvider):
    def __init__(self, enabled: bool = True) -> None:
        super().__init__()
        self.enabled = enabled

    def is_available(self) -> bool:
        return self.enabled

    @property
    def api_key(self):
        raise AssertionError("The interface must not inspect credentials")


@pytest.mark.parametrize("adapter", [SarvamClient, BhashiniClient])
@pytest.mark.parametrize("configured", [False, True])
def test_adapter_reports_existing_configuration_without_exposing_it(adapter, configured) -> None:
    client = object.__new__(adapter)
    client.api_key = "synthetic" if configured else ""
    assert client.is_available() is configured


@pytest.mark.parametrize(
    "sarvam,bhashini,selected",
    [
        (True, True, "sarvam"),
        (True, False, "sarvam"),
        (False, True, "bhashini"),
        (False, False, "sarvam"),
    ],
)
async def test_bootstrap_preserves_selection_order(monkeypatch, sarvam, bhashini, selected) -> None:
    sarvam_client = CredentialFreeSpeech(sarvam)
    bhashini_client = CredentialFreeSpeech(bhashini)
    sarvam_client.close = AsyncMock()
    bhashini_client.close = AsyncMock()
    factories = {
        "sarvam": Mock(return_value=sarvam_client),
        "bhashini": Mock(return_value=bhashini_client),
    }
    settings = Settings(
        _env_file=None,
        sarvam_api_key="synthetic" if sarvam else "",
        bhashini_api_key="synthetic" if bhashini else "",
    )
    monkeypatch.setattr(runtime, "open_pool", AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(runtime, "build_session_store", lambda *args, **kwargs: Mock())
    monkeypatch.setattr(runtime, "build_work_queue", lambda settings: None)
    monkeypatch.setattr(runtime, "FallbackLLMClient", Mock(return_value=AsyncMock()))
    monkeypatch.setattr(runtime, "FallbackEmbeddingClient", Mock(return_value=AsyncMock()))
    monkeypatch.setattr(runtime, "TelegramClient", Mock(return_value=AsyncMock()))
    monkeypatch.setattr(runtime, "SarvamClient", factories["sarvam"])
    monkeypatch.setattr(runtime, "BhashiniClient", factories["bhashini"])
    async with runtime.api_runtime(settings) as graph:
        client = graph.dependencies.telegram.__self__.speech
        assert client is (sarvam_client if selected == "sarvam" else bhashini_client)
        assert isinstance(client, SpeechProvider)
    factories[selected].assert_called_once_with(settings=settings)
    factories["bhashini" if selected == "sarvam" else "sarvam"].assert_not_called()
    client.close.assert_awaited_once()


@pytest.mark.parametrize("enabled", [False, True])
async def test_stt_and_tts_use_only_the_capability(enabled) -> None:
    provider = CredentialFreeSpeech(enabled)
    notifier = AsyncMock()
    notifier.download_voice.return_value = b"synthetic-audio"
    clock = FixedClock()
    handler = TelegramHandler(notifier, provider, InMemorySessionStore(clock), clock, AsyncMock())
    update = TelegramUpdate(update_id=1, message={"voice": {"file_id": "synthetic-file"}})
    transcript = await handler.voice(update, "synthetic-chat", Session(user_id="synthetic-user"))
    response = ChatResponse(text="Synthetic response", language="en")
    await handler.send_response("synthetic-chat", response, True)
    if enabled:
        assert transcript == "मुझे आवास चाहिए"
        assert provider.stt_calls == 2
        assert provider.tts_calls == 1
        notifier.send_voice.assert_awaited_once()
    else:
        assert transcript is None
        assert provider.stt_calls == provider.tts_calls == 0
        notifier.download_voice.assert_not_awaited()
        notifier.send_voice.assert_not_awaited()
