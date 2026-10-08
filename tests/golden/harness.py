"""Deterministic golden-master harness for the conversation pipeline.

The harness drives ``ConversationService.handle_message`` with injected local
state and fake external providers. Fixtures contain a normalized snapshot of
all ChatResponse fields, all persisted Session fields, and stable AI telemetry.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.dss.application.conversation.contracts import ChatResponse
from src.dss.application.ports.session_repository import SessionStore
from src.dss.domain.conversations.session import Session
from src.dss.domain.schemes.scheme import EligibilityCriteria, Scheme, SchemeMatch
from src.dss.observability.llm_usage import LLMUsageEvent

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures"
GOLDEN_REGENERATE_APPROVAL_ENV = "GOLDEN_REGENERATE_APPROVED"

_FIXED_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
_TIMEOUT_SECONDS = 0.01
_SCENARIO_ID_RE = re.compile(r"[a-z0-9_]+")


class _FixedClock:
    """Time source shared by conversation mutations and storage."""

    def now(self) -> datetime:
        return _FIXED_TIME


_CAPTURED_RESPONSE_FIELDS = {
    "text",
    "text_hindi",
    "audio_url",
    "schemes",
    "documents",
    "rejection_warnings",
    "offices",
    "inline_keyboard",
    "next_state",
    "language",
}
_CAPTURED_SESSION_FIELDS = {
    "user_id",
    "state",
    "user_profile",
    "messages",
    "working_memory",
    "discussed_schemes",
    "selected_scheme_id",
    "language_preference",
    "language_locked",
    "currently_asking",
    "skipped_fields",
    "awaiting_profile_change",
    "presented_schemes",
    "completed_turn_count",
    "last_memory_refresh_turn",
    "pending_memory_job",
    "created_at",
    "updated_at",
    "metadata",
}

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


# Synthetic catalogue. IDs cannot collide with real seeded data.
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

SCHEME_RENTAL = _make_scheme(
    "SCH-GOLD-004",
    name="Delhi Rental Support",
    name_hindi="दिल्ली किराया सहायता",
    life_event="HOUSING",
    benefits_amount=100000,
    min_age=18,
    max_income=300000,
    categories=["EWS", "LIG"],
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
    """Stable, explicit projection of one response and its persisted session."""

    response_text: str
    response_text_hindi: str | None
    response_audio_url: str | None
    response_documents: list[dict[str, Any]]
    response_rejection_warnings: list[dict[str, Any]]
    response_offices: list[dict[str, Any]]
    next_state: str
    language: str
    schemes: list[dict[str, Any]]
    inline_keyboard: list[list[dict[str, str]]] | None
    session_user_id: str = ""
    session_state: str = ""
    session_profile: dict[str, Any] = field(default_factory=dict)
    session_messages: list[dict[str, Any]] = field(default_factory=list)
    session_working_memory: dict[str, Any] = field(default_factory=dict)
    session_discussed_schemes: list[str] = field(default_factory=list)
    session_selected_scheme_id: str | None = None
    session_presented_schemes: list[dict[str, str]] = field(default_factory=list)
    session_language_preference: str = ""
    session_language_locked: bool = False
    session_currently_asking: str | None = None
    session_skipped_fields: list[str] = field(default_factory=list)
    session_awaiting_profile_change: bool = False
    session_completed_turn_count: int = 0
    session_last_memory_refresh_turn: int = 0
    session_pending_memory_job: bool = False
    session_created_at: str | None = None
    session_updated_at: str | None = None
    session_metadata: dict[str, Any] = field(default_factory=dict)
    ai_events: list[dict[str, Any]] = field(default_factory=list)
    llm_timeout_cancelled: bool = False


@dataclass
class ScenarioResult:
    """The normalized transcript for one scenario."""

    scenario_id: str
    turns: list[TurnRecord] = field(default_factory=list)


def _model_dump(value: Any) -> dict[str, Any]:
    """Serialize one Pydantic model using JSON-compatible values."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _event_snapshot(event: LLMUsageEvent) -> dict[str, Any]:
    """Keep stable telemetry fields; wall-clock latency is intentionally omitted."""
    return {
        "task_type": event.task_type,
        "provider": event.provider,
        "fallback_used": event.fallback_used,
        "error": event.error,
    }


async def run_scenario(
    scenario_id: str,
    user_id: str,
    turns: list[TurnSpec],
    *,
    session_store: SessionStore | None = None,
) -> ScenarioResult:
    """Drive the canonical graph with constructor-injected deterministic ports."""
    from tests.golden.runtime import run_scenario as run_canonical

    return await run_canonical(scenario_id, user_id, turns, session_store=session_store)


