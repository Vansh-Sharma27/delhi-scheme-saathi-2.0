"""Golden-master transcript harness for the modular-monolith migration.

Drives ``ConversationService.handle_message`` with all external non-determinism
stubbed to fixed fixtures, records the full response for fixed turn sequences,
and compares against committed golden transcripts.

All non-determinism is pinned:
- LLM analysis, judging, and generation return fixed dicts/strings.
- Scheme matching returns synthetic ``SchemeMatch`` objects.
- Scheme detail rendering (DB queries via ``views``) returns fixed data.
- The clock is frozen so session timestamps are stable.
- Background memory refresh is disabled so no async work leaks.

Spec reference: ARCHITECTURE_MIGRATION_SPEC_v3.md Section 5.2-5.4.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from src.db.session_store import InMemorySessionStore, configure_session_store, get_session_store
from src.models.api import ChatRequest
from src.models.scheme import EligibilityCriteria, Scheme, SchemeMatch
from src.services.conversation import ConversationService

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures"

_FIXED_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

_DEFAULT_JUDGE_RESULT: dict[str, Any] = {
    "should_clarify": False,
    "clarification_question": None,
    "overall_confidence": 0.9,
    "candidate_scores": [],
}


def _make_scheme(
    scheme_id: str,
    *,
    name: str | None = None,
    name_hindi: str | None = None,
    life_event: str = "HOUSING",
    benefits_amount: int = 250000,
    min_age: int = 18,
    max_age: int | None = None,
    max_income: int = 500000,
    genders: list[str] | None = None,
    categories: list[str] | None = None,
    description: str = "A test scheme description for verification.",
    description_hindi: str = "सत्यापन के लिए परीक्षण योजना विवरण।",
) -> Scheme:
    """Create a synthetic scheme for golden fixtures."""
    return Scheme(
        id=scheme_id,
        name=name or f"Scheme {scheme_id}",
        name_hindi=name_hindi or f"योजना {scheme_id}",
        department="Test Department",
        department_hindi="परीक्षण विभाग",
        level="state",
        description=description,
        description_hindi=description_hindi,
        benefits_amount=benefits_amount,
        benefits_frequency="one-time",
        eligibility=EligibilityCriteria(
            min_age=min_age,
            max_age=max_age,
            max_income=max_income,
            genders=genders or ["all"],
            categories=categories or ["OBC", "General"],
        ),
        life_events=[life_event],
        application_url="https://example.com/apply",
        offline_process="Visit the district office",
    )


def _make_match(scheme: Scheme, score: float = 0.8) -> SchemeMatch:
    """Create a synthetic SchemeMatch for golden fixtures."""
    return SchemeMatch(
        scheme=scheme,
        similarity=score,
        eligibility_match={"age": True, "income": True, "category": True},
        deterministic_score=score,
    )


# Synthetic scheme catalogue used across scenarios. IDs are deliberately
# synthetic (SCH-GOLD-*) so they never collide with real seeded data.

SCHEME_HOUSING = _make_scheme(
    "SCH-GOLD-001",
    name="Delhi Housing Assistance",
    name_hindi="दिल्ली आवास सहायता",
    life_event="HOUSING",
    benefits_amount=250000,
    min_age=18,
    max_income=300000,
    categories=["EWS", "LIG"],
)

SCHEME_WIDOW = _make_scheme(
    "SCH-GOLD-002",
    name="Widow Pension Scheme",
    name_hindi="विधवा पेंशन योजना",
    life_event="DEATH_IN_FAMILY",
    benefits_amount=120000,
    min_age=18,
    max_income=100000,
    genders=["female"],
    categories=["SC", "ST", "OBC", "General"],
)

SCHEME_EDUCATION = _make_scheme(
    "SCH-GOLD-003",
    name="Education Loan Scheme",
    name_hindi="शिक्षा ऋण योजना",
    life_event="EDUCATION",
    benefits_amount=500000,
    min_age=18,
    max_income=800000,
    categories=["SC", "ST", "OBC"],
)


@dataclass
class TurnSpec:
    """One turn in a golden scenario."""

    message: str
    message_type: str = "text"
    callback_data: str | None = None
    llm_analysis: dict[str, Any] = field(default_factory=dict)
    llm_judge: dict[str, Any] | None = None
    match_result: list[SchemeMatch] = field(default_factory=list)
    llm_generate: str | None = None
    scheme_for_details: Scheme | None = None
    embedding_failure: bool = False
    llm_timeout: bool = False


@dataclass
class TurnRecord:
    """The recorded output of one turn."""

    response_text: str
    next_state: str
    language: str
    schemes: list[dict[str, Any]] = field(default_factory=list)
    inline_keyboard: list[list[dict[str, str]]] | None = None
    session_state: str = ""
    session_profile: dict[str, Any] = field(default_factory=dict)
    session_selected_scheme_id: str | None = None
    session_presented_schemes: list[dict[str, str]] = field(default_factory=list)
    session_language_preference: str = ""
    session_language_locked: bool = False
    session_currently_asking: str | None = None
    session_completed_turn_count: int = 0


@dataclass
class ScenarioResult:
    """The full recorded transcript for one scenario."""

    scenario_id: str
    turns: list[TurnRecord] = field(default_factory=list)


async def run_scenario(
    scenario_id: str,
    user_id: str,
    turns: list[TurnSpec],
) -> ScenarioResult:
    """Drive a multi-turn conversation and record the transcript.

    All external calls are stubbed. The session store is a fresh
    InMemorySessionStore. The clock is frozen.

    Stubbed non-determinism:

    - ``service.llm.analyze_message``: the LLM turn analysis. Set per turn
      via ``TurnSpec.llm_analysis``.
    - ``service.llm.judge_scheme_relevance``: the LLM relevance gate. Set
      per turn via ``TurnSpec.llm_judge``, defaulting to "no clarification".
    - ``response_generator.get_ai_orchestrator().generate_response``: the
      LLM response generation used by language normalization, grounded
      translation, and scheme-question answering. Returns ``TurnSpec.llm_generate``
      or empty string.
    - ``scheme_matcher.match_schemes``: returns ``TurnSpec.match_result``.
    - ``views.scheme_repo.get_scheme_by_id``: returns
      ``TurnSpec.scheme_for_details`` or ``None``.
    - ``views.document_resolver.resolve_documents_for_scheme``: returns ``[]``.
    - ``views.rejection_engine.get_rejection_warnings``: returns ``[]``.
    - ``views.office_repo.get_nearest_offices`` and
      ``get_offices_by_district``: return ``[]`` (used in CSC handoff).
    - ``enqueue_memory_refresh``: returns ``False`` (no background work).
    - ``datetime.now`` in ``src.models.session`` and
      ``src.services.session_manager``: frozen to ``_FIXED_TIME``.
    """
    configure_session_store(InMemorySessionStore())
    result = ScenarioResult(scenario_id=scenario_id)

    service = ConversationService(db_pool=AsyncMock())

    # Mocks for the DB-layer and integration-layer calls that the
    # conversation service reaches into.
    get_scheme_mock = AsyncMock(return_value=None)
    docs_mock = AsyncMock(return_value=[])
    rejection_mock = AsyncMock(return_value=[])
    offices_nearest_mock = AsyncMock(return_value=[])
    offices_district_mock = AsyncMock(return_value=[])

    # The response_generator's get_ai_orchestrator is called for language
    # normalization, grounded translation, and scheme-question answering.
    # All of those go through orchestrator.generate_response, which we stub
    # on a fake AsyncMock orchestrator.
    fake_resp_ai = AsyncMock()
    fake_resp_ai.generate_response = AsyncMock(return_value="")

    # Embedding client mock: returns a valid embedding by default, or raises
    # when TurnSpec.embedding_failure is set (exercising the fallback path
    # inside the real match_schemes function).
    fake_embedding_client = AsyncMock()
    fake_embedding_client.get_embedding = AsyncMock(return_value=[0.0] * 512)

    # Hybrid search mock: replaces the DB call inside match_schemes.
    # Returns synthetic SchemeMatch objects so the post-filter and ranking
    # in match_schemes run for real.
    fake_hybrid_search = AsyncMock(return_value=[])

    with patch("src.models.session.datetime") as mock_model_dt, patch(
        "src.services.session_manager.datetime"
    ) as mock_mgr_dt, patch(
        "src.services.scheme_matcher.get_embedding_client",
        return_value=fake_embedding_client,
    ), patch(
        "src.services.scheme_matcher.hybrid_search",
        new=fake_hybrid_search,
    ), patch(
        "src.services.conversation.views.scheme_repo.get_scheme_by_id",
        new=get_scheme_mock,
    ), patch(
        "src.services.conversation.views.document_resolver.resolve_documents_for_scheme",
        new=docs_mock,
    ), patch(
        "src.services.conversation.views.rejection_engine.get_rejection_warnings",
        new=rejection_mock,
    ), patch(
        "src.services.conversation.views.office_repo.get_nearest_offices",
        new=offices_nearest_mock,
    ), patch(
        "src.services.conversation.views.office_repo.get_offices_by_district",
        new=offices_district_mock,
    ), patch(
        "src.services.response_generator.get_ai_orchestrator",
        return_value=fake_resp_ai,
    ), patch(
        "src.services.conversation.service.enqueue_memory_refresh",
        new=AsyncMock(return_value=False),
    ):
        mock_model_dt.now.return_value = _FIXED_TIME
        mock_mgr_dt.now.return_value = _FIXED_TIME

        for turn_spec in turns:
            # LLM analysis: the orchestrator's analyze_message checks for
            # an instance override on llm_client.__dict__. Setting it on
            # service.llm (which IS llm_client) makes the override fire.
            if turn_spec.llm_timeout:
                # Simulate timeout: the override raises TimeoutError,
                # triggering the safe-output fallback in _run_task.
                async def _timeout_override(**_kw: Any) -> Any:
                    raise TimeoutError
                service.llm.analyze_message = _timeout_override
            else:
                service.llm.analyze_message = AsyncMock(
                    return_value=turn_spec.llm_analysis
                )
            service.llm.judge_scheme_relevance = AsyncMock(
                return_value=(
                    turn_spec.llm_judge
                    if turn_spec.llm_judge is not None
                    else _DEFAULT_JUDGE_RESULT
                )
            )

            # Matching: set hybrid_search return value per turn. The real
            # match_schemes function runs, exercising the embedding
            # failure path and post-filter for real.
            fake_hybrid_search.return_value = turn_spec.match_result

            # Embedding failure: make get_embedding raise so match_schemes
            # catches it and sets query_embedding=None, exercising the
            # SQL-only fallback ordering path (spec 11.1, 10.4).
            if turn_spec.embedding_failure:
                fake_embedding_client.get_embedding = AsyncMock(
                    side_effect=RuntimeError("embedding provider unavailable"),
                )
            else:
                fake_embedding_client.get_embedding = AsyncMock(
                    return_value=[0.0] * 512,
                )

            # Scheme detail lookups.
            get_scheme_mock.return_value = turn_spec.scheme_for_details

            # LLM generation for this turn.
            fake_resp_ai.generate_response = AsyncMock(
                return_value=turn_spec.llm_generate or ""
            )

            chat_request = ChatRequest(
                user_id=user_id,
                message=turn_spec.message,
                message_type=turn_spec.message_type,
                callback_data=turn_spec.callback_data,
            )
            response = await service.handle_message(chat_request)

            store = get_session_store()
            session = await store.get(user_id)

            record = TurnRecord(
                response_text=response.text,
                next_state=response.next_state or "",
                language=response.language,
                schemes=[
                    s.model_dump() if hasattr(s, "model_dump") else s
                    for s in (response.schemes or [])
                ],
                inline_keyboard=response.inline_keyboard,
            )
            if session is not None:
                record.session_state = session.state.value
                record.session_profile = session.user_profile.model_dump()
                record.session_selected_scheme_id = session.selected_scheme_id
                record.session_presented_schemes = list(session.presented_schemes)
                record.session_language_preference = session.language_preference
                record.session_language_locked = session.language_locked
                record.session_currently_asking = session.currently_asking
                record.session_completed_turn_count = session.completed_turn_count

            result.turns.append(record)

    return result


def result_to_dict(result: ScenarioResult) -> dict[str, Any]:
    """Serialize a ScenarioResult to a JSON-compatible dict."""
    return {
        "scenario_id": result.scenario_id,
        "turns": [asdict(t) for t in result.turns],
    }


def save_fixture(result: ScenarioResult, path: Path | None = None) -> Path:
    """Write a golden fixture to disk."""
    if path is None:
        path = GOLDEN_DIR / f"{result.scenario_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result_to_dict(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_fixture(scenario_id: str, path: Path | None = None) -> dict[str, Any]:
    """Read a golden fixture from disk."""
    if path is None:
        path = GOLDEN_DIR / f"{scenario_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def compare_results(
    actual: ScenarioResult,
    expected: dict[str, Any],
) -> list[str]:
    """Compare actual result against expected fixture. Returns list of diffs."""
    diffs: list[str] = []
    actual_dict = result_to_dict(actual)

    if actual_dict["scenario_id"] != expected["scenario_id"]:
        diffs.append(
            f"scenario_id: expected {expected['scenario_id']!r}, "
            f"got {actual_dict['scenario_id']!r}"
        )

    actual_turns = actual_dict["turns"]
    expected_turns = expected["turns"]
    if len(actual_turns) != len(expected_turns):
        diffs.append(
            f"turn count: expected {len(expected_turns)}, got {len(actual_turns)}"
        )
        return diffs

    for i, (a, e) in enumerate(zip(actual_turns, expected_turns, strict=False)):
        prefix = f"turn {i}"
        for key in e:
            if key not in a:
                diffs.append(f"{prefix}: missing key {key!r}")
                continue
            if a[key] != e[key]:
                diffs.append(
                    f"{prefix}.{key}: expected {json.dumps(e[key], ensure_ascii=False)!r}, "
                    f"got {json.dumps(a[key], ensure_ascii=False)!r}"
                )
    return diffs
