# Phase 0 Baseline — delhi-scheme-saathi-2.0

Recorded on `arch/phase-0-safety-net`, cut from `main` at commit `e82c0a1`.
The tag `baseline/v1` points at `98a8d6a`, the import commit. These figures
reproduce the spec's Section 5.1 measurements and confirm the environment
matches.

## 1. Prerequisites (spec 3.2, 3.3)

- **Clean tree:** `git status --porcelain` is empty at the branch point.
  Prerequisite A (clean tree before branching) is satisfied.
- **Restore point:** `baseline/v1` is present locally and points at `98a8d6a`.
  Prerequisite B (off-machine copy) requires the tag on the remote, confirmed
  before Phase 1. The agent does not push; pushing requires explicit consent
  (spec 13.6).
- **`.env` absent.** No `.env` file exists in the working tree. All settings
  fall back to defaults in `src/config.py`. The required keys
  (`DATABASE_URL`, `XAI_API_KEY`, `VOYAGE_API_KEY`, `TELEGRAM_BOT_TOKEN`)
  are absent. This is expected for a unit-test-only environment; the test
  suite stubs all external providers.

## 2. Test suite

| Check | Command | Result |
| --- | --- | --- |
| Tests | `pytest -q` | **275 passed**, 1 warning, 2.26s |
| Lint | `ruff check .` | **All checks passed** |
| Types | `mypy src` | **66 errors in 19 files** (57 source files checked) |

These reproduce spec 5.1 exactly. The single pytest warning is a
`StarletteDeprecationWarning` from `fastapi.testclient` about `httpx`,
originating in a dependency, not in project code.

### mypy error distribution

| File | Errors |
| --- | --- |
| `src/webhook/handler.py` | 16 |
| `src/integrations/llm_client.py` | 12 |
| `src/integrations/grok_client.py` | 6 |
| `src/services/profile_extractor.py` | 5 |
| `src/models/api.py` | 4 |
| `src/integrations/bedrock_client.py` | 4 |
| `src/db/session_store.py` | 3 |
| `src/utils/validators.py` | 2 |
| `src/services/conversation/service.py` | 2 |
| `src/integrations/sarvam.py` | 2 |
| `src/integrations/embedding_client.py` | 2 |
| `src/services/life_event_classifier.py` | 1 |
| `src/services/fsm.py` | 1 |
| `src/services/ai_background.py` | 1 |
| `src/integrations/telegram.py` | 1 |
| `src/integrations/jina_client.py` | 1 |
| `src/integrations/bhashini.py` | 1 |
| `src/db/office_repo.py` | 1 |
| `src/main.py` | 1 |

Total: 66. The gate is the total, not the per-file table. After each phase,
`mypy src` must report 66 or fewer. The count may fall as a structural side
effect; it must never rise, and no file is opened for the purpose of
lowering it.

## 3. Tool versions

The baseline was reproduced under Python 3.11.9 with the following tool
versions. These are pinned in the CI workflow (spec 5.5) so the ceiling
does not drift.

| Tool | Local version | CI pin |
| --- | --- | --- |
| Python | 3.11.9 | 3.11 |
| ruff | 0.16.2 | 0.16.3 |
| mypy | 2.3.0 | 2.3.1 |
| pytest | 9.1.1 | 9.1.1 |
| pytest-asyncio | 1.4.0 | 1.4.0 |

The local ruff and mypy versions differ from the CI pins by one patch
version. Both reproduce the 66-error and 275-passed counts exactly, so
the environment is compatible. The CI pins are authoritative; the local
versions are the closest available in this environment.

## 4. Dependency drift

`requirements.txt` and `pyproject.toml` specify the same production
dependencies with compatible lower bounds. Differences:

- `requirements.txt` caps `fastapi` at `<1.0.0`; `pyproject.toml` does not.
- `pyproject.toml` lists dev dependencies (pytest, ruff, mypy, pip-audit,
  types-boto3) under `[project.optional-dependencies] dev`; `requirements-dev.txt`
  mirrors these minus `pip-audit` and `types-boto3`, plus `types-boto3` is
  listed in `requirements-dev.txt` but not in `pyproject.toml`'s dev extras.
  Specifically: `requirements-dev.txt` includes `types-boto3>=1.0.0`;
  `pyproject.toml` dev extras do not.

