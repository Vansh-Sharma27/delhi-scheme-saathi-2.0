"""Golden scenario definitions — the 14 minimum scenarios from spec 5.4.

Each scenario is a list of TurnSpec objects. The LLM analysis, judge, and
generation responses are fixed dicts/strings that simulate what a real LLM
would return. Scheme matching returns synthetic SchemeMatch objects.

Privacy: all fixtures are synthetic. No forked real sessions (spec 5.3).
"""

from __future__ import annotations

from typing import Any

from tests.golden.harness import (
    SCHEME_HOUSING,
    SCHEME_RENTAL,
    TurnSpec,
    _make_match,
)


def _analysis(
    *,
    intent: str = "question",
    action: str | None = None,
    life_event: str | None = None,
    extracted_fields: dict[str, Any] | None = None,
    language: str = "en",
    selected_scheme_id: str | None = None,
    response_text: str | None = None,
) -> dict[str, Any]:
    """Build a fixed LLM analysis payload."""
    return {
        "intent": intent,
        "action": action,
        "life_event": life_event,
        "extracted_fields": extracted_fields or {},
        "language": language,
        "selected_scheme_id": selected_scheme_id,
        "response_text": response_text,
    }


def _judge(
    *,
    should_clarify: bool = False,
    clarification_question: str | None = None,
    confidence: float = 0.9,
) -> dict[str, Any]:
    """Build a fixed LLM relevance-judge payload."""
    return {
        "should_clarify": should_clarify,
        "clarification_question": clarification_question,
        "overall_confidence": confidence,
        "candidate_scores": [],
    }


# --- Scenario 1: Cold start through housing, profile, matching, details (en) ---

SCENARIO_01_HOUSING_EN = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="I need help with housing",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    TurnSpec(
        message="I am 30 years old",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30},
        ),
    ),
    TurnSpec(
        message="My category is OBC",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"category": "OBC"},
        ),
    ),
    TurnSpec(
        message="My annual income is 200000",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"annual_income": 200000},
        ),
        match_result=[_make_match(SCHEME_HOUSING)],
    ),
    TurnSpec(
        message="1",
        llm_analysis=_analysis(
            selected_scheme_id="SCH-GOLD-001",
        ),
        scheme_for_details=SCHEME_HOUSING,
    ),
]


# --- Scenario 2: Same flow in Hindi ---

SCENARIO_02_HOUSING_HI = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over", language="hi"),
    ),
    TurnSpec(
        message="मुझे आवास सहायता चाहिए",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
            language="hi",
        ),
    ),
    TurnSpec(
        message="मेरी उम्र 30 साल है",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30},
            language="hi",
        ),
    ),
    TurnSpec(
        message="मेरी श्रेणी OBC है",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"category": "OBC"},
            language="hi",
        ),
    ),
    TurnSpec(
        message="मेरी वार्षिक आय 200000 है",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"annual_income": 200000},
            language="hi",
        ),
        match_result=[_make_match(SCHEME_HOUSING)],
    ),
    TurnSpec(
        message="1",
        llm_analysis=_analysis(
            selected_scheme_id="SCH-GOLD-001",
            language="hi",
        ),
        scheme_for_details=SCHEME_HOUSING,
    ),
]


# --- Scenario 3: Hinglish, including code-mixed message ---

SCENARIO_03_HINGLISH = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over", language="hinglish"),
    ),
    TurnSpec(
        message="mujhe housing help chahiye",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
            language="hinglish",
        ),
    ),
    TurnSpec(
        message="meri umar 30 saal hai",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30},
            language="hinglish",
        ),
    ),
    TurnSpec(
        message="category OBC hai mera",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"category": "OBC"},
            language="hinglish",
        ),
    ),
    TurnSpec(
        message="income 200000 hai approximately",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"annual_income": 200000},
            language="hinglish",
        ),
        match_result=[_make_match(SCHEME_HOUSING)],
    ),
]


# --- Scenario 4: /help and /language, including language-callback path ---
# The callback exercises _render_state_snapshot which re-renders the current
# context in the chosen language.

SCENARIO_04_HELP_LANGUAGE = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="/help",
        llm_analysis=_analysis(),
    ),
    TurnSpec(
        message="/language",
        llm_analysis=_analysis(),
    ),
    TurnSpec(
        message="",
        message_type="callback",
        callback_data="lang:hi",
        llm_analysis=_analysis(language="hi"),
    ),
]


