#!/usr/bin/env bash
# Regression tests for the /ship hooks and helper. Builds throwaway git repos
# in a temp folder (removed at the end) and checks every allow/deny decision.
#   tests/hook-tests.sh            test the installed copy (~/.claude/hooks)
#   tests/hook-tests.sh ./hooks    test the copy in this repo
set -uo pipefail
HOOKS="$(cd "${1:-$HOME/.claude/hooks}" && pwd)"
G="$HOOKS/ship-tool-guard.py"; GATE="$HOOKS/ship-handoff-gate.py"; SHIP="$HOOKS/ship.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export SHIP_PRD_PREFIX="PRD - " GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
fail=0; n=0

# fixtures: a workspace with one run, one worktree, and agent transcripts
R="$T/ws/.ship-runs/f-one-two"; W="$T/ws/svc-f-one-two"
mkdir -p "$R/snap" "$W/mod/docs" "$T/ws/other"; git -C "$W" init -q
touch "$R/.active"; echo "$W" > "$R/repos.txt"
printf '{"type":"user","message":{"content":"SHIP_RUN=%s\\nMode: RED"}}\n' "$R" > "$T/tr-run.jsonl"
echo '{"type":"user","message":{"content":"no marker"}}' > "$T/tr-none.jsonl"

json() { python3 -I -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1"; }
bash_case() {  # want agent command
  n=$((n+1))
  printf '{"tool_name":"Bash","tool_input":{"command":%s},"cwd":"%s","agent_transcript_path":"%s"}' \
    "$(json "$3")" "$T/ws" "$T/tr-run.jsonl" | python3 -I "$G" "$2" >/dev/null 2>"$T/err"
  rc=$?; [ "$rc" = "$1" ] || { fail=1; echo "FAIL rc=$rc want=$1 [$2] $3 :: $(cat "$T/err")"; }
}
write_case() {  # want agent path [transcript]
  n=$((n+1))
  printf '{"tool_name":"Write","tool_input":{"file_path":%s},"cwd":"%s","agent_transcript_path":"%s"}' \
    "$(json "$3")" "$T/ws" "${4:-$T/tr-run.jsonl}" | python3 -I "$G" "$2" >/dev/null 2>"$T/err"
  rc=$?; [ "$rc" = "$1" ] || { fail=1; echo "FAIL rc=$rc want=$1 [$2] Write $3 :: $(cat "$T/err")"; }
}

# guard: must block
for c in "git push" "git add -A" "git fetch origin" "git -c alias.p=push p" "git stash" \
  "cd /x && git commit -m a" "bash -c 'git push'" "sshpass -p x ssh u@h" "rsync a h:/b" \
  "curl -s http://10.0.0.7:8080/x" "curl \$URL" "wget example.com/x" "mvn -q deploy" \
  "./gradlew publish" "npm install x" "npx x" "SPRING_PROFILES_ACTIVE=prod java -jar a.jar" \
  "mvn spring-boot:run -Dspring-boot.run.profiles=stage" "mvn -Pprod test" \
  "psql postgresql://u@10.0.0.9:5432/db" "PGHOST=10.0.0.1 psql db" "sed -i s/a/b/ /etc/hosts" \
  "echo x > /etc/foo" "cp a /home/nobody/x" "echo x | tee /var/tmp/y" "git diff --output=/x" \
  "rm -rf ~/Documents" "echo x > $R/repos.txt" "echo x > $R/red.sha" \
  "echo r >> $W/.ship/constitution.md" "python3 -I $SHIP --run $R commit x" \
  "echo t > $R/red-tests.txt"; do bash_case 2 coder "$c"; done
for c in "sed -i s/a/b/ $W/A.java" "cat > $W/A.java <<EOF" "python3 -c 'open(1)'" "rm $W/A.java"; do
  bash_case 2 reviewer "$c"; done
write_case 2 coder "$R/repos.txt"; write_case 2 coder "$R/.pipeline/changes.md"
write_case 2 coder "$T/ws/other/A.java"; write_case 2 coder "$W/.ship/constitution.md"
write_case 2 documenter "$W/src/A.java"; write_case 2 analyst "$T/ws/PRD - X.md"
write_case 2 planner "$W/src/A.java"; write_case 2 coder "$W/src/A.java" "$T/tr-none.jsonl"
n=$((n+1)); echo "notjson" | python3 -I "$G" coder 2>/dev/null; [ $? = 2 ] || { fail=1; echo "FAIL non-json input"; }
# guard: must allow
bash_case 0 tester "echo t > $R/red-tests.txt"
for c in "git -C $W status" "git -C $W diff -- src/branch/X.java" "git branch --show-current" \
  "grep -rn 'Map<String, List<Long>>' $W" "grep -n 'amount > 0' $W/A.java" \
  "curl -s localhost:8080/health | python3 -m json.tool" "curl -s http://127.0.0.1:18081/x" \
  "grep -rn ssh $W" "mvn -f $W/deploy/pom.xml test" "./gradlew test -Dspring.profiles.active=test" \
  "cd $W && mvn -q -o test -Dtest=FooTest 2>&1 | tail -60" "find . -name .git -prune -o -type f -print" \
  "psql -h localhost -c 'select 1'"; do bash_case 0 reviewer "$c"; done
for c in "cd $W && mkdir -p src/x && echo a > src/x/A.java" "sed -i 's/a > b/c/' $W/A.java" \
  "chmod 755 $W/run.sh" "cp $W/a $W/b" "echo notes > $R/notes.md"; do bash_case 0 coder "$c"; done
write_case 0 coder "$W/src/A.java"; write_case 0 coder "$R/changes.md"; write_case 0 tester "$R/red-tests.txt"
write_case 0 documenter "$W/mod/docs/x.md"; write_case 0 documenter "$W/mod/README.md"; write_case 0 analyst "$R/prd.md"

# gate
gate() {  # want agent [transcript]
  n=$((n+1))
  printf '{"agent_transcript_path":"%s","stop_hook_active":false}' "${3:-$T/tr-run.jsonl}" \
    | python3 -I "$GATE" "$2" >/dev/null 2>"$T/err"
  rc=$?; [ "$rc" = "$1" ] || { fail=1; echo "FAIL gate rc=$rc want=$1 [$2] :: $(cat "$T/err")"; }
}
gate 2 coder; echo "changes" > "$R/changes.md"; gate 0 coder
echo "foo" > "$R/test-results.md"; gate 2 tester; echo "RESULT: RED" > "$R/test-results.md"; gate 0 tester
(echo "# PRD"; seq 450) > "$R/prd.md"; gate 2 analyst; (echo "# PRD"; seq 50) > "$R/prd.md"; gate 0 analyst
gate 0 coder "$T/tr-none.jsonl"

# helper: worktrees, base branch, commit set, RED checksums, PRD protection
cd "$T" && git init -q --bare origin.git && git clone -q origin.git ws/api 2>/dev/null
( cd ws/api && git checkout -q -b dev && echo a > a.txt && git add -A && git commit -qm base \
  && git push -q origin dev && git checkout -q -b someone-else && echo b > b.txt && git add -A \
  && git commit -qm other && echo wip >> a.txt )
cd "$T/ws"
check() { n=$((n+1)); if eval "$2"; then :; else fail=1; echo "FAIL helper: $1"; fi; }
RUN=$(python3 -I "$SHIP" init x-new-thing | sed 's/RUN=//')
check "second init of the same feature asks" "! python3 -I '$SHIP' init x-new-thing 2>/dev/null"
check "vague branch name rejected" "! python3 -I '$SHIP' --run '$RUN' join api feat/adm-0049 2>/dev/null"
python3 -I "$SHIP" --run "$RUN" join api feat/x-new-thing >/dev/null
WT="$T/ws/api-x-new-thing"
check "worktree created" "[ -d '$WT' ]"
check "branched from origin/dev, not the checkout" "[ \"\$(git -C '$WT' log -1 --format=%s)\" = base ]"
check "no upstream" "! git -C '$WT' rev-parse --abbrev-ref @{u} >/dev/null 2>&1"
check "user's checkout untouched" "[ \"\$(git -C api branch --show-current)\" = someone-else ] && git -C api status --porcelain | grep -q a.txt"
echo new > "$WT/B.java"; echo t > "$WT/T.java"; echo "$WT/T.java" > "$RUN/red-tests.txt"
python3 -I "$SHIP" --run "$RUN" redsum >/dev/null
check "redcheck passes" "python3 -I '$SHIP' --run '$RUN' redcheck >/dev/null"
echo x >> "$WT/T.java"
check "redcheck catches a changed test" "! python3 -I '$SHIP' --run '$RUN' redcheck 2>/dev/null"
check "commitset lists the run's files" "python3 -I '$SHIP' --run '$RUN' commitset | grep -q B.java"
python3 -I "$SHIP" --run "$RUN" commit "feat: test" >/dev/null
check "commit landed on the feature branch" "[ \"\$(git -C '$WT' log -1 --format=%s)\" = 'feat: test' ]"
printf '| Document Version | 1.2 |\n' > "PRD - Client Feature.md"
printf '# PRD\nGenerated by /ship analyst\n' > "$RUN/prd.md"
check "client PRD never overwritten" "! python3 -I '$SHIP' --run '$RUN' prd-save 'Client Feature' --replace 2>/dev/null"
check "prd-find sees the PRD" "python3 -I '$SHIP' prd-find client | grep -q 'Client Feature'"
check "second run on the same repo in parallel" "R2=\$(python3 -I '$SHIP' init y-other-thing | sed 's/RUN=//') && python3 -I '$SHIP' --run \"\$R2\" join api fix/y-other-thing >/dev/null && [ -d '$T/ws/api-y-other-thing' ]"

[ $fail = 0 ] && echo "ALL $n CASES PASS" || { echo "SOME CASES FAILED ($n run)"; exit 1; }
