---
name: ship
description: Run the 5-stage feature pipeline (planner -> coder -> tester -> reviewer -> documenter subagents) for a feature request, updating the OpenAPI spec, feature docs and Mermaid diagrams under docs/, handing off through .pipeline/ files, and finish with a local commit on a feature branch for human review. Use when the user types /ship <feature> or asks to run the feature pipeline.
argument-hint: <feature request>
disable-model-invocation: true
---

Run the full feature pipeline for: $ARGUMENTS

If no feature request was given, ask for one and stop.

## 0. Pre-flight
- Confirm the working directory is a git repo. If not, stop and say so.
- Protected branches: `main`, `master`, `dev`, `develop`, `release/*`,
  `prod*`, `stage*`. The pipeline works on a feature branch ONLY.
  - If the current branch is a feature branch (`feat/*`, `feature/*`,
    `fix/*`, or any non-protected branch), use it as is.
  - If the current branch is protected, create and switch to
    `feat/<short-slug>` from the current HEAD. Never write to the protected
    branch itself.
- Unless the user explicitly asks in this request, never: commit to, merge
  into, rebase onto, reset, push, or check out a protected branch, and never
  pull/fetch-and-merge from one. Remember the feature branch name; it must
  not change for the rest of the run.
- Note any pre-existing uncommitted changes and tell the user; do not
  include them in the pipeline commit.
- Reset the handoff folder: `rm -rf .pipeline && mkdir .pipeline`, and make
  sure `.pipeline/` is listed in `.git/info/exclude` so it is never committed.

## Stages
Execute in order. Do not skip ahead. After each stage, confirm the handoff
file exists before starting the next. Run the subagents in the foreground,
one at a time.

1. Delegate to the `planner` subagent with the feature request above.
   Wait for `.pipeline/spec.md`.
2. If the spec's OPEN QUESTIONS are not "none", stop and show them to the
   user. Otherwise delegate to the `coder` subagent. Wait for
   `.pipeline/changes.md`.
3. Delegate to the `tester` subagent. Wait for `.pipeline/test-results.md`.
   If it says `RESULT: FAIL`, stop and show the failures.
4. Delegate to the `reviewer` subagent. Wait for `.pipeline/review.md`.
5. Only if `.pipeline/review.md` says `VERDICT: SHIP`, delegate to the
   `documenter` subagent. It must produce, under `docs/`:
   - the OpenAPI spec (`docs/openapi/...yaml`, or the repo's existing spec
     file) updated for every added/changed endpoint;
   - the "how it works" doc `docs/features/<feature-slug>.md` (created, or
     updated if the feature already has one);
   - Mermaid diagrams `docs/diagrams/<feature-slug>.md` (sequence + flow/
     state), created or updated;
   - updates to any other doc this change made stale.
   Before delegating, save the list of changed and untracked files
   (`git status --porcelain`) to `.pipeline/pre-docs.txt`.
   Wait for `.pipeline/docs.md`. Then compare `git status --porcelain` with
   that snapshot: any newly changed file outside `docs/`, `README*` and
   `CHANGELOG*` must be reverted, and the user told. Never revert files
   that were already in the snapshot. If an endpoint was added/changed but
   the OpenAPI spec was not updated, send it back to the documenter once.

## Finish
- Show the verdict and the findings from `.pipeline/review.md`.
- If `VERDICT: SHIP`, first confirm `git branch --show-current` is still
  the feature branch from pre-flight (stop if not), then commit the
  pipeline's changes locally on that feature branch (only the files listed
  in changes.md, the new tests, and the doc files listed in docs.md).
  Do NOT push, merge, open a PR, or deploy — leave it for the user's review.
- If `NEEDS WORK` or `BLOCK`, do not commit; leave the working tree as is
  and list what has to be fixed.
- End with: branch name, commit hash (if any), the docs created/updated
  (OpenAPI spec, feature doc, diagrams), and the paths of the handoff files.