# --- Scenario 5: Scheme selected by ordinal and by name ---
# After matching, the user selects by ordinal ("1"), views details, then
# goes back to the list and selects by name ("Delhi Housing Assistance").

SCENARIO_05_ORDINAL_AND_NAME = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="I need housing help",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    TurnSpec(
        message="Age 30, category OBC, income 200000",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30, "category": "OBC", "annual_income": 200000},
        ),
        match_result=[
            _make_match(SCHEME_HOUSING, score=0.9),
            _make_match(SCHEME_RENTAL, score=0.7),
        ],
    ),
    # Select the second result by ordinal. The LLM intentionally supplies no ID.
    TurnSpec(
        message="2",
        llm_analysis=_analysis(),
        scheme_for_details=SCHEME_RENTAL,
    ),
    # Go back to the persisted multi-scheme list.
    TurnSpec(
        message="other schemes",
        llm_analysis=_analysis(),
    ),
    # Select the first result by exact name, again without an LLM-supplied ID.
    TurnSpec(
        message="Delhi Housing Assistance",
        llm_analysis=_analysis(),
        scheme_for_details=SCHEME_HOUSING,
    ),
]


# --- Scenario 6: Navigation across all four per-scheme views and back ---
# The user views scheme details, then documents, rejection warnings,
# application help, and finally returns to the scheme list.

SCENARIO_06_VIEWS_NAVIGATION = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="Housing assistance needed",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    TurnSpec(
        message="30 years old, OBC, income 200000",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30, "category": "OBC", "annual_income": 200000},
        ),
        match_result=[_make_match(SCHEME_HOUSING)],
    ),
    # Open scheme details
    TurnSpec(
        message="1",
        llm_analysis=_analysis(
            selected_scheme_id="SCH-GOLD-001",
        ),
        scheme_for_details=SCHEME_HOUSING,
    ),
    # Navigate to document guidance
    TurnSpec(
        message="documents",
        llm_analysis=_analysis(),
        scheme_for_details=SCHEME_HOUSING,
    ),
    # Navigate to rejection warnings
    TurnSpec(
        message="rejection warnings",
        llm_analysis=_analysis(),
        scheme_for_details=SCHEME_HOUSING,
    ),
    # Navigate to application help
    TurnSpec(
        message="how to apply",
        llm_analysis=_analysis(),
        scheme_for_details=SCHEME_HOUSING,
    ),
    # Go back to the scheme list
    TurnSpec(
        message="other schemes",
        llm_analysis=_analysis(),
        scheme_for_details=SCHEME_HOUSING,
    ),
]


# --- Scenario 7: No-match outcome ---

SCENARIO_07_NO_MATCH = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="I need housing help",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    TurnSpec(
        message="Age 30, OBC, income 200000",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30, "category": "OBC", "annual_income": 200000},
        ),
        match_result=[],
    ),
]


# --- Scenario 8: Clarification outcome from the relevance judge ---
# The first match completes a low-context collection turn. A later, substantive
# profile update triggers a fresh match with no pending field, so clarification
# is not suppressed by the low-context guard.

SCENARIO_08_CLARIFICATION = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="I need housing help",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    TurnSpec(
        message="Age 30, OBC, income 200000",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30, "category": "OBC", "annual_income": 200000},
        ),
        match_result=[_make_match(SCHEME_HOUSING, score=0.9)],
    ),
    TurnSpec(
        message="I specifically need affordable housing; our annual income changed to 210000",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"annual_income": 210000},
        ),
        match_result=[
            _make_match(SCHEME_HOUSING, score=0.1),
            _make_match(SCHEME_RENTAL, score=0.1),
        ],
        llm_judge=_judge(
            should_clarify=True,
            clarification_question="Do you want housing schemes specifically?",
        ),
    ),
]


# --- Scenario 9: DEATH_IN_FAMILY first-detection turn (empathy prepend) ---
# The user mentions a death in the family. The deterministic life_event
# classifier detects DEATH_IN_FAMILY from keywords, and the service prepends
# an empathy message before the next question.

SCENARIO_09_DEATH_IN_FAMILY_EMPATHY = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="My husband passed away recently",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"marital_status": "widowed"},
        ),
    ),
]


# --- Scenario 10: Mid-conversation topic reset, and bye / start over ---
# The user starts with housing, then switches to education (topic reset),
# says goodbye, and starts over.

