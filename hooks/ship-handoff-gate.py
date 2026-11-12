#!/usr/bin/env python3
"""SubagentStop gate for the /ship pipeline agents.

Blocks a pipeline agent from finishing until it has written its handoff
file in .pipeline/ during this run, with the required status line.
Exits 0 (allow) whenever it is not inside a /ship run or cannot tell.
Usage (agent frontmatter Stop hook): ship-handoff-gate.py <agent-name>
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

# Size limits (lines) for files every later stage re-reads; one block, then
# the agent may finish (stop_hook_active), so this nudges rather than traps.
MAX_LINES = {"prd.md": 400, "prd-review.md": 200, "spec.md": 350}

RULES = {
    "analyst": (("prd-review.md", "prd.md"), r"\A(PRD: (READY|READY WITH NOTES|NEEDS CHANGES)\b|#)",
                "a first line `PRD: READY|READY WITH NOTES|NEEDS CHANGES` (review) or a `#` title (prd.md)"),
    "planner": ("spec.md", r"^## OPEN QUESTIONS", "a `## OPEN QUESTIONS` heading"),
    "coder": ("changes.md", r"\S", "content"),
    "tester": ("test-results.md", r"\ARESULT: (RED|PASS|FAIL)\b",
               "first line `RESULT: RED`, `RESULT: PASS` or `RESULT: FAIL`"),
    "reviewer": ("review.md", r"\AVERDICT: (SHIP|NEEDS WORK|BLOCK)\b",
                 "first line `VERDICT: SHIP`, `VERDICT: NEEDS WORK` or `VERDICT: BLOCK`"),
    "documenter": ("docs.md", r"\S", "content"),
    "investigator": (("diagnosis.md", "review-triage.md"), r"\S", "content"),
}


def find_run(data):
    """The /ship run folder this agent belongs to: the `SHIP_RUN=<dir>` line
    the orchestrator puts at the top of every pipeline agent's task."""
    import time
    path = data.get("agent_transcript_path")
    if not path and data.get("transcript_path") and data.get("agent_id"):
        base = data["transcript_path"]
        base = base[:-6] if base.endswith(".jsonl") else base
        path = os.path.join(base, "subagents", f"agent-{data['agent_id']}.jsonl")
    if not path:
        return None
    for _ in range(4):  # the transcript is written asynchronously
        try:
            with open(path) as f:
                for i, line in enumerate(f):
                    m = re.search(r"SHIP_RUN=([^\s\\\"']+)", line)
                    if m:
                        run = os.path.realpath(os.path.expanduser(m.group(1)))
                        return run if os.path.isdir(run) else None
                    if i > 3:
                        return None
        except OSError:
            pass
        time.sleep(0.4)
    return None


def agent_start(transcript):
    try:
        with open(transcript) as f:
            for line in f:
                ts = json.loads(line).get("timestamp")
                if ts:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (OSError, ValueError):
        pass
    return None


def main():
    agent = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if data.get("stop_hook_active") or agent not in RULES:
        return 0
    pipeline = find_run(data)
    if not pipeline or not os.path.isfile(os.path.join(pipeline, ".active")):
        return 0  # not inside a /ship run

    names, pattern, need = RULES[agent]
    start = agent_start(data.get("agent_transcript_path") or "")
    problem = None
    for name in (names if isinstance(names, tuple) else (names,)):
        path = os.path.join(pipeline, name)
        if not os.path.isfile(path):
            problem = f"{path} does not exist"
        elif start and os.path.getmtime(path) < start - 5:
            problem = f"{path} was not written during this run (it is from an earlier stage)"
        else:
            with open(path, errors="replace") as f:
                text = f.read()
            problem = None if re.search(pattern, text, re.MULTILINE) else f"{path} is missing {need}"
            limit = MAX_LINES.get(name)
            if problem is None and limit and text.count("\n") > limit:
                problem = (f"{path} has {text.count(chr(10))} lines; the limit is {limit}. Tighten it: "
                           "no repetition, cite path:line instead of quoting code, move detail "
                           "the next stage does not need out of the file")
        if problem is None:
            break
    try:
        with open(os.path.join(pipeline, "hooks.log"), "a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} gate {agent} "
                    f"{'BLOCK ' + problem if problem else 'pass'}\n")
    except OSError:
        pass
    if problem:
        print(f"/ship gate: {problem}. Write the handoff file as your "
              f"instructions require, then finish.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
