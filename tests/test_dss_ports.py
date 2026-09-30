"""Phase 2 port conformance and in-memory fakes.

Two things are verified per port (spec Phase 2 gate):

1. Existing concrete adapters that the port is the future home for still
   expose every port method. Checked with `issubclass(RealAdapter, Port)`
   under `@runtime_checkable`. This catches a renamed or removed method on
   the adapter during the migration. It does NOT catch signature drift (a
   changed parameter): `runtime_checkable` checks method presence only.
   Signature drift is caught in Phase 3, when callers redirect through the
   port and `mypy src` checks the call sites.

2. An in-memory fake conforms to the port and is awaitable. The fake is the
   test seam Phase 3+ reuses, so proving it conforms and its methods do not
   raise on await is the point. Behavioral asserts are kept only where the
   fake encodes a real invariant the production adapter will share
   (idempotency first-seen, rejection-rule severity order, clock tick); for
   pure recorder fakes (LLM, embeddings, notifier) only conformance and
   awaitability are asserted, because asserting the fake's own hardcoded
   return values would be circular.

Concrete adapters that need live settings to construct (FallbackLLMClient,
FallbackEmbeddingClient, TelegramClient, DynamoDBSessionStore,
SQSAIWorkQueue) are checked with `issubclass`, which needs no instance.
InMemorySessionStore and InMemoryAIWorkQueue need no settings and are
exercised directly through their ports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.config import get_settings
from src.db.session_store import DynamoDBSessionStore, InMemorySessionStore
from src.dss.application.ports.clock import Clock
from src.dss.application.ports.document_repository import DocumentRepository
from src.dss.application.ports.embeddings import EmbeddingProvider
from src.dss.application.ports.idempotency_store import IdempotencyStore
from src.dss.application.ports.llm import (
    LLMProvider,
    ProviderExecutionResult,
    TaskPriority,
)
from src.dss.application.ports.notifier import Notifier
from src.dss.application.ports.office_repository import OfficeRepository
from src.dss.application.ports.rejection_rule_repository import (
    RejectionRuleRepository,
)
from src.dss.application.ports.scheme_repository import SchemeRepository
from src.dss.application.ports.session_repository import SessionStore
from src.dss.application.ports.speech import (
    SpeechProvider,
    STTResult,
    TTSResult,
)
from src.dss.application.ports.work_queue import (
    AIWorkItem,
    AIWorkQueue,
    AIWorkType,
)
from src.dss.infrastructure.embeddings.fallback_client import EMBEDDING_DIM, FallbackEmbeddingClient
from src.dss.infrastructure.speech.bhashini import BhashiniClient
from src.dss.infrastructure.speech.sarvam import SarvamClient
from src.integrations.llm_client import FallbackLLMClient
from src.integrations.telegram import TelegramClient
from src.models.rejection_rule import RejectionRule
from src.models.session import Session
from src.services.ai_orchestrator import AIOrchestrator, AITaskType
from src.services.scheme_relevance import (
    CLARIFY_CONFIDENCE_THRESHOLD,
    PRESENT_CONFIDENCE_THRESHOLD,
)


def test_llm_port_conformance() -> None:
    """FallbackLLMClient exposes every LLMProvider method. Catches a rename
    or removal on the production adapter; does not catch signature drift."""
    assert issubclass(FallbackLLMClient, LLMProvider)


def test_frozen_constants_sentinel() -> None:
    """Pins the five frozen values the PR #2 review (F3/N3) found silently
    mutable: the two relevance thresholds, the two relevance-skipping config
    defaults, the orchestrator's per-task policies, and EMBEDDING_DIM. A
    change to any of them must be a deliberate, reviewed act, not a silent
    drift; this test makes the change visible by failing the suite."""
    assert PRESENT_CONFIDENCE_THRESHOLD == 0.6
    assert CLARIFY_CONFIDENCE_THRESHOLD == 0.45
    settings = get_settings()
    assert settings.ai_relevance_min_deterministic_score == 0.85
    assert settings.ai_relevance_score_gap_threshold == 0.15
    policies = AIOrchestrator._POLICIES
    assert policies[AITaskType.ANALYZE_MESSAGE].timeout_seconds == 8.0
    assert policies[AITaskType.ANALYZE_MESSAGE].priority == "inline"
    assert policies[AITaskType.JUDGE_SCHEME_RELEVANCE].timeout_seconds == 3.0
    assert policies[AITaskType.JUDGE_SCHEME_RELEVANCE].priority == "inline"
    assert policies[AITaskType.GENERATE_RESPONSE].timeout_seconds == 8.0
    assert policies[AITaskType.GENERATE_RESPONSE].priority == "inline"
    assert policies[AITaskType.REFRESH_WORKING_MEMORY].timeout_seconds == 20.0
    assert policies[AITaskType.REFRESH_WORKING_MEMORY].priority == "background"
    assert EMBEDDING_DIM == 1024


def test_embedding_port_conformance() -> None:
    """FallbackEmbeddingClient exposes every EmbeddingProvider method."""
    assert issubclass(FallbackEmbeddingClient, EmbeddingProvider)


def test_notifier_port_conformance() -> None:
    """TelegramClient exposes every Notifier method (no construction; the
    client needs live settings)."""
    assert issubclass(TelegramClient, Notifier)


def test_session_repository_port_conformance() -> None:
    """Both session store backends expose the SessionStore methods. DynamoDB
    is checked via issubclass without construction, so no boto3 client."""
    assert issubclass(InMemorySessionStore, SessionStore)
    assert issubclass(DynamoDBSessionStore, SessionStore)


class FakeLLMProvider:
    """Deterministic LLM provider. Returns canned payloads sized for the four
    task types and their `*_with_meta` variants. Pure recorder: Phase 3
    tests assert behaviour through it, so Phase 2 only proves conformance
    and awaitability."""

    def __init__(self) -> None:
        self.calls: int = 0
        self._analysis: dict[str, Any] = {"intent": "unknown", "language": "hi"}
        self._relevance: dict[str, Any] = {"overall_confidence": 0.5, "candidate_scores": []}

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
        self.calls += 1
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
        self.calls += 1
        return ProviderExecutionResult(output=dict(self._analysis), provider="fake", fallback_used=False, latency_ms=1.0)

    async def generate_response(
        self,
        context: dict[str, Any],
        system_prompt: str,
        user_language: str = "hi",
        priority: TaskPriority = "inline",
    ) -> str:
        self.calls += 1
        return "नमस्ते"

    async def generate_response_with_meta(
        self,
        context: dict[str, Any],
        system_prompt: str,
        user_language: str = "hi",
        priority: TaskPriority = "inline",
    ) -> ProviderExecutionResult[str]:
        self.calls += 1
        return ProviderExecutionResult(output="नमस्ते", provider="fake", fallback_used=False, latency_ms=1.0)

    async def summarize_conversation(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
        priority: TaskPriority = "background",
    ) -> str:
        self.calls += 1
        return current_summary or ""

    async def summarize_conversation_with_meta(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
        priority: TaskPriority = "background",
    ) -> ProviderExecutionResult[str]:
        self.calls += 1
        return ProviderExecutionResult(output=current_summary or "", provider="fake", fallback_used=False, latency_ms=1.0)

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
        self.calls += 1
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
        self.calls += 1
        return ProviderExecutionResult(output=dict(self._relevance), provider="fake", fallback_used=False, latency_ms=1.0)


@pytest.mark.asyncio
async def test_fake_llm_provider_conforms_and_is_awaitable() -> None:
    """FakeLLMProvider conforms to LLMProvider and every method (including
    the four *_with_meta variants) is awaitable and returns the port-declared
    type. Return values are not asserted: they are canned data the fake owns."""
    provider: LLMProvider = FakeLLMProvider()
    assert isinstance(provider, LLMProvider)

    assert isinstance(await provider.analyze_message("", [], "", {}, ""), dict)
    assert isinstance(await provider.analyze_message_with_meta("", [], "", {}, ""), ProviderExecutionResult)
    assert isinstance(await provider.generate_response({}, "", "hi"), str)
    assert isinstance(await provider.generate_response_with_meta({}, ""), ProviderExecutionResult)
    assert isinstance(await provider.summarize_conversation([], None), str)
    assert isinstance(await provider.summarize_conversation_with_meta([]), ProviderExecutionResult)
    assert isinstance(await provider.judge_scheme_relevance("", [], "", {}, []), dict)
    assert isinstance(await provider.judge_scheme_relevance_with_meta("", [], "", {}, []), ProviderExecutionResult)
    assert provider.calls == 8


class FakeEmbeddingProvider:
    """Deterministic embedding provider. None for unknown text mirrors the
    frozen-list rule (spec 10.4): a missing embedding must skip vector
    ranking, not corrupt the query."""

    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {"आवास": [1.0, 0.0, 0.0]}

    async def get_embedding(self, text: str) -> list[float] | None:
        return self._vectors.get(text)

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._vectors.get(text, [0.0, 0.0, 0.0]) for text in texts]


@pytest.mark.asyncio
async def test_fake_embedding_provider_conforms_and_none_on_miss() -> None:
    """FakeEmbeddingProvider conforms to EmbeddingProvider. The None-on-miss
    branch is the one invariant the matching layer depends on (skip vector
    ranking), so it is asserted; the hit values are canned and not asserted."""
    provider: EmbeddingProvider = FakeEmbeddingProvider()
    assert isinstance(provider, EmbeddingProvider)

    assert await provider.get_embedding("unknown") is None
    assert isinstance(await provider.get_embedding("आवास"), list)
    assert await provider.get_embeddings_batch([]) == []
    assert len(await provider.get_embeddings_batch(["आवास", "unknown"])) == 2


class FakeClock:
    """Fixed clock. `tick` advances the fixed time; tests that cover
    ordering over time (TTL, memory-refresh lag) use it."""

    def __init__(self, fixed: datetime | None = None) -> None:
        self._fixed = fixed or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._fixed

    def tick(self, to: datetime) -> None:
        self._fixed = to


def test_fake_clock_conforms_and_tick_advances() -> None:
    """FakeClock conforms to Clock, returns a stable UTC datetime, and tick
    advances it. The advancement is the real invariant: TTL and refresh-lag
    tests compare two reads, so the clock must move on demand."""
    clock: Clock = FakeClock()
    assert isinstance(clock, Clock)

    first = clock.now()
    assert first == clock.now()
    assert first.tzinfo == UTC

    clock.tick(datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC))
    assert clock.now() > first


class InMemoryIdempotencyStore:
    """Set-backed atomic claim store. A single set with no await between
    check and insert is atomic within one event loop, which is enough for
    the unit tests. Cross-process races need a real conditional-write
    backend; this fake does not model them."""

    def __init__(self) -> None:
        self._seen: set[int] = set()

    async def claim(self, update_id: int) -> bool:
        if update_id in self._seen:
            return False
        self._seen.add(update_id)
        return True


@pytest.mark.asyncio
async def test_in_memory_idempotency_store_conforms_and_first_seen_wins() -> None:
    """InMemoryIdempotencyStore conforms to IdempotencyStore. First-seen is
    the real invariant: the port exists because Telegram retries, so the
    first claim must return True and every retry False."""
    store: IdempotencyStore = InMemoryIdempotencyStore()
    assert isinstance(store, IdempotencyStore)

    assert await store.claim(123456) is True
    assert await store.claim(123456) is False
    assert await store.claim(123457) is True
    assert await store.claim(123456) is False


class FakeNotifier:
    """Recording notifier. Captures outbound sends so Phase 3+ tests assert
    what the conversation layer sent without hitting the Telegram API."""

    def __init__(self, voice_bytes: bytes = b"audio") -> None:
        self.texts: list[tuple[int | str, str]] = []
        self.keyboards: list[dict[str, Any]] = []
        self.callback_answers: list[str] = []
        self.chat_actions: list[tuple[int | str, str]] = []
        self.voice_sends: int = 0
        self.audio_sends: int = 0
        self.download_returns: list[str] = []
        self._voice_bytes = voice_bytes

    async def send_text(self, chat_id: int | str, text: str, parse_mode: str | None = None) -> dict[str, Any]:
        self.texts.append((chat_id, text))
        return {"ok": True}

    async def send_inline_keyboard(
        self, chat_id: int | str, text: str, buttons: list[list[dict[str, str]]], parse_mode: str | None = None
    ) -> dict[str, Any]:
        self.keyboards.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"ok": True}

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> dict[str, Any]:
        self.callback_answers.append(callback_query_id)
        return {"ok": True}

    async def send_chat_action(self, chat_id: int | str, action: str = "typing") -> dict[str, Any]:
        self.chat_actions.append((chat_id, action))
        return {"ok": True}

    async def send_voice(
        self, chat_id: int | str, voice_data: bytes | str, caption: str | None = None,
        filename: str = "response.ogg", content_type: str = "audio/ogg",
    ) -> dict[str, Any]:
        self.voice_sends += 1
        return {"ok": True}

    async def send_audio(
        self, chat_id: int | str, audio_bytes: bytes, filename: str = "response.ogg",
        caption: str | None = None, content_type: str = "audio/ogg",
    ) -> dict[str, Any]:
        self.audio_sends += 1
        return {"ok": True}

    async def download_voice(self, file_id: str) -> bytes:
        self.download_returns.append(file_id)
        return self._voice_bytes


@pytest.mark.asyncio
async def test_fake_notifier_conforms_and_records() -> None:
    """FakeNotifier conforms to Notifier and every method is awaitable. The
    recorder counts are asserted because Phase 3 tests read them to verify
    what the conversation layer sent; a broken recorder would silently lose
    assertions later. Return payloads are canned and not asserted."""
    notifier: Notifier = FakeNotifier(voice_bytes=b"voice")
    assert isinstance(notifier, Notifier)

    await notifier.send_chat_action(123, "typing")
    await notifier.answer_callback_query("cb-1")
    await notifier.send_text(123, "नमस्ते")
    await notifier.send_inline_keyboard(123, "चुनें", [[{"text": "1", "callback_data": "1"}]])
    assert await notifier.download_voice("file-abc") == b"voice"
    await notifier.send_voice(123, b"x")
    await notifier.send_audio(123, b"x")

    fake = notifier
    assert isinstance(fake, FakeNotifier)
    assert fake.chat_actions == [(123, "typing")]
    assert fake.callback_answers == ["cb-1"]
    assert fake.texts == [(123, "नमस्ते")]
    assert len(fake.keyboards) == 1
    assert fake.download_returns == ["file-abc"]
    assert fake.voice_sends == 1
    assert fake.audio_sends == 1


@pytest.mark.asyncio
async def test_in_memory_session_store_exercised_through_port() -> None:
    """InMemorySessionStore (the real local-dev adapter, no settings needed)
    is exercised through the SessionStore port with a save/get/delete
    round-trip. This is both the gate's in-memory fake and a real behaviour
    check that the existing adapter still round-trips a Session, including
    the deep-copy the store does on save and get."""
    store: SessionStore = InMemorySessionStore()
    assert isinstance(store, SessionStore)

    session = Session(user_id="api:roundtrip")
    await store.save(session)
    fetched = await store.get("api:roundtrip")
    assert fetched is not None
    assert fetched.user_id == "api:roundtrip"
    assert fetched is not session

    await store.delete("api:roundtrip")
    assert await store.get("api:roundtrip") is None


def test_work_queue_port_conformance() -> None:
    """Both queue backends expose the AIWorkQueue methods. issubclass needs
    no construction, so SQSAIWorkQueue is checked without a boto3 client."""
    from src.services.ai_background import InMemoryAIWorkQueue, SQSAIWorkQueue

    assert issubclass(InMemoryAIWorkQueue, AIWorkQueue)
    assert issubclass(SQSAIWorkQueue, AIWorkQueue)


@pytest.mark.asyncio
async def test_in_memory_ai_work_queue_exercised_through_port() -> None:
    """InMemoryAIWorkQueue (the real local-dev adapter) is exercised through
    the AIWorkQueue port with an enqueue/dequeue/ack round-trip. The
    FIFO order is the real invariant: the worker drains items in the order
    they were enqueued, so a later item must not dequeue before an earlier
    one. The payload type AIWorkItem is also constructed and read through
    the port types to confirm the moved dataclass still round-trips."""
    from src.services.ai_background import InMemoryAIWorkQueue

    queue: AIWorkQueue = InMemoryAIWorkQueue()
    assert isinstance(queue, AIWorkQueue)

    first = AIWorkItem(work_type=AIWorkType.REFRESH_WORKING_MEMORY, user_id="api:u1", turn_count=1)
    second = AIWorkItem(work_type=AIWorkType.REFRESH_WORKING_MEMORY, user_id="api:u2", turn_count=2)
    await queue.enqueue(first)
    await queue.enqueue(second)

    out1 = await queue.dequeue()
    assert out1 is not None
    assert out1.user_id == "api:u1"
    out2 = await queue.dequeue()
    assert out2 is not None
    assert out2.user_id == "api:u2"

    await queue.ack(out1)
    await queue.ack(out2)
    await queue.close()


class InMemoryRejectionRuleRepository:
    """List-backed rejection rule repository. Severity order mirrors the
    legacy repo (critical, high, warning), which is the order the
    rejection-warnings view truncates from."""

    _SEVERITY_ORDER = {"critical": 0, "high": 1, "warning": 2}

    def __init__(self, rules: list[RejectionRule] | None = None) -> None:
        self._rules: list[RejectionRule] = list(rules or [])

    async def get_rules_by_scheme(self, scheme_id: str) -> list[RejectionRule]:
        hits = [r for r in self._rules if r.scheme_id == scheme_id]
        return sorted(hits, key=lambda r: self._SEVERITY_ORDER.get(r.severity, 3))

    async def get_rules_by_ids(self, rule_ids: list[str]) -> list[RejectionRule]:
        if not rule_ids:
            return []
        wanted = set(rule_ids)
        return sorted(
            [r for r in self._rules if r.id in wanted],
            key=lambda r: self._SEVERITY_ORDER.get(r.severity, 3),
        )

    async def get_critical_rules(self, scheme_id: str) -> list[RejectionRule]:
        return [r for r in self._rules if r.scheme_id == scheme_id and r.severity == "critical"]

    async def get_all_rules(self) -> list[RejectionRule]:
        return sorted(self._rules, key=lambda r: (r.scheme_id, self._SEVERITY_ORDER.get(r.severity, 3)))


def _rule(seed: str, scheme_id: str, severity: str) -> RejectionRule:
    return RejectionRule(
        id=seed, scheme_id=scheme_id, rule_type="procedural",
        description="d", description_hindi="वि", severity=severity, prevention_tip="t",
    )


@pytest.mark.asyncio
async def test_in_memory_rejection_rule_repository_conforms_and_orders_by_severity() -> None:
    """InMemoryRejectionRuleRepository conforms to RejectionRuleRepository.
    Severity ordering is the real invariant: the rejection-warnings view
    truncates to five rules, so a critical rule must sort above a warning or
    it gets dropped. The order, not the canned rule content, is asserted."""
    repo: RejectionRuleRepository = InMemoryRejectionRuleRepository([
        _rule("R1", "S1", "warning"),
        _rule("R2", "S1", "critical"),
        _rule("R3", "S2", "high"),
    ])
    assert isinstance(repo, RejectionRuleRepository)

    by_scheme = await repo.get_rules_by_scheme("S1")
    assert [r.id for r in by_scheme] == ["R2", "R1"]

    by_ids = await repo.get_rules_by_ids(["R3", "R1"])
    assert [r.id for r in by_ids] == ["R3", "R1"]

    critical = await repo.get_critical_rules("S1")
    assert [r.id for r in critical] == ["R2"]

    assert await repo.get_rules_by_ids([]) == []
    assert len(await repo.get_all_rules()) == 3


class InMemorySchemeRepository:
    """List-backed scheme repository. When no embedding is passed to
    `hybrid_search`, the legacy repo falls back to ordering by
    `benefits_amount DESC` (spec 11.1); the fake mirrors that fallback so
    Phase 3 tests of the matching layer can pin it."""

    def __init__(self, schemes: list[Any] | None = None) -> None:
        self._schemes: list[Any] = list(schemes or [])

    async def get_scheme_by_id(self, scheme_id: str) -> Any:
        return next((s for s in self._schemes if s.id == scheme_id), None)

    async def get_schemes_by_life_event(self, life_event: str, limit: int = 10) -> list[Any]:
        hits = [s for s in self._schemes if life_event in s.life_events]
        return sorted(hits, key=lambda s: s.benefits_amount or 0, reverse=True)[:limit]

    async def get_all_schemes(self, active_only: bool = True) -> list[Any]:
        hits = self._schemes if not active_only else [s for s in self._schemes if s.is_active]
        return sorted(hits, key=lambda s: s.name)

    async def hybrid_search(
        self,
        life_event: str | None,
        profile: Any,
        query_embedding: list[float] | None = None,
        limit: int = 5,
    ) -> list[Any]:
        from src.models.scheme import SchemeMatch

        hits = self._schemes if life_event is None else [
            s for s in self._schemes if life_event in s.life_events
        ]
        ordered = sorted(hits, key=lambda s: s.benefits_amount or 0, reverse=True)
        return [SchemeMatch(scheme=s, similarity=0.0) for s in ordered[:limit]]

    async def search_schemes_by_text(self, search_text: str, limit: int = 10) -> list[Any]:
        needle = search_text.lower()
        hits = [
            s for s in self._schemes
            if needle in s.name.lower() or needle in s.description.lower()
        ]
        return sorted(hits, key=lambda s: s.benefits_amount or 0, reverse=True)[:limit]

    async def get_scheme_debug_rows(self, scheme_ids: list[str]) -> list[dict[str, Any]]:
        wanted = set(scheme_ids)
        return [
            {"id": s.id, "name": s.name, "life_events": list(s.life_events)}
            for s in self._schemes if s.id in wanted
        ]


def _scheme(
    sid: str, name: str, benefits_amount: int | None, life_events: list[str], active: bool = True
) -> Any:
    from src.models.scheme import Scheme

    return Scheme(
        id=sid, name=name, name_hindi=name, department="d", department_hindi="ड",
        level="state", description="desc", description_hindi="वि",
        benefits_amount=benefits_amount, life_events=life_events, is_active=active,
    )


@pytest.mark.asyncio
async def test_in_memory_scheme_repository_conforms_and_fallback_orders_by_benefit() -> None:
    """InMemorySchemeRepository conforms to SchemeRepository. The asserted
    invariant is the spec 11.1 fallback: when no embedding is passed,
    `hybrid_search` orders candidates by `benefits_amount DESC`. That is the
    degradation path the matching layer silently takes on any embedding
    failure, so a port fake that does not reproduce it would mislead Phase 3
    tests. `get_scheme_by_id` returning None for a miss is also asserted
    because the views layer branches on it."""
    repo: SchemeRepository = InMemorySchemeRepository([
        _scheme("S1", "Small Benefit", 1000, ["HOUSING"]),
        _scheme("S2", "Large Benefit", 50000, ["HOUSING"]),
        _scheme("S3", "No Amount", None, ["HOUSING"]),
        _scheme("S4", "Other Event", 2000, ["HEALTH_CRISIS"]),
    ])
    assert isinstance(repo, SchemeRepository)

    by_id = await repo.get_scheme_by_id("S1")
    assert by_id is not None and by_id.id == "S1"
    assert await repo.get_scheme_by_id("missing") is None

    matches = await repo.hybrid_search("HOUSING", profile=None, query_embedding=None)
    assert [m.scheme.id for m in matches] == ["S2", "S1", "S3"]

    by_event = await repo.get_schemes_by_life_event("HOUSING")
    assert [s.id for s in by_event] == ["S2", "S1", "S3"]

    active = await repo.get_all_schemes(active_only=True)
    assert {s.id for s in active} == {"S1", "S2", "S3", "S4"}

    rows = await repo.get_scheme_debug_rows(["S1", "S4"])
    assert {r["id"] for r in rows} == {"S1", "S4"}


class InMemoryDocumentRepository:
    """List-backed document repository. `get_documents_for_scheme` takes a
    scheme id, not a scheme object, because the legacy repo reads the
    scheme's `documents_required` array from the schemes table; the fake
    keeps a side map of scheme id to required document ids to mirror that."""

    def __init__(
        self,
        documents: list[Any] | None = None,
        scheme_docs: dict[str, list[str]] | None = None,
    ) -> None:
        self._docs: list[Any] = list(documents or [])
        self._scheme_docs: dict[str, list[str]] = dict(scheme_docs or {})

    async def get_document_by_id(self, doc_id: str) -> Any:
        return next((d for d in self._docs if d.id == doc_id), None)

    async def get_documents_by_ids(self, doc_ids: list[str]) -> list[Any]:
        if not doc_ids:
            return []
        wanted = set(doc_ids)
        return [d for d in self._docs if d.id in wanted]

    async def get_all_documents(self) -> list[Any]:
        return sorted(self._docs, key=lambda d: d.name)

    async def get_documents_for_scheme(self, scheme_id: str) -> list[Any]:
        required = self._scheme_docs.get(scheme_id, [])
        wanted = set(required)
        return [d for d in self._docs if d.id in wanted]

    async def search_documents(self, query: str, limit: int = 10) -> list[Any]:
        needle = query.lower()
        hits = [d for d in self._docs if needle in d.name.lower() or needle in d.name_hindi.lower()]
        return sorted(hits, key=lambda d: d.name)[:limit]


def _document(doc_id: str, name: str, name_hindi: str = "ड") -> Any:
    from src.models.document import Document

    return Document(
        id=doc_id, name=name, name_hindi=name_hindi, issuing_authority="UIDAI",
    )


@pytest.mark.asyncio
async def test_in_memory_document_repository_conforms_and_resolves_scheme_docs() -> None:
    """InMemoryDocumentRepository conforms to DocumentRepository. The
    asserted invariant is `get_documents_for_scheme` resolving the scheme's
    required-documents list to Document objects, which is the path the
    guidance layer uses to show what to bring. `get_document_by_id` returning
    None for a miss is asserted because the document-detail endpoint
    branches on it. `get_documents_by_ids([])` returning an empty list is
    asserted because the legacy repo guards it explicitly."""
    repo: DocumentRepository = InMemoryDocumentRepository(
        documents=[
            _document("DOC-1", "Aadhaar"),
            _document("DOC-2", "Income Certificate", "आय प्रमाण पत्र"),
            _document("DOC-3", "Death Certificate"),
        ],
        scheme_docs={"SCH-1": ["DOC-1", "DOC-2"]},
    )
    assert isinstance(repo, DocumentRepository)

    assert (await repo.get_document_by_id("DOC-1")).id == "DOC-1"
    assert await repo.get_document_by_id("missing") is None

    by_ids = await repo.get_documents_by_ids(["DOC-3", "DOC-1"])
    assert {d.id for d in by_ids} == {"DOC-1", "DOC-3"}
    assert await repo.get_documents_by_ids([]) == []

    scheme_docs = await repo.get_documents_for_scheme("SCH-1")
    assert {d.id for d in scheme_docs} == {"DOC-1", "DOC-2"}
    assert await repo.get_documents_for_scheme("SCH-2") == []

    assert len(await repo.get_all_documents()) == 3
    hits = await repo.search_documents("income")
    assert [d.id for d in hits] == ["DOC-2"]


class InMemoryOfficeRepository:
    """List-backed office repository. `get_offices_by_service` filters by a
    document id appearing in the office's `services` list, which is the
    filter the guidance layer uses to find where to procure a document."""

    def __init__(self, offices: list[Any] | None = None) -> None:
        self._offices: list[Any] = list(offices or [])

    async def get_office_by_id(self, office_id: str) -> Any:
        return next((o for o in self._offices if o.id == office_id), None)

    async def get_offices_by_district(self, district: str, limit: int = 10) -> list[Any]:
        hits = [o for o in self._offices if district.lower() in o.district.lower()]
        return sorted(hits, key=lambda o: (o.type, o.name))[:limit]

    async def get_nearest_offices(
        self,
        latitude: float,
        longitude: float,
        limit: int = 5,
        office_type: str | None = None,
    ) -> list[Any]:
        hits = self._offices if office_type is None else [o for o in self._offices if o.type == office_type]
        return sorted(hits, key=lambda o: o.name)[:limit]

    async def get_offices_by_service(
        self,
        document_id: str,
        district: str | None = None,
        limit: int = 10,
    ) -> list[Any]:
        hits = [o for o in self._offices if document_id in o.services]
        if district:
            hits = [o for o in hits if district.lower() in o.district.lower()]
        return sorted(hits, key=lambda o: (o.type, o.name))[:limit]

    async def get_all_offices(self) -> list[Any]:
        return sorted(self._offices, key=lambda o: (o.district, o.name))


def _office(oid: str, district: str, services: list[str], otype: str = "CSC") -> Any:
    from src.models.office import Office

    return Office(
        id=oid, name=oid, type=otype, address="addr", district=district, services=services,
    )


@pytest.mark.asyncio
async def test_in_memory_office_repository_conforms_and_filters_by_service() -> None:
    """InMemoryOfficeRepository conforms to OfficeRepository. The asserted
    invariant is `get_offices_by_service` filtering by a document id in the
    office's `services` list, which is the path the guidance layer uses to
    find where to procure a document. The district narrowing on the same
    call is asserted because the endpoint takes both. `get_office_by_id`
    returning None for a miss is asserted because the office view branches
    on it."""
    repo: OfficeRepository = InMemoryOfficeRepository([
        _office("OFF-1", "North Delhi", ["DOC-1", "DOC-2"]),
        _office("OFF-2", "South Delhi", ["DOC-2"]),
        _office("OFF-3", "North Delhi", ["DOC-3"]),
    ])
    assert isinstance(repo, OfficeRepository)

    assert (await repo.get_office_by_id("OFF-1")).id == "OFF-1"
    assert await repo.get_office_by_id("missing") is None

    by_service = await repo.get_offices_by_service("DOC-2")
    assert {o.id for o in by_service} == {"OFF-1", "OFF-2"}

    by_service_north = await repo.get_offices_by_service("DOC-2", district="North")
    assert [o.id for o in by_service_north] == ["OFF-1"]

    by_district = await repo.get_offices_by_district("North")
    assert {o.id for o in by_district} == {"OFF-1", "OFF-3"}

    assert len(await repo.get_all_offices()) == 3


def test_speech_port_conformance() -> None:
    """Both speech adapters expose the SpeechProvider methods. issubclass
    needs no construction, so neither SarvamClient nor BhashiniClient needs
    live settings."""
    assert issubclass(SarvamClient, SpeechProvider)
    assert issubclass(BhashiniClient, SpeechProvider)


class FakeSpeechProvider:
    """Deterministic speech provider. Returns a fixed transcript and a
    fixed audio payload. Used to exercise the webhook handler's voice path
    through the port without hitting Sarvam or Bhashini."""

    def __init__(self) -> None:
        self.stt_calls: int = 0
        self.tts_calls: int = 0

    async def speech_to_text(
        self,
        audio_bytes: bytes,
        source_lang: str = "hi",
        audio_format: str = "ogg",
    ) -> STTResult:
        self.stt_calls += 1
        return STTResult(text="मुझे आवास चाहिए", confidence=0.9, language=source_lang)

    async def text_to_speech(
        self,
        text: str,
        target_lang: str = "hi",
        voice: str = "female",
    ) -> TTSResult:
        self.tts_calls += 1
        return TTSResult(audio_bytes=b"audio-bytes", content_type="audio/ogg")


@pytest.mark.asyncio
async def test_fake_speech_provider_conforms_and_round_trips() -> None:
    """FakeSpeechProvider conforms to SpeechProvider. The asserted invariant
    is the result-type identity: the fake returns the port's canonical
    STTResult and TTSResult (the same class both legacy adapters now
    re-export), so isinstance checks in test_webhook and test_sarvam keep
    working against one class."""
    provider: SpeechProvider = FakeSpeechProvider()
    assert isinstance(provider, SpeechProvider)

    stt = await provider.speech_to_text(b"audio", source_lang="hi")
    assert isinstance(stt, STTResult)
    assert stt.language == "hi"

    tts = await provider.text_to_speech("नमस्ते")
    assert isinstance(tts, TTSResult)
    assert tts.audio_bytes == b"audio-bytes"

    fake = provider
    assert isinstance(fake, FakeSpeechProvider)
    assert fake.stt_calls == 1
    assert fake.tts_calls == 1
