"""Golden-master tests for the migration safety net.

Intentional regeneration is blocked in CI and requires an explicit maintainer
approval environment variable:

    GOLDEN_REGENERATE_APPROVED=1 \
      pytest tests/test_golden_master.py --golden-regenerate
"""

from __future__ import annotations

import copy

import pytest

from src.db.session_store import InMemorySessionStore
from src.main import CHAT_SESSION_PREFIX
from tests.golden.harness import (
    GOLDEN_DIR,
    ScenarioResult,
    TurnRecord,
    compare_results,
    format_fixture_diff,
    load_fixture,
    result_to_dict,
    run_scenario,
    save_fixture,
)
from tests.golden.scenarios import ALL_SCENARIOS


def _assert_scenario_contract(scenario_id: str, result: ScenarioResult) -> None:
    """Keep scenario claims independent from regeneratable JSON fixtures."""
    turns = result.turns

    if scenario_id == "s04_help_language":
        callback = turns[-1]
        assert callback.language == "hi"
        assert callback.session_language_preference == "hi"
        assert callback.session_language_locked is True
        assert "भाषा" in callback.response_text

    elif scenario_id == "s05_ordinal_name":
        assert len(turns[2].session_presented_schemes) == 2
        assert turns[3].next_state == "SCHEME_DETAILS"
        assert turns[3].session_selected_scheme_id == "SCH-GOLD-004"
        assert turns[4].next_state == "SCHEME_PRESENTATION"
        assert turns[5].next_state == "SCHEME_DETAILS"
        assert turns[5].session_selected_scheme_id == "SCH-GOLD-001"

    elif scenario_id == "s06_views_navigation":
        assert [turn.next_state for turn in turns[3:]] == [
            "SCHEME_DETAILS",
            "DOCUMENT_GUIDANCE",
            "REJECTION_WARNINGS",
            "APPLICATION_HELP",
            "SCHEME_PRESENTATION",
        ]
        assert turns[6].response_text

    elif scenario_id == "s08_clarification":
        clarification = turns[-1]
        assert clarification.next_state == "SITUATION_UNDERSTANDING"
        assert "housing schemes" in clarification.response_text.lower()

    elif scenario_id == "s09_death_empathy":
        assert turns[-1].session_profile["life_event"] == "DEATH_IN_FAMILY"

    elif scenario_id == "s12_embedding_failure":
        assert turns[-1].next_state == "SCHEME_PRESENTATION"
        assert turns[-1].schemes

    elif scenario_id == "s13_llm_timeout":
        timed_out = turns[-1]
        assert timed_out.llm_timeout_cancelled is True
        assert any(
            event["task_type"] == "analyze_message" and event["error"] == "timeout"
            for event in timed_out.ai_events
        )


@pytest.mark.asyncio
async def test_telegram_keyspace_assertion() -> None:
    """Scenario 14 stores API-prefixed and bare Telegram keys separately.

    The actual HTTP route binding and prefixing are covered by
    ``test_main.py::test_chat_route_binds_body_and_namespaces_over_http``.
    """
    telegram_user_id = "780045592"
    namespaced = f"{CHAT_SESSION_PREFIX}{telegram_user_id}"
    assert namespaced == f"api:{telegram_user_id}"
    assert namespaced != telegram_user_id

    store = InMemorySessionStore()
    await run_scenario(
        "s14_keyspace_check",
        user_id=namespaced,
        turns=ALL_SCENARIOS[13][2],
        session_store=store,
    )

    session = await store.get(namespaced)
    assert session is not None
    assert session.user_id == namespaced
    assert await store.get(telegram_user_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario_id,user_id,turns",
    ALL_SCENARIOS,
    ids=[scenario[0] for scenario in ALL_SCENARIOS],
)
async def test_golden_scenario(
    scenario_id: str,
    user_id: str,
    turns: list,
    request: pytest.FixtureRequest,
) -> None:
    """Run one scenario, check semantics, then compare the exact fixture."""
    fixture_path = GOLDEN_DIR / f"{scenario_id}.json"
    result = await run_scenario(scenario_id, user_id, turns)
    _assert_scenario_contract(scenario_id, result)

    if request.config.getoption("--golden-regenerate"):
        if fixture_path.exists():
            existing = load_fixture(scenario_id)
            fixture_diff = format_fixture_diff(result, existing)
            if fixture_diff:
                print(f"\nGolden fixture update for {scenario_id}:\n{fixture_diff}")
        save_fixture(result)
        regenerated = load_fixture(scenario_id)
        assert compare_results(result, regenerated) == []
        return

    if not fixture_path.exists():
        pytest.fail(
            f"Golden fixture missing: {fixture_path}. Use the documented, "
            "approval-gated regeneration command to create it."
        )

    expected = load_fixture(scenario_id)
    diffs = compare_results(result, expected)
    if diffs:
        details = "\n".join(f"  - {diff}" for diff in diffs[:20])
        pytest.fail(f"Golden transcript drift in {scenario_id}:\n{details}")


def _minimal_result() -> ScenarioResult:
    return ScenarioResult(
        scenario_id="strict_fixture",
        turns=[
            TurnRecord(
                response_text="ok",
                response_text_hindi=None,
                response_audio_url=None,
                response_documents=[],
                response_rejection_warnings=[],
                response_offices=[],
                next_state="GREETING",
                language="en",
                schemes=[],
                inline_keyboard=None,
            )
        ],
    )


def test_compare_results_rejects_removed_turn_key() -> None:
    """Deleting an assertion from JSON must fail rather than weaken the test."""
    actual = _minimal_result()
    fixture = result_to_dict(actual)
    del fixture["turns"][0]["response_text"]

    diffs = compare_results(actual, fixture)

    assert any("key mismatch" in diff and "response_text" in diff for diff in diffs)


def test_compare_results_rejects_unexpected_keys_and_empty_turns() -> None:
    actual = _minimal_result()
    unexpected = copy.deepcopy(result_to_dict(actual))
    unexpected["turns"][0]["not_part_of_schema"] = True
    assert any("unexpected" in diff for diff in compare_results(actual, unexpected))

    empty = {"scenario_id": actual.scenario_id, "turns": []}
    assert any("at least one turn" in diff for diff in compare_results(actual, empty))


def test_save_fixture_rejects_path_like_scenario_id() -> None:
    """Fixture writes cannot escape the committed fixtures directory."""
    result = _minimal_result()
    result.scenario_id = "../outside"

    with pytest.raises(ValueError, match="Invalid golden scenario id"):
        save_fixture(result)


@pytest.mark.asyncio
async def test_injected_store_keeps_two_users_isolated() -> None:
    """Two users sharing one store never read or overwrite each other's state."""
    store = InMemorySessionStore()
    await run_scenario(
        "isolation_a_start",
        "isolation-a",
        ALL_SCENARIOS[0][2][:2],
        session_store=store,
    )
    await run_scenario(
        "isolation_b_start",
        "isolation-b",
        ALL_SCENARIOS[1][2][:2],
        session_store=store,
    )

    session_a = await store.get("isolation-a")
    session_b = await store.get("isolation-b")
    assert session_a is not None and session_b is not None
    assert session_a.user_id != session_b.user_id
    assert session_a.messages != session_b.messages
    assert session_a.language_preference == "en"
    assert session_b.language_preference == "hi"
