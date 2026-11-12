#!/usr/bin/env python3
"""PreToolUse guard for the /ship pipeline agents.

Denies (exit 2, reason on stderr) what pipeline agents must never do:
git commands other than read-only ones, remote access, publishing,
dependency installs, stage/prod profiles or databases, and file writes
outside the run's repos. Read-only agents may not write files via Bash.
Usage (agent frontmatter PreToolUse hook): ship-tool-guard.py <agent-name>
"""
import json
import os
import re
import subprocess
import sys

READ_ONLY_BASH = {"analyst", "planner", "reviewer", "investigator", "documenter"}
PIPELINE_ONLY_WRITES = {"analyst", "planner", "reviewer", "investigator"}
GIT_READ = {"status", "diff", "log", "show", "rev-parse", "ls-files", "blame", "grep",
            "describe", "cat-file", "merge-base", "shortlog", "ls-tree", "diff-tree", "show-ref"}
LOCAL = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
CMD_START = r"(?:^|[;&|(`]\s*|\$\(\s*|\b(?:sudo|exec|xargs|env|nohup|time|timeout\s+\d+)\s+)"

GIT = re.compile(r"(?:^|[;&|(`\"']\s*|\$\(\s*|\b(?:sudo|exec|xargs|env|nohup|time|timeout\s+\d+)\s+)git((?:\s+-[Cc]\s+\S+|\s+--?[\w.-]+(?:=\S+)?)*)\s+([\w-]+)([^;&|]*)")
DENY = [
    (re.compile(r"\bship\.py\b"), "ship.py is the orchestrator's tool"),
    (re.compile(CMD_START + r"(ssh|scp|sshpass|rsync|sftp|kubectl|telnet|nc)\b"),
     "no remote access from pipeline agents"),
    (re.compile(r"\bdocker\s+(push|login)\b"), "no publishing images"),
    (re.compile(r"\b(mvn|mvnw|gradle|gradlew)\b[^|;&]*\s(deploy|publish\w*)(?=\s|$)"),
     "no publishing artifacts"),
    (re.compile(r"\b(npm|pnpm|yarn)\s+(i|install|add)\b|\bnpx\s|\bpip3?\s+install\b|"
                r"\bpoetry\s+add\b|\bcargo\s+(add|install)\b|\bapt(-get)?\s+install\b"),
     "no dependency installs or downloads (ask the user)"),
    (re.compile(r"(spring[._-]profiles[._-]active|SPRING_PROFILES_ACTIVE|run\.profiles)"
                r"[=\s]\S*(stage|prod)|\s-P\s*\S*(stage|prod)", re.I),
     "never run against stage/prod profiles"),
    (re.compile(r"\bgit\b[^;&|]*\s--output\b"), "git --output writes files"),
]
# .pipeline files only the orchestrator (ship.py) may write
PROTECTED = ("repos.txt", "pre-run.txt", "red.sha", ".active", "hooks.log", "changed.txt", "snap",
             "constitutions.txt", "mains.txt")
HOST_URL = re.compile(r"\b[a-z][\w+.-]*://(?:[^@/\s]+@)?(\[[^\]]+\]|[^/\s:'\"]+)", re.I)
BARE_HOST = re.compile(r"^(localhost|\d{1,3}(?:\.\d{1,3}){3}|[\w-]+(?:\.[\w-]+)*\.[a-z]{2,})(:\d+)?(/|$)", re.I)
WRITE_BASH = re.compile(
    r"\bsed\s+(?:-\w*i|--in-place)|\bperl\s+-\w*i|\btee\b|\bpython3?\s+-c\b|"
    r"(?<![0-9&<>])>{1,2}(?!&)\s*(?!/dev/null\b)[^\s&|;]|"
    + CMD_START + r"(cp|mv|rm|touch|mkdir|ln|chmod|truncate|dd|install|patch)\b")
WRITE_TARGET = re.compile(r"(?<![0-9&<>])>{1,2}\s*([^\s&|;]+)|\btee\s+(?:-a\s+)?([^\s&|;]+)")
FILE_CHANGE_CMD = re.compile(CMD_START + r"(cp|mv|rm|touch|mkdir|ln|chmod|truncate|dd)\b|"
                             r"\bsed\s+(?:-\w*i|--in-place)")


def git_toplevel(path):
    try:
        out = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


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


RUN = None  # set in main()


def roots(cwd):
    """(run folder, allowed write roots). Outside a /ship run there is no run
    folder and agents may write nowhere."""
    if not RUN:
        return "/nonexistent-ship-run", set()
    result = set()
    repos = os.path.join(RUN, "repos.txt")
    if os.path.isfile(repos):
        with open(repos) as f:
            result.update(os.path.realpath(line.strip()) for line in f if line.strip())
    return RUN, result


def inside(path, base):
    return path == base or path.startswith(base.rstrip("/") + "/")


def protected(real, pipeline, agent):
    """Run control files: never writable by agents (red-tests.txt: tester only)."""
    if "/.pipeline/" in real + "/":
        return f"no .pipeline/ folders: write handoff files directly into the run folder {pipeline}/"
    rel = os.path.relpath(real, pipeline) if inside(real, pipeline) else None
    if rel is not None:
        first = rel.split(os.sep)[0]
        if first in PROTECTED or (first == "red-tests.txt" and agent != "tester"):
            return f"{rel} is a /ship control file"
    if "/.ship/" in real or real.endswith("/.ship"):
        return "the repo constitution is edited only by the user / orchestrator"
    return None


def allowed_path(real, pipeline, allowed):
    return inside(real, pipeline) or inside(real, "/tmp") or any(inside(real, r) for r in allowed)


def strip_quotes(cmd):
    """Drop quoted strings so `grep 'a > b'` is not read as a redirect."""
    return re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", cmd)


