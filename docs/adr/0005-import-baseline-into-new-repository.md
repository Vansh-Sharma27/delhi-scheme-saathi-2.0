# ADR-0005: Import the hackathon baseline into a new repository rather than carrying its history

**Date**: 2026-08-09
**Status**: accepted
**Deciders**: Vansh Sharma

Recorded alongside the change. The import shipped as commit `98a8d6a`, tagged
`baseline/v1`; the identity edits followed in `9dc5fb7`.

## Context

This codebase was written for a hackathon and accumulated 35 commits in
`Vansh-Sharma27/delhi-scheme-saathi` before the semester began. It has now been
approved as a mini project, and the college's project workspace has been
registered against a different URL, `Vansh-Sharma27/delhi-scheme-saathi-2.0`,
with the submission locked.

Neither the faculty reviewer nor the automated project-management system can
separate pre-semester commits from semester work inside a single history. The
semester's deliverable is the architectural migration described in
`ARCHITECTURE_MIGRATION_SPEC.md`, and that work has to be legible as the
repository's own history rather than as a layer on top of an unrelated 35-commit
base. The starting point is 57 source files, 12,877 lines, 275 passing tests, a
clean `ruff` run and 66 `mypy` errors — a state that must be preserved exactly,
because the migration is defined as behaviour-preserving and measured against it.

## Decision

Import the hackathon working tree into the new repository as a single unmodified
baseline commit, tagged `baseline/v1`, and carry out all migration work there on
`arch/*` branches merged into `main` with `--no-ff`. The original repository is
archived read-only and remains public as provenance, referenced from the import
commit message and the README.

## Alternatives Considered

### Alternative 1: Push the original repository's full history into the new remote
- **Pros**: perfect continuity; `git blame` and `git bisect` reach back through the hackathon period; nothing has to be explained.
- **Cons**: the graded repository would open with 35 commits that predate the semester and were not part of the approved work.
- **Why not**: this is the exact condition the new repository exists to avoid. An automated tracker counting commits or contributions would attribute pre-semester work to the semester, which misrepresents the submission regardless of intent.

### Alternative 2: Continue working in the original repository, copy the finished result across as one commit at the end
- **Pros**: no disruption to the existing setup; the migration keeps its full granular history where the work actually happens.
- **Cons**: the graded repository would contain a single commit of roughly 16,000 lines, authored on one day by one person.
- **Why not**: it destroys precisely the evidence the semester is assessed on. Per-author attribution for a three-person team collapses; the phase gates, review points and revert boundaries that the migration plan is built around would all live in a repository nobody grades; CI would run for the first time at submission. There is also no hybrid available — `git push` requires full ancestry, so the new remote cannot receive only the post-baseline commits without rewriting history. One repository has to be chosen.

### Alternative 3: Seed the new repository from `git clone`, `git archive`, or GitHub's "Download ZIP"
- **Pros**: one command; no dependence on the state of any particular machine.
- **Cons**: all three reproduce the committed tree only, silently omitting anything gitignored but locally present.
- **Why not**: this project has been bitten by HEAD-only snapshots repeatedly, and `.gitignore` excludes real working files including the benchmark harness and `.claude/`. A working-tree copy was used instead, with fidelity proven by comparing `git ls-files -s` between source and target rather than assumed.

## Consequences

### Positive
- Every commit in the graded repository after `98a8d6a` is semester work, with real per-author attribution for all three team members.
- `baseline/v1` is an immutable anchor for golden-master comparison, usable as a second working tree (`git worktree add ../dss-baseline baseline/v1`) throughout the migration.
- The hackathon repository survives unmodified and publicly linked, so provenance is disclosed rather than obscured.
- CI, import-linter contracts and the golden corpus can be established from Phase 0, before any structural change lands.

### Negative
- `git log` in the new repository stops at the import. Blame and bisect across the hackathon period require the archived repository.
- Two repositories now have to be explained to anyone reading the project cold, which is what this record is for.
- The 35 original commits no longer appear in the contribution graph of the repository being assessed.

### Risks
- A squash merge would collapse a phase branch into one commit and undo the reason this repository exists. Mitigation: squash merging is disabled at the repository level and phases merge with `--no-ff`.
- `baseline/v1` losing its meaning if moved or deleted. Mitigation: tag protection on `baseline/*`, and the tag deliberately points at the import commit rather than at any later `main`.
- Import fidelity resting on a claim rather than a check. Mitigation: the gate compares git index entries, which cover both blob hashes and file modes; it is reproducible at any time against the archived repository.
- File modes not surviving a Windows working-tree copy. Four executable scripts arrived as `100644` and were repaired with `git update-index --chmod=+x` before the import commit. Mitigation: CI runs on Linux and should assert the expected `100755` count so the drift cannot return unnoticed.
