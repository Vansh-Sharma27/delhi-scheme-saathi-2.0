# Phase 0 Safety-Net Requirements

This repository-tracked document is the authoritative acceptance specification
for Phase 0. Earlier commits referenced private/untracked files named
`ARCHITECTURE_MIGRATION_SPEC.md` and `ARCHITECTURE_MIGRATION_SPEC_v3.md`; those
files are not required to audit or run the controls below.

## Acceptance requirements

1. **Reproducible environment**
   - CI runs Python 3.11.16.
   - `requirements.lock` pins every direct production dependency.
   - `requirements-dev.txt` is the canonical CI/local development install.
   - `scripts/check_dependency_sync.py` prevents `pyproject.toml` drift.
2. **Behavioral corpus**
   - Fourteen synthetic scenarios cover English, Hindi, Hinglish, commands,
     callbacks, selection, all scheme views, no-match, clarification, empathy,
     topic reset, deterministic overrides, embedding failure, a real LLM
     deadline, and API/Telegram key separation.
   - Scenario-specific semantic assertions are code, not regeneratable JSON, so
     fixture regeneration cannot bless a broken route.
3. **Exact fixtures**
   - Every `ChatResponse` field and every persisted `Session` field is recorded.
   - Fixture key sets are exact; removed or unexpected keys fail.
   - All three clocks used by session creation, mutation, and storage are frozen.
4. **Controlled regeneration**
   - Regeneration is refused when `CI` is true.
   - Local regeneration requires both `--golden-regenerate` and
     `GOLDEN_REGENERATE_APPROVED=1`.
   - A unified diff is printed, generated data is validated, writes are atomic,
     and the newly written fixture is compared immediately.
   - Fixture output is fixed under `tests/golden/fixtures`; callers cannot pass
     arbitrary paths and symlink targets are rejected.
5. **Static architecture gate**
   - Import-linter enforces the explicit six-module conversation layer order in
     ADR-0004. The contract intentionally does not constrain imports to modules
     outside those six named layers.
6. **Type-regression gate**
   - CI runs mypy on the PR base and current revision with the same toolchain.
   - It fails closed on invocation or output-parse errors.
   - It compares a multiset of `(path, error code, message)` fingerprints and
     rejects additions; total-count compensation cannot hide a regression.
7. **Dependency security**
   - CI runs `pip-audit --strict` against `requirements.lock`.
8. **Repository invariants**
   - The complete unit/golden suite, Ruff, import-linter, dependency-sync check,
     executable-bit check, mypy delta check, and dependency audit must pass.

## Scenario claims that must remain explicit

| Scenario | Non-regeneratable assertion |
| --- | --- |
| 4 | Empty-message `lang:hi` callback executes, locks Hindi, and re-renders context |
| 5 | Two candidates; ordinal `2`, back-to-list, then name selection resolve without LLM IDs |
| 6 | Details → documents → rejection warnings → application help → list |
| 8 | A non-low-context ambiguous rematch enters `SITUATION_UNDERSTANDING` |
| 9 | `DEATH_IN_FAMILY` comes from deterministic wording, not the LLM fixture |
| 12 | Embedding failure is user-visible resilience; focused tests own repository ordering |
| 13 | The coroutine is cancelled by a real deadline and telemetry records `timeout` |
| 14 | HTTP route coverage and persisted keyspace checks prove API/Telegram isolation |

## Restore point

The remote tag `baseline/v1` points to import commit `98a8d6a`. A local clone
has the tag only after tags are fetched, for example:

```bash
git fetch origin tag baseline/v1
git rev-parse --verify baseline/v1^{commit}
```
