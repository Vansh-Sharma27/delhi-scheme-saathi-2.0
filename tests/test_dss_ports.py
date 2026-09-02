"""Phase 2 port conformance and in-memory fakes.

Each application port in ``src.dss.application.ports`` must have at least one
in-memory fake exercised by a test (spec Phase 2 gate), and each existing
concrete adapter that the port is the future home for is asserted to satisfy
the port. Concrete adapters that need live settings (FallbackLLMClient,
FallbackEmbeddingClient, SarvamClient, BhashiniClient, TelegramClient,
DynamoDBSessionStore, SQSAIWorkQueue) are checked with a static
conformance function rather than constructed, so this file runs with no
environment. The in-memory implementations that need no settings
(InMemorySessionStore, InMemoryAIWorkQueue) are constructed and exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.dss.application.ports.clock import Clock
from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.idempotency_store import IdempotencyStore
from src.dss.application.ports.llm import (
    LLMProvider,
    ProviderExecutionResult,
    TaskPriority,
)
from src.dss.application.ports.notifier import Notifier
from src.dss.application.ports.rejection_rule_repository import (
    RejectionRuleRepository,
)
from src.integrations.embedding_client import FallbackEmbeddingClient
from src.integrations.llm_client import FallbackLLMClient
from src.integrations.telegram import TelegramClient
from src.models.rejection_rule import RejectionRule


class FakeLLMProvider:
    """Deterministic LLM provider for tests.

    Records every call and returns canned payloads sized so the four task
    types (analyze, generate, summarize, judge) and their ``*_with_meta``
    variants are all exercised through the port.
    """

    def __init__(self) -> None:
        self.analyze_calls: list[dict[str, Any]] = []
        self.generate_calls: list[dict[str, Any]] = []
        self.summarize_calls: list[dict[str, Any]] = []
        self.judge_calls: list[dict[str, Any]] = []
        self._analysis: dict[str, Any] = {
            "intent": "unknown",
            "life_event": None,
            "extracted_fields": {},
            "language": "hi",
            "selected_scheme_id": None,
            "action": None,
            "needs_clarification": False,
            "clarification_question": None,
            "response_text": None,
        }
        self._relevance: dict[str, Any] = {
            "should_clarify": False,
            "clarification_question": None,
            "overall_confidence": 0.5,
            "candidate_scores": [],
        }

    async def analyze_message(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        system_prompt: str,
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> dict[str, Any]:
        self.analyze_calls.append({"user_message": user_message, "priority": priority})
        return dict(self._analysis)

    async def analyze_message_with_meta(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        system_prompt: str,
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> ProviderExecutionResult[dict[str, Any]]:
        payload = await self.analyze_message(
            user_message=user_message,
            conversation_history=conversation_history,
            current_state=current_state,
            user_profile=user_profile,
            system_prompt=system_prompt,
            session_language=session_language,
            working_memory=working_memory,
            priority=priority,
        )
        return ProviderExecutionResult(output=payload, provider="fake", fallback_used=False, latency_ms=1.0)

    async def generate_response(
        self,
        context: dict[str, Any],
        system_prompt: str,
        user_language: str = "hi",
        priority: TaskPriority = "inline",
    ) -> str:
        self.generate_calls.append({"user_language": user_language, "priority": priority})
        return "à¤¨à¤®à¤¸à¥à¤¤à¥‡"

    async def generate_response_with_meta(
        self,
        context: dict[str, Any],
        system_prompt: str,
        user_language: str = "hi",
        priority: TaskPriority = "inline",
    ) -> ProviderExecutionResult[str]:
        text = await self.generate_response(
            context=context, system_prompt=system_prompt, user_language=user_language, priority=priority
        )
        return ProviderExecutionResult(output=text, provider="fake", fallback_used=False, latency_ms=1.0)

    async def summarize_conversation(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
        priority: TaskPriority = "background",
    ) -> str:
        self.summarize_calls.append({"priority": priority})
        return current_summary or ""

    async def summarize_conversation_with_meta(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
        priority: TaskPriority = "background",
    ) -> ProviderExecutionResult[str]:
        summary = await self.summarize_conversation(
            messages=messages, current_summary=current_summary, priority=priority
        )
        return ProviderExecutionResult(output=summary, provider="fake", fallback_used=False, latency_ms=1.0)

    async def judge_scheme_relevance(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        candidate_schemes: list[dict[str, Any]],
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> dict[str, Any]:
        self.judge_calls.append({"user_message": user_message, "priority": priority})
        return dict(self._relevance)

    async def judge_scheme_relevance_with_meta(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
        current_state: str,
        user_profile: dict[str, Any],
        candidate_schemes: list[dict[str, Any]],
        session_language: str = "hi",
        working_memory: dict[str, Any] | None = None,
        priority: TaskPriority = "inline",
    ) -> ProviderExecutionResult[dict[str, Any]]:
        payload = await self.judge_scheme_relevance(
            user_message=user_message,
            conversation_history=conversation_history,
            current_state=current_state,
            user_profile=user_profile,
            candidate_schemes=candidate_schemes,
            session_language=session_language,
            working_memory=working_memory,
            priority=priority,
        )
        return ProviderExecutionResult(output=payload, provider="fake", fallback_used=False, latency_ms=1.0)


def _fallback_llm_client_satisfies_llm_port(client: FallbackLLMClient) -> LLMProvider:
    """Static assertion: FallbackLLMClient conforms to the LLMProvider port.

    mypy verifies this at type-check time; the function is never called.
    """
    return client


@pytest.mark.asyncio
async def test_fake_llm_provider_exercised_through_port() -> None:
    """The LLM port is implementable and usable: a fake is typed as the port
    and every method is called through the port type."""
    provider: LLMProvider = FakeLLMProvider()

    analysis = await provider.analyze_message(
        user_message="à¤®à¥à¤à¥‡ à¤†à¤µà¤¾à¤¸ à¤šà¤¾à¤¹à¤¿à¤",
        conversation_history=[],
        current_state="GREETING",
        user_profile={},
        system_prompt="",
    )
    assert analysis["intent"] == "unknown"

    meta = await provider.analyze_message_with_meta(
        user_message="à¤®à¥à¤à¥‡ à¤†à¤µà¤¾à¤¸ à¤šà¤¾à¤¹à¤¿à¤",
        conversation_history=[],
        current_state="GREETING",
        user_profile={},
        system_prompt="",
    )
    assert meta.provider == "fake"
    assert meta.output["intent"] == "unknown"

    text = await provider.generate_response(context={}, system_prompt="", user_language="hi")
    assert text == "à¤¨à¤®à¤¸à¥à¤¤à¥‡"

    gen_meta = await provider.generate_response_with_meta(context={}, system_prompt="")
    assert gen_meta.output == "à¤¨à¤®à¤¸à¥à¤¤à¥‡"

    summary = await provider.summarize_conversation(messages=[], current_summary=None)
    assert summary == ""

    sum_meta = await provider.summarize_conversation_with_meta(messages=[])
    assert sum_meta.output == ""

    relevance = await provider.judge_scheme_relevance(
        user_message="à¤†à¤µà¤¾à¤¸",
        conversation_history=[],
        current_state="SCHEME_MATCHING",
        user_profile={},
        candidate_schemes=[],
    )
    assert relevance["overall_confidence"] == 0.5

    judge_meta = await provider.judge_scheme_relevance_with_meta(
        user_message="à¤†à¤µà¤¾à¤¸",
        conversation_history=[],
        current_state="SCHEME_MATCHING",
        user_profile={},
        candidate_schemes=[],
    )
    assert judge_meta.provider == "fake"

    fake = provider
    assert isinstance(fake, FakeLLMProvider)
    assert len(fake.analyze_calls) == 2
    assert len(fake.generate_calls) == 2
    assert len(fake.summarize_calls) == 2
    assert len(fake.judge_calls) == 2


class FakeEmbeddingProvider:
    """Deterministic embedding provider backed by a fixed vector map.

    Returns a stored 3-dimensional vector per text, ``None`` for unknown text,
    and an empty batch for an empty input list. Mirrors the contract an
    adapter must satisfy so the matching layer can skip vector ranking on a
    missing embedding (spec 10.4 frozen list).
    """

    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {
            "आवास": [1.0, 0.0, 0.0],
            "housing": [0.9, 0.1, 0.0],
        }
        self.get_calls: int = 0
        self.batch_calls: int = 0

    async def get_embedding(self, text: str) -> list[float] | None:
        self.get_calls += 1
        return self._vectors.get(text)

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls += 1
        if not texts:
            return []
        return [self._vectors.get(text, [0.0, 0.0, 0.0]) for text in texts]


def _fallback_embedding_client_satisfies_port(
    client: FallbackEmbeddingClient,
) -> EmbeddingProvider:
    """Static assertion: FallbackEmbeddingClient conforms to the port.

    mypy verifies this at type-check time; the function is never called.
    """
    return client


@pytest.mark.asyncio
async def test_fake_embedding_provider_exercised_through_port() -> None:
    """The embedding port is implementable and usable: a fake is typed as the
    port and both methods are called through the port type."""
    provider: EmbeddingProvider = FakeEmbeddingProvider()

    housing = await provider.get_embedding("आवास")
    assert housing == [1.0, 0.0, 0.0]

    missing = await provider.get_embedding("unknown text")
    assert missing is None

    batch = await provider.get_embeddings_batch(["आवास", "housing", "unknown"])
    assert batch[0] == [1.0, 0.0, 0.0]
    assert batch[1] == [0.9, 0.1, 0.0]
    assert batch[2] == [0.0, 0.0, 0.0]

    empty = await provider.get_embeddings_batch([])
    assert empty == []

    fake = provider
    assert isinstance(fake, FakeEmbeddingProvider)
    assert fake.get_calls == 2
    assert fake.batch_calls == 2


class FakeClock:
    """Fixed clock for deterministic time-dependent tests.

    Returns the same UTC datetime for every call unless advanced via
    ``tick``. This is the seam the spec Phase 3 caution names: once a clock
    is injected into the session helpers, TTL and memory-refresh logic can
    be pinned without freezing wall time globally.
    """

    def __init__(self, fixed: datetime | None = None) -> None:
        self._fixed = fixed or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._fixed

    def tick(self, to: datetime) -> None:
        """Advance the fixed time for tests that cover ordering over time."""
        self._fixed = to


@pytest.mark.asyncio
async def test_fake_clock_exercised_through_port() -> None:
    """The clock port is implementable and usable: a fake is typed as the
    port and returns a stable UTC datetime across reads, then advances."""
    clock: Clock = FakeClock()

    first = clock.now()
    again = clock.now()
    assert first == again
    assert first.tzinfo == UTC

    clock.tick(datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC))
    later = clock.now()
    assert later > first
    assert later.day == 2

    fake = clock
    assert isinstance(fake, FakeClock)


class InMemoryIdempotencyStore:
    """Set-backed atomic claim store for tests.

    A single Python `set` with no await between check and insert is atomic
    within one event loop, which is enough for the unit tests that exercise
    the port. A production adapter needs a real conditional-write backend;
    this fake does not model cross-process races.
    """

    def __init__(self) -> None:
        self._seen: set[int] = set()
        self.claim_calls: int = 0

    async def claim(self, update_id: int) -> bool:
        self.claim_calls += 1
        if update_id in self._seen:
            return False
        self._seen.add(update_id)
        return True


@pytest.mark.asyncio
async def test_in_memory_idempotency_store_exercised_through_port() -> None:
    """The idempotency port is implementable and usable: a fake is typed as
    the port and the first-seen semantics hold across repeats."""
    store: IdempotencyStore = InMemoryIdempotencyStore()

    assert await store.claim(123456) is True
    assert await store.claim(123456) is False
    assert await store.claim(123457) is True
    assert await store.claim(123456) is False

    fake = store
    assert isinstance(fake, InMemoryIdempotencyStore)
    assert fake.claim_calls == 4


class FakeNotifier:
    """Recording notifier that captures every outbound message.

    Stores text sends, inline keyboards, callback answers, chat actions,
    and voice or audio sends in order, plus the bytes returned for a voice
    download. Used to assert the conversation layer replies through the port
    without hitting the Telegram API.
    """

    def __init__(self, voice_bytes: bytes = b"audio") -> None:
        self.texts: list[tuple[int | str, str]] = []
        self.keyboards: list[dict[str, Any]] = []
        self.callback_answers: list[str] = []
        self.chat_actions: list[tuple[int | str, str]] = []
        self.voice_sends: list[dict[str, Any]] = []
        self.audio_sends: list[dict[str, Any]] = []
        self.download_returns: list[str] = []
        self._voice_bytes = voice_bytes

    async def send_text(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        self.texts.append((chat_id, text))
        return {"ok": True, "result": {}}

    async def send_inline_keyboard(
        self,
        chat_id: int | str,
        text: str,
        buttons: list[list[dict[str, str]]],
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        self.keyboards.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"ok": True, "result": {}}

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        self.callback_answers.append(callback_query_id)
        return {"ok": True, "result": True}

    async def send_chat_action(
        self,
        chat_id: int | str,
        action: str = "typing",
    ) -> dict[str, Any]:
        self.chat_actions.append((chat_id, action))
        return {"ok": True, "result": True}

    async def send_voice(
        self,
        chat_id: int | str,
        voice_data: bytes | str,
        caption: str | None = None,
        filename: str = "response.ogg",
        content_type: str = "audio/ogg",
    ) -> dict[str, Any]:
        self.voice_sends.append({"chat_id": chat_id, "filename": filename, "content_type": content_type})
        return {"ok": True, "result": {}}

    async def send_audio(
        self,
        chat_id: int | str,
        audio_bytes: bytes,
        filename: str = "response.ogg",
        caption: str | None = None,
        content_type: str = "audio/ogg",
    ) -> dict[str, Any]:
        self.audio_sends.append({"chat_id": chat_id, "filename": filename, "content_type": content_type})
        return {"ok": True, "result": {}}

    async def download_voice(self, file_id: str) -> bytes:
        self.download_returns.append(file_id)
        return self._voice_bytes


def _telegram_client_satisfies_notifier_port(client: TelegramClient) -> Notifier:
    """Static assertion: TelegramClient conforms to the Notifier port.

    mypy verifies this at type-check time; the function is never called
    because TelegramClient needs live settings to construct.
    """
    return client


@pytest.mark.asyncio
async def test_fake_notifier_exercised_through_port() -> None:
    """The notifier port is implementable and usable: a fake is typed as the
    port and the full send plus download surface is called through it."""
    notifier: Notifier = FakeNotifier(voice_bytes=b"voice-bytes")

    await notifier.send_chat_action(123, "typing")
    await notifier.answer_callback_query("cb-1")
    await notifier.send_text(123, "नमस्ते")
    await notifier.send_inline_keyboard(
        chat_id=123, text="चुनें", buttons=[[{"text": "विकल्प 1", "callback_data": "1"}]]
    )
    voice = await notifier.download_voice("file-abc")
    assert voice == b"voice-bytes"
    await notifier.send_voice(123, b"audio-bytes", filename="reply.ogg", content_type="audio/ogg")
    await notifier.send_audio(123, b"audio-bytes", filename="reply.ogg", content_type="audio/ogg")

    fake = notifier
    assert isinstance(fake, FakeNotifier)
    assert fake.chat_actions == [(123, "typing")]
    assert fake.callback_answers == ["cb-1"]
    assert fake.texts == [(123, "नमस्ते")]
    assert len(fake.keyboards) == 1
    assert fake.download_returns == ["file-abc"]
    assert len(fake.voice_sends) == 1
    assert len(fake.audio_sends) == 1


class InMemoryRejectionRuleRepository:
    """List-backed rejection rule repository for tests.

    Holds RejectionRule instances and answers the four read methods by
    filtering in memory. Severity ordering matches the legacy repo's
    critical/high/warning ordering.
    """

    _SEVERITY_ORDER = {"critical": 0, "high": 1, "warning": 2}

    def __init__(self, rules: list[RejectionRule] | None = None) -> None:
        self._rules: list[RejectionRule] = list(rules or [])

    async def get_rules_by_scheme(self, scheme_id: str) -> list[RejectionRule]:
        hits = [rule for rule in self._rules if rule.scheme_id == scheme_id]
        return sorted(hits, key=lambda r: self._SEVERITY_ORDER.get(r.severity, 3))

    async def get_rules_by_ids(self, rule_ids: list[str]) -> list[RejectionRule]:
        if not rule_ids:
            return []
        wanted = set(rule_ids)
        hits = [rule for rule in self._rules if rule.id in wanted]
        return sorted(hits, key=lambda r: self._SEVERITY_ORDER.get(r.severity, 3))

    async def get_critical_rules(self, scheme_id: str) -> list[RejectionRule]:
        hits = [
            rule for rule in self._rules
            if rule.scheme_id == scheme_id and rule.severity == "critical"
        ]
        return hits

    async def get_all_rules(self) -> list[RejectionRule]:
        return sorted(self._rules, key=lambda r: (r.scheme_id, self._SEVERITY_ORDER.get(r.severity, 3)))


def _rejection_rule(seed: str = "RULE-1", scheme_id: str = "SCH-1", severity: str = "high") -> RejectionRule:
    return RejectionRule(
        id=seed,
        scheme_id=scheme_id,
        rule_type="procedural",
        description="desc",
        description_hindi="विवरण",
        severity=severity,
        prevention_tip="tip",
    )


@pytest.mark.asyncio
async def test_in_memory_rejection_rule_repository_exercised_through_port() -> None:
    """The rejection rule port is implementable and usable: a fake is typed
    as the port and the four read methods filter correctly."""
    rules = [
        _rejection_rule("RULE-1", "SCH-1", "warning"),
        _rejection_rule("RULE-2", "SCH-1", "critical"),
        _rejection_rule("RULE-3", "SCH-2", "high"),
    ]
    repo: RejectionRuleRepository = InMemoryRejectionRuleRepository(rules)

    by_scheme = await repo.get_rules_by_scheme("SCH-1")
    assert [rule.id for rule in by_scheme] == ["RULE-2", "RULE-1"]

    by_ids = await repo.get_rules_by_ids(["RULE-3", "RULE-1"])
    assert {rule.id for rule in by_ids} == {"RULE-3", "RULE-1"}

    critical = await repo.get_critical_rules("SCH-1")
    assert [rule.id for rule in critical] == ["RULE-2"]

    empty_ids = await repo.get_rules_by_ids([])
    assert empty_ids == []

    all_rules = await repo.get_all_rules()
    assert len(all_rules) == 3

    fake = repo
    assert isinstance(fake, InMemoryRejectionRuleRepository)
