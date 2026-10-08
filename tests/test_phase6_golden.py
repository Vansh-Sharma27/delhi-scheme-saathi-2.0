"""Canonical constructor graph matches immutable pre-Phase-6 transcript bytes."""

import json
import subprocess
from pathlib import Path

import pytest

from tests.golden.harness import result_to_dict
from tests.golden.runtime import run_scenario
from tests.golden.scenarios import ALL_SCENARIOS


@pytest.mark.parametrize("scenario_id,user_id,turns", ALL_SCENARIOS, ids=[s[0] for s in ALL_SCENARIOS])
async def test_canonical_graph_golden_bytes(scenario_id, user_id, turns) -> None:
    result = await run_scenario(scenario_id, user_id, turns)
    actual = (json.dumps(result_to_dict(result), indent=2, ensure_ascii=False) + "\n").encode()
    expected = subprocess.check_output(
        ["git", "show", f"d8148ee:tests/golden/fixtures/{scenario_id}.json"],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert actual == expected, scenario_id
