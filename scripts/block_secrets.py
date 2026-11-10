"""Block commits that would add secrets. One scanner, two entry points.

Blocks when a commit would include:
  - a file named `.env` (any directory), or
  - a string starting with "AIza" (classic Google API key) or "AQ." (newer Google key
    format) followed by key-like characters. Bare mentions of the prefixes are allowed.

Modes:
  --git-hook     Real git hook (pre-commit / pre-merge-commit). Scans the staged index
                 only, since that is exactly what will be committed. Exit 1 blocks.
  --claude-hook  Claude Code PreToolUse hook. Reads the tool call JSON on stdin, acts
                 only on commands containing `git commit`. Runs BEFORE the command, so a
                 chained `git add . && git commit` hasn't staged anything yet: it also scans
                 unstaged + untracked (non-ignored) files and the command text. Exit 2 blocks.

Stdlib only, so it runs with any Python 3 on PATH.
"""
import json
import os
import re
import subprocess
import sys

# Key-like tail is required so docs that mention the bare prefixes don't trip it.
KEY_RE = re.compile(r"(?<![A-Za-z0-9])(?:AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{20,})")
COMMIT_RE = re.compile(r"\bgit\b(?:\s+-[cC]\s+\S+)*\s+commit\b")
# Only `git add ... .env` in command text, so a commit *message* mentioning .env is fine.
ENV_ADD_RE = re.compile(r"\bgit\s+add\b[^;&|\r\n]*?[\s/\\'\"]\.env(?=$|[\s'\";|&)])")


class Blocked(Exception):
    pass


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def is_env_file(path):
    return os.path.basename(path.strip().strip('"')) == ".env"


def check_paths(paths):
    for p in paths:
        if p and is_env_file(p):
            raise Blocked(f"a file named .env would be committed: {p}")


def check_added_lines(diff_text):
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++") and KEY_RE.search(line):
            raise Blocked("changes add a Google API key pattern (AIza... / AQ....).")


def scan_staged(cwd):
    """What the next commit will contain."""
    check_paths(git(cwd, "diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines())
    check_added_lines(git(cwd, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff"))


def scan_worktree_extra(cwd):
    """Things a chained `git add` could still stage before the commit runs."""
    unstaged = git(cwd, "diff", "--name-only").splitlines()
    untracked = git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()
    check_paths(unstaged + untracked)
    check_added_lines(git(cwd, "diff", "-U0", "--no-color", "--no-ext-diff"))
    for p in untracked:
        full = os.path.join(cwd, p)
        try:
            if os.path.getsize(full) > 5_000_000:
                continue
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                if KEY_RE.search(fh.read()):
                    raise Blocked(f"untracked file contains a Google API key pattern: {p}")
        except OSError:
            continue


def run_git_hook():
    try:
        scan_staged(os.getcwd())
    except Blocked as e:
        print(f"BLOCKED by scripts/block_secrets.py: {e}", file=sys.stderr)
        print("Unstage it (git restore --staged <file>) and try again.", file=sys.stderr)
        return 1
    return 0


def run_claude_hook():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    if not COMMIT_RE.search(command):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    try:
        if KEY_RE.search(command):
            raise Blocked("command text contains a Google API key pattern (AIza... / AQ....).")
        if ENV_ADD_RE.search(command):
            raise Blocked("command stages a file named .env.")
        scan_staged(cwd)
        scan_worktree_extra(cwd)
    except Blocked as e:
        print(f"BLOCKED by scripts/block_secrets.py: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--claude-hook"
    sys.exit(run_git_hook() if mode == "--git-hook" else run_claude_hook())
