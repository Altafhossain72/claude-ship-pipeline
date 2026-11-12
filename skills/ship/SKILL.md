---
name: ship
description: Run the feature pipeline for a feature request — Full lane (PRD written or reviewed -> planner -> spec approval -> tester RED -> coder -> tester GREEN -> reviewer -> documenter) or Quick lane for small changes — across one or more repos, each run in its own git worktrees and run folder (parallel runs never block, the user's checkouts are never touched), handing off through run-folder files, writing developer docs (how it works, how to change and test it) with Mermaid diagrams and the OpenAPI spec from the final reviewed code, and finishing with a local commit on a feature branch for human review. Use when the user types /ship <feature> or asks to run the feature pipeline.
argument-hint: "[--quick|--full] [in <repo>[ and <repo>]:] [prd: <PRD file>] <feature request>"
disable-model-invocation: true
effort: medium
---

Run the feature pipeline for: $ARGUMENTS

If no feature request was given, ask for one and stop.

The session folder is where this session started: a workspace holding
several repos (e.g. `~/work`) or a repo. Every run has its
own run folder `<workspace>/.ship-runs/<slug>/` (called RUN below; every
`.pipeline/<file>` in this file means `RUN/<file>`) and its own git
worktree per repo, `<repo>-<slug>` next to the repo. So any number of
runs, in this or other sessions, go in parallel, and the user's own
checkouts and uncommitted work are never touched.

All bookkeeping goes through the helper, run from the session folder:
`python3 -I $HOME/.claude/hooks/ship.py --run <RUN> <command>` (written
`$SHIP` below; spell it out in every command, shell variables do not
persist; run it with no arguments for its usage). Exit code 3 means "ask
the user": show its message and stop.

Every subagent prompt starts with the line `SHIP_RUN=<RUN>` (absolute
path). The agents' guards and stop gates find the run from that line;
without it an agent can write nothing.

## 0. Pre-flight
1. Fresh session: if this conversation already holds earlier work, stop
   and tell the user: "Run /clear (or open a new session) and re-run
   /ship; continuing here multiplies token use." Continue only if they
   say so.
2. Branch name for the run: `<feat|fix>/<ticket>-<2-5 words saying what
   it does>`, ticket only if the request has one, e.g.
   `feat/adm-0049-transaction-limit-usage`. The same in every repo. The
   slug is the part after `feat/` or `fix/`.
3. `python3 -I $HOME/.claude/hooks/ship.py init <slug>` prints
   `RUN=<path>`; use that path for the whole run. Exit 3 means a run for
   this feature is already active: ask whether to resume it (use its
   RUN) or start over. `ship.py runs` lists the runs in this workspace;
   if it shows other runs still active from earlier days, mention them in
   one line (the user can end them with `--run <RUN> end`).
4. Repos: if the session folder is inside a git repo, or the request
   names repos ("in api: ..."), `$SHIP join <repo> <branch>` for each
   now (it creates or reuses the worktree `<repo>-<slug>`; a new branch
   starts from a freshly fetched `origin/dev`, else dev/main/master, never
   from whatever the user's checkout is on, and gets no upstream, so a
   stray push can't reach dev; add `--base <ref>` if the user names a
   base) and tell the planner to start there.
   Otherwise (workspace, nothing named) the planner finds the repos and
   they join at the spec gate; until then agents can write only in RUN.
   Show each join's output (worktree, HEAD, new constitution). A repo's
   constitution lives untracked in its main checkout (`<repo>/.ship/`,
   git-excluded) by design, shared by all its worktrees; never suggest
   committing it.
5. Lane, in one line to the user with the reason:
   - `--quick` / `--full` forces it; `--quick` with no repo joined: ask
     which repo. A request that comes with or matches a PRD is Full.
   - Otherwise Quick only for a small, well-defined change in one joined
     repo: about 3 files or fewer, no new endpoint, table/migration,
     config key or dependency, not touching auth, money, limits or
     customer data. If unsure, or no repo joined: Full.

## Orchestrator rules
- You coordinate; the subagents read. Never read source, diffs or test
  output yourself. From handoff files read only: the first ~20 lines
  (OPEN QUESTIONS / RESULT / VERDICT / RISK), the spec sections you show
  at the gate plus `## Risk` and `## Repos`, and the findings you show the
  user. Subagent prompts: the request, the mode, the handoff paths, any
  scope. Their definitions hold the rules.
- Never edit code, tests or handoff files yourself. Code fixes go
  through the `coder`, test fixes through the `tester` (RED-fix). You
  only run `$SHIP`, write the Quick-lane spec, run the final check,
  append the user's PRD decisions, and append lessons.
- Revise the spec by resuming the same `planner` (SendMessage), not a new
  one. Investigation goes to the `investigator`.
- Agents are fenced by hooks: a guard (read-only git, no remote access,
  publishing, installs or prod profiles, writes only in the run's repos)
  and a stop gate (no finishing without the handoff file, and size limits
  on the PRD, review and spec). If an agent still ends without its file
  (turn limit), resume it once with SendMessage: "Write RUN/<file> now
  from what you have already read; mark gaps UNVERIFIED." If it is still
  missing, stop and tell the user.
- After every `coder` and every GREEN `tester` run: `$SHIP redcheck`
  (exit 3: RED tests were changed; stop).
- Fix rounds are scoped: the GREEN `tester` tests only the touched files
  plus one full run; the `reviewer` checks only the listed findings and
  the files changed since its previous review.

## Full lane
Run subagents in the foreground, one at a time.
0. **Requirements (PRD).** Find the PRD: a path in the request (`prd:`),
   else `$SHIP prd-find <ticket or feature words>` (PRD files in the
   workspace, named with the user's prefix from `~/.claude/ship.json`).
   Say which in one line; if two could match, ask. For a `.docx`, run `$SHIP prd-text
   "<file>"` and give the analyst both paths.
   - **No PRD:** `analyst` in write mode (give it the request and any
     named repos). Wait for `.pipeline/prd.md`. PRD gate: show the
     problem/goal, the FR list (ids and titles), non-goals and open
     questions; wait for approval. Answers and feedback go to the same
     analyst (SendMessage); repeat. On approval:
     `$SHIP prd-save "<Feature Name>"`; that saved file is the PRD. Do not
     run a second analyst to "validate" a PRD the analyst just wrote; it
     self-checks, and the user's review here is the check. Exit
     3 means a PRD with that name exists: ask the user (another name, or
     `--replace` / `--replace-any` only if they explicitly say so).
   - **PRD exists:** `analyst` in review mode with its path. Wait for
     `.pipeline/prd-review.md`, then `$SHIP review-save "<PRD path>"`.
     `PRD: READY` with no decisions needed: continue, one line to the
     user. Otherwise show the BLOCKER/MAJOR findings and the decisions
     needed (with the analyst's recommendations) and stop. Append the
     user's answers under `## Decisions (<date>)` in the saved
     validation file. If there were BLOCKERs, send the answers to the
     same analyst for a delta re-review (then `$SHIP review-save` again);
     otherwise go on to planning. Never overwrite the existing PRD unless
     the user explicitly says so (`$SHIP prd-save ... --replace-any`,
     which keeps the old version as `.bak`); a client-authored PRD stays
     as it is and the decisions file records the deviations.
   The planner, reviewer and documenter get the PRD path and, if any,
   the validation file path.
1. **Plan.** `planner` with the request, the PRD (+ validation) paths
   and any named repos; tell it to start from the PRD's VERIFIED
   `path:line` map instead of re-surveying. Wait for `.pipeline/spec.md`.
2. **Spec gate.** OPEN QUESTIONS not "none": show them, stop; send the
   answers to the same planner, repeat. Else show `## Files`,
   `## Success criteria`, `## Out of scope`, `## Risk`, `## Repos`
   (call out repos marked `(not named by user)` and variant/worktree
   copies such as `api-feature-x`) and the branch name; wait for approval.
   Feedback goes to the same planner; repeat. On approval,
   `$SHIP join <repo> <branch>` each repo not yet joined.
3. **RED.** `tester` in RED mode. Wait for `RESULT: RED`, then
   `$SHIP redsum`. Mention any test that already passes.
4. **Build.** `coder` (with `model: opus` if `## Risk` is not `none`).
   Then `$SHIP redcheck`. If changes.md has `## Needs other repos`: Full
   lane sends it to the same planner and repeats the gate; Quick lane
   recommends `--full` (or joins the repo if the user agrees). If it has
   `## Test disputes`: show, stop; if the user agrees a test is wrong,
   `tester` RED-fix mode, `$SHIP redsum`, repeat this step.
5. **GREEN.** `tester` in GREEN mode; on `RESULT: PASS`, `$SHIP save
   green`. On `RESULT: FAIL`: `investigator`
   (task: diagnose), show `.pipeline/diagnosis.md`'s summary, stop. On
   approval a code fix goes to the `coder` (then step 5, scoped); a wrong
   test to RED-fix (then step 4).
6. **Review N** (N = 1, 2, ...). `$SHIP changed <base for N=1, else
   review<N-1>> > RUN/changed.txt`, `$SHIP save review<N>`, then
   `reviewer` (tell it the label for N>1). On `NEEDS WORK`:
   `investigator` (task: triage), show `.pipeline/review-triage.md`'s
   summary, stop; on approval valid findings go to the `coder`, then
   steps 5-6 scoped. `BLOCK` always stops.
7. **Docs** (only after `VERDICT: SHIP`). `$SHIP changed base >
   RUN/changed.txt`, `$SHIP save predocs`, then `documenter` (its
   definition lists the OpenAPI, feature doc and diagram outputs). Wait
   for `.pipeline/docs.md`. `$SHIP changed predocs --non-docs` must print
   nothing; restore each listed file with `git -C <repo> restore
   --source=$(cat RUN/snap/predocs.<worktree-folder>.tree) --worktree --
   <path>` (delete it if it is new) and tell the user. If an endpoint
   changed but the OpenAPI spec did not, send it back once.
   Docs must match the final code. If code or tests must change after
   this step (a failed final check, or a change the user asks for), the
   change goes `coder` -> step 5 -> step 6 (scoped), then
   `$SHIP changed predocs --non-docs > RUN/changed.txt`,
   `$SHIP save predocs2`, and the `documenter` again scoped to those
   files; its non-docs check is against `predocs2`. Then Finish.

## Quick lane
No PRD stage: Quick is for small changes that do not need one.
1. Write `.pipeline/spec.md` yourself: `## OPEN QUESTIONS` none;
   `## Request` verbatim; `## Files` and `## Reference files` "not
   planned; locate with Grep"; `## Interfaces` "existing code; locate
   with Grep"; `## Edge cases`; `## Success criteria` SC1.. (1-3 lines
   each); `## Out of scope` everything not in the request; `## Risk`
   none; `## Repos` the joined repo; `## Build and test` "tester to
   determine". Show the success criteria in one line; no gate.
2. Full-lane steps 3-6, with the `reviewer` invoked as `model: sonnet`.
   If its `RISK:` line is not `none`, stop and suggest `--full`.
3. Docs: `documenter` in `light` mode after `VERDICT: SHIP` (same
   `predocs` snapshot and check as Full-lane step 7).

## Finish
1. Show the verdict, the coverage table and the findings.
2. On `VERDICT: SHIP`: if `$SHIP changed green --non-docs` prints
   anything, re-run the build and test commands from
   `.pipeline/test-results.md` (trimmed `2>&1 | tail -40`); if they
   fail, do not commit; take the late-change path in step 7. (Nothing
   printed: the tested code is unchanged; skip the re-run.) Then `$SHIP commitset` and show the list (exit 3: the
   run touched files that held the user's own edits; ask). Then
   `$SHIP commit "<type>: <summary>"` (commits exactly that set per repo
   on its feature branch; never pushes). Do NOT push, merge, open a PR or
   deploy.
3. On `NEEDS WORK` / `BLOCK` the user does not continue: no commit; list
   what has to be fixed.
4. Lessons: for each finding confirmed valid and fixed, append one dated,
   general rule (no customer data, ids or credentials) to `## Lessons from
   past runs` in the `.ship/constitution.md` of the repo that owns the
   file. Past ~30 lessons, tell the user to promote recurring ones to
   `## Rules`.
5. When the run ends (committed, or the user stops it): `$SHIP end`.
   Keep it active while waiting for the user mid-run. The worktrees stay
   for the user's review; mention that `git worktree remove <path>`
   cleans one up after the branch is pushed or merged.
6. End with: lane, the PRD (written / reviewed, path), each repo's
   worktree, branch and commit, docs updated, and the RUN path.