SCENARIO_10_TOPIC_RESET_BYE = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="I need housing help",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    # Topic switch: "actually I need ... instead" triggers explicit_topic_switch
    TurnSpec(
        message="Actually I need education loan help instead",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="EDUCATION",
        ),
    ),
    # Goodbye
    TurnSpec(
        message="bye",
        llm_analysis=_analysis(
            intent="goodbye",
            action="goodbye",
        ),
    ),
    # Start over
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
]


# --- Scenario 11: LLM analysis contradicts user's plain words; deterministic override wins ---
# The user says "start over" but the LLM says action="answer_field". The
# deterministic detect_action_override matches "start over" via _START_OVER_RE
# and overrides the LLM's action. This pins spec 10.1: the LLM proposes, the
# deterministic layers dispose.

SCENARIO_11_DETERMINISTIC_OVERRIDE = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="I need housing help",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    # LLM says "answer_field" but the user said "start over" — deterministic wins
    TurnSpec(
        message="start over",
        llm_analysis=_analysis(
            action="answer_field",
            response_text="What is your annual income?",
        ),
    ),
]


# --- Scenario 12: Embedding provider failure does not break conversation ---
# Focused matcher/repository tests verify dimensions, query_embedding=None,
# SQL parameters, and fallback ordering. This end-to-end scenario only pins
# the user-visible resilience contract.

SCENARIO_12_EMBEDDING_FAILURE = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="Housing help needed",
        llm_analysis=_analysis(
            action="answer_field",
            life_event="HOUSING",
        ),
    ),
    TurnSpec(
        message="30 years, OBC, income 200000",
        llm_analysis=_analysis(
            action="answer_field",
            extracted_fields={"age": 30, "category": "OBC", "annual_income": 200000},
        ),
        match_result=[_make_match(SCHEME_HOUSING)],
        embedding_failure=True,
    ),
]


# --- Scenario 13: Real deadline cancellation with safe-output payload ---
# The injected analysis coroutine sleeps past a 10 ms policy deadline. The
# fixture records both cancellation and ``error=timeout`` telemetry, so an
# ordinary empty analysis can no longer satisfy this scenario.

SCENARIO_13_LLM_TIMEOUT_SAFE_OUTPUT = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    # analyze_message timeout -> safe_analysis_payload shape
    TurnSpec(
        message="I need housing",
        llm_timeout=True,
    ),
]


# --- Scenario 14: Telegram keyspace assertion (ADR-0001) ---
# An /api/chat call with a numeric Telegram ID must never read or write
# that user's real session. The harness asserts the session key is prefixed.
# The actual keyspace assertion is in test_golden_master.py::test_telegram_keyspace_assertion.

SCENARIO_14_TELEGRAM_KEYSPACE = [
    TurnSpec(
        message="/start",
        llm_analysis=_analysis(action="start_over"),
    ),
    TurnSpec(
        message="Hello",
        llm_analysis=_analysis(),
    ),
]


ALL_SCENARIOS: list[tuple[str, str, list[TurnSpec]]] = [
    ("s01_housing_en", "golden-01", SCENARIO_01_HOUSING_EN),
    ("s02_housing_hi", "golden-02", SCENARIO_02_HOUSING_HI),
    ("s03_hinglish", "golden-03", SCENARIO_03_HINGLISH),
    ("s04_help_language", "golden-04", SCENARIO_04_HELP_LANGUAGE),
    ("s05_ordinal_name", "golden-05", SCENARIO_05_ORDINAL_AND_NAME),
    ("s06_views_navigation", "golden-06", SCENARIO_06_VIEWS_NAVIGATION),
    ("s07_no_match", "golden-07", SCENARIO_07_NO_MATCH),
    ("s08_clarification", "golden-08", SCENARIO_08_CLARIFICATION),
    ("s09_death_empathy", "golden-09", SCENARIO_09_DEATH_IN_FAMILY_EMPATHY),
    ("s10_topic_reset_bye", "golden-10", SCENARIO_10_TOPIC_RESET_BYE),
    ("s11_deterministic_override", "golden-11", SCENARIO_11_DETERMINISTIC_OVERRIDE),
    ("s12_embedding_failure", "golden-12", SCENARIO_12_EMBEDDING_FAILURE),
    ("s13_llm_timeout", "golden-13", SCENARIO_13_LLM_TIMEOUT_SAFE_OUTPUT),
    ("s14_telegram_keyspace", "golden-14", SCENARIO_14_TELEGRAM_KEYSPACE),
]