Installed versions (resolved by pip from the lower bounds):

| Package | Specified | Installed |
| --- | --- | --- |
| fastapi | >=0.104.0 (req: <1.0.0) | 0.141.1 |
| openai | >=1.12.0 | 3.1.0 |
| pydantic | >=2.5.0 | 2.13.4 |
| python-telegram-bot | >=20.7 | 22.8 |
| boto3 | >=1.34.0 | 1.43.72 |
| asyncpg | >=0.29.0 | 0.31.0 |
| httpx | >=0.25.0 | 0.28.1 |

No drift causes a test failure or a lint/type count change. Reported, not
fixed (spec 5.1 item 5, rule 13.11).

## 5. Executable bits

Four scripts carry mode `100755` in the index (spec 3.1):

- `scripts/rapid_redeploy.sh`
- `scripts/seed_local_db.sh`
- `scripts/set_telegram_webhook.py`
- `scripts/test_conversation_flow.py`

A Windows working-tree operation drops these silently. CI asserts them
(spec 5.5).

## 6. Suspected live defects (post-migration work queue)

Recorded per spec 5.1 / 13.10. Not fixed during the migration.

| File | Line | Finding | Suspected runtime consequence |
| --- | --- | --- | --- |
| `src/webhook/handler.py` | 226 | Passes `int` where `str` expected (`_handle_voice_message` arg) | Possible type error in voice message handling path |
| `src/webhook/handler.py` | 267 | Passes `int` where `str` expected (`_send_response` arg) | Possible type error in response sending path |
| `src/services/profile_extractor.py` | 152, 162, 175, 191 | Assigns `str` into `int` targets | Profile fields may hold string values where integers are expected, affecting eligibility checks |
| `src/db/office_repo.py` | 121 | Appends `int` to `list[str]` | Office service list may contain mixed types |
| `src/services/conversation/service.py` | 1018 | Passes `str \| None` where `str` expected (`get_validation_re_prompt`) | Possible `None` passed to prompt loader when validation error path fires with no field |
| `src/services/conversation/service.py` | 1032 | Assigns `str \| None` into `str` variable | Response text could be `None` where string is expected |

These overlap with the known defects in spec Section 11 and are not
investigated further here. They form the post-migration work queue.

### Documentation defect: ADR-0004 layer order

ADR-0004 states the dependency order as `language → intents →
scheme_reference → turn_policy → views → service`, where "no module imports
anything later in the list." The actual code has `intents` importing
`scheme_reference` (`intents.py:15`), which contradicts the stated order
where `intents` precedes `scheme_reference`. The code is the source of
truth (spec rule: "the repository is the source of truth for behaviour").
The import-linter contract in `pyproject.toml` reflects the actual order:
`service → views → turn_policy → intents → scheme_reference → language`.
ADR-0004's prose should be corrected post-migration.

## 7. Known defects carried forward (spec Section 11)

Not fixed during the migration. The agent recognises them as known rather
than discovering them mid-refactor.

1. Benefit amount is a retrieval order, not only a ranking bonus (11.1).
2. Eligibility evaluation covers 4 of 18 criteria (11.2).
3. Session writes can lose updates — no `ConditionExpression`, no version
   field (11.3).
4. Telegram updates are not deduplicated — `update_id` never read (11.4).
5. Seeding discards source provenance — `last_verified` omitted from
   `INSERT` (11.5).
6. Storage backend selected by an LLM flag — `use_bedrock` coupling (11.6).
7. No schema migration system — only `scripts/init-db/01-schema.sql` (11.7).

## 8. Benchmark scripts status (spec 3.3.1)

Spec 3.3.1 requires settling the status of the gitignored benchmark
scripts (`scripts/benchmark.py`, `scripts/benchmark_text_live.py`,
`scripts/benchmark_voice.py`, `scripts/generate_pptx.py`) before Phase 0
closes. On this machine, `git ls-files --others --ignored --exclude-standard`
returns only `.claude/` — the benchmark scripts are absent. They exist on
a different machine and are not currently available for audit.

Status: pending. These scripts must be retrieved, read for credentials and
hardcoded endpoints, and their status settled before Phase 6 (spec 7.7).
They are not committed without instruction (spec 13.9).