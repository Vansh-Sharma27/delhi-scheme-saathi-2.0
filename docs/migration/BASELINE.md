# Phase 0 Baseline — delhi-scheme-saathi-2.0

Recorded on `arch/phase-0-safety-net`, cut from `main` at commit `e82c0a1`.
The auditable, repository-local acceptance requirements are in
[`SAFETY_NET.md`](SAFETY_NET.md).

The remote tag `baseline/v1` points to import commit `98a8d6a`. A normal clone
may not have that tag locally until it is fetched:

```bash
git ls-remote --tags origin refs/tags/baseline/v1
git fetch origin tag baseline/v1
git rev-parse --verify baseline/v1^{commit}
```

## 1. Original measurements

These are historical measurements from the branch point, not promises about an
arbitrary resolver result.

| Check | Command | Historical result |
| --- | --- | --- |
| Tests | `pytest -q` | 275 passed, 1 dependency warning |
| Lint | `ruff check .` | clean |
| Types | `mypy src` | 66 errors in 19 files |

### Historical mypy distribution

| File | Errors |
| --- | ---: |
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

The old CI gate compared only the total. It has been replaced by
`scripts/check_mypy_delta.py`, which runs the same pinned mypy against the base
and current revisions and rejects new `(path, code, message)` fingerprints.
The command fails closed if either mypy invocation fails or its diagnostics
cannot be parsed.

## 2. Reproducible environment

The merge gate uses Python **3.11.16**. Production direct dependencies are
exactly pinned in `requirements.lock`; local and CI development tools are
exactly pinned in `requirements-dev.txt`. `requirements.txt`, Docker, and CI
all consume the lock, while `scripts/check_dependency_sync.py` verifies that
`pyproject.toml` mirrors both canonical files.

Install and verify with:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/check_dependency_sync.py
pytest -q
ruff check .
lint-imports
python -m pip_audit --strict -r requirements.lock
```

Dependency changes are intentional repository changes: update the lock and
metadata together, run the complete gate, and review the dependency audit.

## 3. Executable bits

The following scripts are required to have mode `100755`; CI checks the mode:

- `scripts/rapid_redeploy.sh`
- `scripts/seed_local_db.sh`
- `scripts/set_telegram_webhook.py`
- `scripts/test_conversation_flow.py`
- `scripts/check_dependency_sync.py`
- `scripts/check_mypy_delta.py`

## 4. Conversation import boundary

The import-linter contract governs exactly these six modules, from highest to
lowest layer:

`service → views → turn_policy → intents → scheme_reference → language`

Higher layers may import lower layers; reverse imports fail. Because
`ignore_unimported_packages = true`, this contract does **not** constrain
imports between these modules and modules outside the six-layer set. ADR-0004
uses the same wording and scope.

## 5. Suspected live defects carried from the branch point

These were recorded as a separate production backlog; Phase 0 does not silently
claim to have resolved them:

| File | Historical location | Finding |
| --- | --- | --- |
| `src/webhook/handler.py` | 226, 267 | integer/string ID mismatches |
| `src/services/profile_extractor.py` | 152, 162, 175, 191 | string values assigned to integer targets |
| `src/db/office_repo.py` | 121 | integer appended to `list[str]` |
| `src/services/conversation/service.py` | 1018, 1032 | optional strings in non-optional paths |

Other known backlog items remain: incomplete eligibility coverage, last-write-
wins session updates, no Telegram update deduplication, dropped seed provenance,
storage selection coupled to an AI flag, and no database migration framework.

## 6. Benchmark scripts

The previously referenced local-only benchmark scripts are not present in this
repository. They remain outside the merge scope and must not be represented as
an auditable Phase 0 gate until they are retrieved, reviewed for credentials
and hard-coded endpoints, and committed intentionally.
