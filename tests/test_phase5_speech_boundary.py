"""Speech consumers require capabilities, not provider credentials."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.dss.application.conversation.contracts import ChatResponse, TelegramUpdate
from src.dss.application.ports.speech import SpeechProvider
from src.dss.infrastructure.speech.bhashini import BhashiniClient
from src.dss.infrastructure.speech.sarvam import SarvamClient
from src.webhook import handler
from tests.test_dss_ports import FakeSpeechProvider


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
def test_legacy_wiring_preserves_selection_order(monkeypatch, sarvam, bhashini, selected) -> None:
    sarvam_client = CredentialFreeSpeech(sarvam)
    bhashini_client = CredentialFreeSpeech(bhashini)
    factories = {
        "sarvam": Mock(return_value=sarvam_client),
        "bhashini": Mock(return_value=bhashini_client),
    }
    monkeypatch.setattr(
        handler,
        "get_settings",
        lambda: SimpleNamespace(
            sarvam_api_key="synthetic" if sarvam else "",
            bhashini_api_key="synthetic" if bhashini else "",
        ),
    )
    monkeypatch.setattr(handler, "get_sarvam_client", factories["sarvam"])
    monkeypatch.setattr(handler, "get_bhashini_client", factories["bhashini"])
    client = handler._get_voice_client()
    assert client is (sarvam_client if selected == "sarvam" else bhashini_client)
    assert isinstance(client, SpeechProvider)
    factories[selected].assert_called_once_with()
    factories["bhashini" if selected == "sarvam" else "sarvam"].assert_not_called()


@pytest.mark.parametrize("enabled", [False, True])
async def test_stt_and_tts_use_only_the_capability(monkeypatch, enabled) -> None:
    provider = CredentialFreeSpeech(enabled)
    notifier = AsyncMock()
    notifier.download_voice.return_value = b"synthetic-audio"
    monkeypatch.setattr(handler, "_get_voice_client", lambda: provider)
    monkeypatch.setattr(handler, "get_telegram_client", lambda: notifier)
    update = TelegramUpdate(update_id=1, message={"voice": {"file_id": "synthetic-file"}})
    transcript = await handler._handle_voice_message(update, "synthetic-chat")
    response = ChatResponse(text="Synthetic response", language="en")
    await handler._send_response(notifier, "synthetic-chat", response, True)
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