def hosts_in(cmd):
    """Hosts named in the curl/wget/http segments of the command only."""
    hosts = set()
    for seg in re.split(r"[;&|]+", cmd):
        if not re.search(r"(?:^|\s)(curl|wget|http|httpie)\b", seg):
            continue
        hosts |= {h.lower() for h in HOST_URL.findall(seg)}
        for token in re.split(r"[\s'\"=]+", seg):
            if token.startswith("-"):
                continue
            m = BARE_HOST.match(token)
            if m:
                hosts.add(m.group(1).lower())
    return hosts


def check_bash(agent, cmd, cwd):
    cmd = cmd.strip()
    for m in GIT.finditer(cmd):
        opts, sub, rest = m.group(1), m.group(2), m.group(3)
        if re.search(r"\s-c\s", opts + " "):
            return "git -c overrides are not allowed"
        if sub == "branch" and re.fullmatch(r"\s*(--show-current|--list|-a|-r|-v|-vv)?\s*", rest):
            continue
        if sub not in GIT_READ:
            return f"git {sub} is not allowed; only read-only git commands (the orchestrator owns git)"
    for pattern, reason in DENY:
        if pattern.search(cmd):
            return reason
    if re.search(CMD_START + r"(curl|wget|http|httpie)\b", cmd):
        hosts = hosts_in(cmd)
        if not hosts or hosts - LOCAL:
            return "curl/wget only to an explicit localhost / 127.0.0.1 URL"
    if re.search(r"\bpsql\b|\bPGHOST=", cmd):
        targets = set(re.findall(r"(?:-h\s*|--host[= ]|PGHOST=)['\"]?([^\s'\"]+)", cmd))
        targets |= {h.lower() for h in HOST_URL.findall(cmd)}
        if targets - LOCAL:
            return "psql only against a local database"
    bare = strip_quotes(cmd)
    if agent in READ_ONLY_BASH:
        if WRITE_BASH.search(bare):
            return f"{agent} may not write files through Bash; use the Write tool for its .pipeline/ file"
        return None
    pipeline, allowed = roots(cwd)
    pipeline = os.path.realpath(pipeline)
    here = cwd

    def resolve(path, base):
        path = os.path.expanduser(path)
        return os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))

    def check(real, shown):
        if not (allowed_path(real, pipeline, allowed) or inside(real, "/usr") or inside(real, "/bin")):
            return f"file changes must stay inside the run's repos ({shown})"
        return protected(real, pipeline, agent)

    # walk the command in order so `cd <dir> && ...` is honoured
    for seg in re.split(r"&&|\|\||[;&|]", bare):
        seg = seg.strip()
        words = seg.split()
        if words[:1] == ["cd"]:
            here = resolve(words[1], here) if len(words) > 1 else os.path.expanduser("~")
            continue
        for m in WRITE_TARGET.finditer(seg):
            target = m.group(1) or m.group(2)
            if not target.startswith("/dev/"):
                bad = check(resolve(target, here), target)
                if bad:
                    return bad
        if FILE_CHANGE_CMD.search(seg):
            for arg in words[1:]:
                if arg.startswith("-") or arg == "''" or re.match(r"^s[/|#]|^[0-7]{3,4}$|^[ugoa]*[-+=][rwxX]+$", arg) \
                        or arg in ("cp", "mv", "rm", "touch", "mkdir", "ln", "chmod", "sed"):
                    continue
                bad = check(resolve(arg, here), arg)
                if bad:
                    return bad
    return None


def check_write(agent, path, cwd):
    pipeline, allowed = roots(cwd)
    real = os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path))
    bad = protected(real, pipeline, agent)
    if bad:
        return bad
    if inside(real, pipeline):
        return None
    if agent in PIPELINE_ONLY_WRITES:
        return f"{agent} may only write inside {pipeline}"
    if not any(inside(real, r) for r in allowed):
        if not RUN:
            return ("no /ship run found for this agent (its task must start with "
                    "SHIP_RUN=<run folder>); nothing may be written")
        return (f"writes must stay inside the run's worktrees: {', '.join(sorted(allowed)) or '(none yet)'}"
                " (listed in the run's repos.txt)")
    if agent == "documenter":
        rel = [os.path.relpath(real, r) for r in allowed if inside(real, r)][0]
        # Root-level *.md is allowed too: not every repo keeps its docs under docs/
        # (ib-identity-management has API_DOCUMENTATION.md / SERVICE_OVERVIEW.md at the root).
        # Code is still fenced off, and a .md nested under src/ is still rejected.
        if not (re.search(r"(^|/)docs/", rel)
                or re.search(r"(^|/)(README|CHANGELOG)[^/]*$", rel)
                or re.fullmatch(r"[^/]+\.md", rel, re.IGNORECASE)):
            return "documenter may only write docs/, README*, CHANGELOG* and root-level *.md"
    return None


def main():
    global RUN
    agent = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.load(sys.stdin)
    except ValueError:
        print("/ship guard: unreadable hook input; blocking to be safe.", file=sys.stderr)
        return 2
    RUN = find_run(data)
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    reason = None
    if tool == "Bash":
        reason = check_bash(agent, inp.get("command", ""), cwd)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        if path:
            reason = check_write(agent, path, cwd)
    audit(f"guard {agent} {tool} {'DENY ' + reason if reason else 'allow'}")
    if reason:
        print(f"/ship guard ({agent}): blocked: {reason}.", file=sys.stderr)
        return 2
    return 0


def audit(line):
    """Append to <run>/hooks.log during a /ship run (proof the hooks ran)."""
    try:
        if RUN and os.path.isfile(os.path.join(RUN, ".active")):
            from datetime import datetime
            with open(os.path.join(RUN, "hooks.log"), "a") as f:
                f.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
