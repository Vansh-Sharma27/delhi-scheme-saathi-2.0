"""Golden-master tests — the behavioural safety net for the migration.

Each scenario drives ConversationService.handle_message with all external
non-determinism stubbed, records the full transcript, and compares against
committed fixtures under tests/golden/fixtures/.

To regenerate fixtures (only with maintainer approval, spec 13.4):
    pytest tests/test_golden_master.py --golden-regenerate

Spec reference: ARCHITECTURE_MIGRATION_SPEC_v3.md Section 5.2-5.6.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from src.db.session_store import InMemorySessionStore, configure_session_store
from src.integrations.llm_client import get_llm_client
from src.main import CHAT_SESSION_PREFIX
from tests.golden.harness import (
    GOLDEN_DIR,
    compare_results,
    load_fixture,
    run_scenario,
    save_fixture,
)
from tests.golden.scenarios import ALL_SCENARIOS


@pytest.fixture(autouse=True)
def _fresh_session_store() -> Generator[None, None, None]:
    configure_session_store(InMemorySessionStore())
    yield


@pytest.fixture(autouse=True)
def _clean_llm_overrides() -> Generator[None, None, None]:
    """Clear instance-level overrides on the LLM client singleton.

    The golden harness sets analyze_message and judge_scheme_relevance on
    the global FallbackLLMClient singleton via the test-only override
    machinery (spec 7.6). Without cleanup, overrides leak across scenarios.
    """
    client = get_llm_client()
    saved = dict(client.__dict__)
    yield
    client.__dict__.clear()
    client.__dict__.update(saved)


@pytest.mark.asyncio
async def test_telegram_keyspace_assertion() -> None:
    """Scenario 14: an /api/chat user_id with a numeric Telegram ID must be
    namespaced under api: and must not address a bare Telegram session.

    This pins ADR-0001 through the migration (spec 5.4 item 14, 10.2).
    """
    telegram_user_id = "780045592"
    namespaced = f"{CHAT_SESSION_PREFIX}{telegram_user_id}"
    assert namespaced == f"api:{telegram_user_id}"
    assert namespaced != telegram_user_id

    # The harness uses the namespaced id internally. Run a scenario and
    # confirm the session is stored under the prefixed key.
    configure_session_store(InMemorySessionStore())
    await run_scenario(
        "s14_keyspace_check",
        user_id=namespaced,
        turns=ALL_SCENARIOS[13][2],
    )
    from src.db.session_store import get_session_store

    store = get_session_store()
    session = await store.get(namespaced)
    assert session is not None
    assert session.user_id == namespaced

    # A bare Telegram ID must not find a session.
    bare = await store.get(telegram_user_id)
    assert bare is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario_id,user_id,turns",
    ALL_SCENARIOS,
    ids=[s[0] for s in ALL_SCENARIOS],
)
async def test_golden_scenario(
    scenario_id: str,
    user_id: str,
    turns: list,
    request: pytest.FixtureRequest,
) -> None:
    """Run one golden scenario and compare against the committed fixture."""
    fixture_path = GOLDEN_DIR / f"{scenario_id}.json"

    result = await run_scenario(scenario_id, user_id, turns)

    if request.config.getoption("--golden-regenerate"):
        save_fixture(result, fixture_path)
        pytest.skip(f"Regenerated fixture for {scenario_id}")
        return

    if not fixture_path.exists():
        pytest.fail(
            f"Golden fixture missing: {fixture_path}. "
            f"Run with --golden-regenerate to create it."
        )

    expected = load_fixture(scenario_id, fixture_path)
    diffs = compare_results(result, expected)
    if diffs:
        details = "\n".join(f"  - {d}" for d in diffs[:20])
        pytest.fail(
            f"Golden transcript drift in {scenario_id}:\n{details}"
        )
