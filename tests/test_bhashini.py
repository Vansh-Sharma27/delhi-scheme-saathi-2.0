"""Tests for Bhashini speech services client."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dss.application.ports.speech import STTResult, TTSResult
from src.dss.infrastructure.speech.bhashini import BhashiniClient
from src.dss.settings import Settings


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, bhashini_api_key="", bhashini_user_id="", bhashini_ulca_api_key="",
    )


class TestBhashiniClient:
    """Tests for BhashiniClient."""

    def test_client_initialization_without_key(self, settings):
        """Test client initializes without API key."""
        client = BhashiniClient(settings=settings)
        assert client.api_key == ""
        assert client.user_id == ""

    def test_client_initialization_with_key(self, settings):
        """Test client initializes with provided API key."""
        client = BhashiniClient(
            settings=settings,
            api_key="test-api-key",
            user_id="test-user-id",
        )
        assert client.api_key == "test-api-key"
        assert client.user_id == "test-user-id"


class TestSpeechToText:
    """Tests for speech-to-text functionality."""

    @pytest.mark.asyncio
    async def test_stt_without_api_key_returns_placeholder(self, settings):
        """Test STT returns placeholder when no API key configured."""
        client = BhashiniClient(settings=settings)
        result = await client.speech_to_text(
            audio_bytes=b"test audio data",
            source_lang="hi",
        )
        assert isinstance(result, STTResult)
        assert result.confidence == 0.0
        assert "please type" in result.text.lower()

    @pytest.mark.asyncio
    async def test_stt_with_api_key_success(self, settings):
        """Test STT with valid API key returns transcription."""
        client = BhashiniClient(api_key="test-api-key", settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelineResponse": [
                {
                    "output": [
                        {
                            "source": "नमस्ते, मुझे पेंशन चाहिए",
                            "confidence": 0.92,
                        }
                    ]
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.speech_to_text(
                audio_bytes=b"test audio data",
                source_lang="hi",
            )

            assert isinstance(result, STTResult)
            assert result.text == "नमस्ते, मुझे पेंशन चाहिए"
            assert result.confidence == 0.92
            assert result.language == "hi"

    @pytest.mark.asyncio
    async def test_stt_handles_http_error(self, settings):
        """Test STT handles HTTP errors gracefully."""
        import httpx

        client = BhashiniClient(api_key="test-api-key", settings=settings)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            mock_get_client.return_value = mock_http_client

            result = await client.speech_to_text(
                audio_bytes=b"test audio data",
                source_lang="hi",
            )

            assert isinstance(result, STTResult)
            assert result.confidence == 0.0
            assert "failed" in result.text.lower()

    @pytest.mark.asyncio
    async def test_stt_handles_empty_response(self, settings):
        """Test STT handles empty pipeline response."""
        client = BhashiniClient(api_key="test-api-key", settings=settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"pipelineResponse": [{"output": []}]}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.speech_to_text(
                audio_bytes=b"test audio data",
                source_lang="hi",
            )

            assert result.text == ""
            assert result.confidence == 0.0


class TestTextToSpeech:
    """Tests for text-to-speech functionality."""

    @pytest.mark.asyncio
    async def test_tts_without_api_key_returns_empty(self, settings):
        """Test TTS returns empty bytes when no API key configured."""
        client = BhashiniClient(settings=settings)
        result = await client.text_to_speech(
            text="नमस्ते",
            target_lang="hi",
        )
        assert isinstance(result, TTSResult)
        assert result.audio_bytes == b""

    @pytest.mark.asyncio
    async def test_tts_with_api_key_success(self, settings):
        """Test TTS with valid API key returns audio bytes."""
        client = BhashiniClient(api_key="test-api-key", settings=settings)

        # Create mock audio content
        audio_content = b"mock audio bytes"
        audio_base64 = base64.b64encode(audio_content).decode("utf-8")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelineResponse": [
                {
                    "audio": [
                        {
                            "audioContent": audio_base64,
                        }
                    ]
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.text_to_speech(
                text="नमस्ते",
                target_lang="hi",
            )

            assert isinstance(result, TTSResult)
            assert result.audio_bytes == audio_content
            assert result.content_type == "audio/wav"

    @pytest.mark.asyncio
    async def test_tts_handles_http_error(self, settings):
        """Test TTS handles HTTP errors gracefully."""
        import httpx

        client = BhashiniClient(api_key="test-api-key", settings=settings)

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            mock_get_client.return_value = mock_http_client

            result = await client.text_to_speech(
                text="नमस्ते",
                target_lang="hi",
            )

            assert result.audio_bytes == b""


class TestLanguageDetection:
    """Tests for language detection."""

    @pytest.mark.asyncio
    async def test_detect_hindi(self, settings):
        """Test detection of Hindi text."""
        client = BhashiniClient(settings=settings)
        lang = await client.detect_language("नमस्ते, मुझे पेंशन चाहिए")
        assert lang == "hi"

    @pytest.mark.asyncio
    async def test_detect_english(self, settings):
        """Test detection of English text."""
        client = BhashiniClient(settings=settings)
        lang = await client.detect_language("Hello, I need pension information")
        assert lang == "en"

    @pytest.mark.asyncio
    async def test_detect_hinglish_defaults_to_hindi(self, settings):
        """Test Hinglish text defaults to Hindi."""
        client = BhashiniClient(settings=settings)
        # Hinglish with <30% Devanagari should detect as English
        lang = await client.detect_language("Mujhe pension chahiye please")
        assert lang == "en"

    @pytest.mark.asyncio
    async def test_detect_empty_defaults_to_hindi(self, settings):
        """Test empty text defaults to Hindi."""
        client = BhashiniClient(settings=settings)
        lang = await client.detect_language("123 456")
        assert lang == "hi"


class TestInstanceIsolation:
    @pytest.mark.asyncio
    async def test_credentials_and_http_lifetimes_are_independent(self, settings):
        first = BhashiniClient(api_key="first-key", user_id="first-user", settings=settings)
        second = BhashiniClient(api_key="second-key", user_id="second-user", settings=settings)
        try:
            first_http = await first._get_client()
            second_http = await second._get_client()
            assert first_http is not second_http
            assert first_http.headers["Authorization"] == "first-key"
            assert second_http.headers["Authorization"] == "second-key"
            assert first.user_id == "first-user"
            assert second.user_id == "second-user"
            await first.close()
            assert first_http.is_closed
            assert not second_http.is_closed
            assert await second._get_client() is second_http
        finally:
            await first.close()
            await second.close()