def result_to_dict(result: ScenarioResult) -> dict[str, Any]:
    """Serialize a ScenarioResult to a JSON-compatible dictionary."""
    return {
        "scenario_id": result.scenario_id,
        "turns": [asdict(turn) for turn in result.turns],
    }


def _fixture_path(scenario_id: str) -> Path:
    """Return the only allowed fixture path for a validated scenario id."""
    if _SCENARIO_ID_RE.fullmatch(scenario_id) is None:
        raise ValueError(f"Invalid golden scenario id: {scenario_id!r}")
    return GOLDEN_DIR / f"{scenario_id}.json"


def validate_fixture(
    fixture: Any,
    *,
    expected_scenario_id: str | None = None,
) -> list[str]:
    """Validate exact fixture structure without trusting fixture-controlled keys."""
    errors: list[str] = []
    if set(ChatResponse.model_fields) != _CAPTURED_RESPONSE_FIELDS:
        errors.append("harness: ChatResponse snapshot coverage is stale")
    if set(Session.model_fields) != _CAPTURED_SESSION_FIELDS:
        errors.append("harness: Session snapshot coverage is stale")
    if not isinstance(fixture, dict):
        return ["fixture: expected an object"]

    expected_top_keys = {"scenario_id", "turns"}
    actual_top_keys = set(fixture)
    if actual_top_keys != expected_top_keys:
        errors.append(
            "fixture: key mismatch; "
            f"missing={sorted(expected_top_keys - actual_top_keys)}, "
            f"unexpected={sorted(actual_top_keys - expected_top_keys)}"
        )

    scenario_id = fixture.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id:
        errors.append("fixture.scenario_id: expected a non-empty string")
    elif expected_scenario_id is not None and scenario_id != expected_scenario_id:
        errors.append(
            f"fixture.scenario_id: expected {expected_scenario_id!r}, got {scenario_id!r}"
        )

    turns = fixture.get("turns")
    if not isinstance(turns, list):
        errors.append("fixture.turns: expected a list")
        return errors
    if not turns:
        errors.append("fixture.turns: expected at least one turn")
        return errors

    expected_turn_keys = {item.name for item in fields(TurnRecord)}
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            errors.append(f"turn {index}: expected an object")
            continue
        actual_turn_keys = set(turn)
        if actual_turn_keys != expected_turn_keys:
            errors.append(
                f"turn {index}: key mismatch; "
                f"missing={sorted(expected_turn_keys - actual_turn_keys)}, "
                f"unexpected={sorted(actual_turn_keys - expected_turn_keys)}"
            )
    return errors


def save_fixture(result: ScenarioResult) -> Path:
    """Atomically write a validated fixture to its fixed repository location."""
    path = _fixture_path(result.scenario_id)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink fixture: {path}")

    payload = result_to_dict(result)
    validation_errors = validate_fixture(
        payload,
        expected_scenario_id=result.scenario_id,
    )
    if validation_errors:
        raise ValueError("Invalid generated fixture: " + "; ".join(validation_errors))

    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        dir=GOLDEN_DIR,
        prefix=f".{result.scenario_id}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def load_fixture(scenario_id: str) -> dict[str, Any]:
    """Read a fixture from its fixed repository location."""
    return json.loads(_fixture_path(scenario_id).read_text(encoding="utf-8"))


def format_fixture_diff(actual: ScenarioResult, expected: dict[str, Any]) -> str:
    """Return a reviewable unified diff for an intentional regeneration."""
    expected_text = json.dumps(expected, indent=2, ensure_ascii=False, sort_keys=True)
    actual_text = json.dumps(
        result_to_dict(actual),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    return "\n".join(
        difflib.unified_diff(
            expected_text.splitlines(),
            actual_text.splitlines(),
            fromfile="committed fixture",
            tofile="generated fixture",
            lineterm="",
        )
    )


def compare_results(
    actual: ScenarioResult,
    expected: dict[str, Any],
) -> list[str]:
    """Compare exact fixture and result schemas, then compare every value."""
    diffs = validate_fixture(expected, expected_scenario_id=actual.scenario_id)
    if diffs:
        return diffs

    actual_dict = result_to_dict(actual)
    actual_turns = actual_dict["turns"]
    expected_turns = expected["turns"]
    if len(actual_turns) != len(expected_turns):
        return [
            f"turn count: expected {len(expected_turns)}, got {len(actual_turns)}"
        ]

    for index, (actual_turn, expected_turn) in enumerate(
        zip(actual_turns, expected_turns, strict=True)
    ):
        for key in sorted(actual_turn):
            if actual_turn[key] != expected_turn[key]:
                diffs.append(
                    f"turn {index}.{key}: "
                    f"expected {json.dumps(expected_turn[key], ensure_ascii=False)!r}, "
                    f"got {json.dumps(actual_turn[key], ensure_ascii=False)!r}"
                )
    return diffs
