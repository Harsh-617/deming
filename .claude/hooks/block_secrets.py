"""PreToolUse hook: block any `git commit` that would commit secrets.

Blocks (exit code 2) when a Bash/PowerShell command contains `git commit` and
anything that could end up in the commit includes:
  - a file named `.env`, or
  - a string starting with "AIza" (classic Google API key) or "AQ." (newer
    Google key format), followed by key-like characters.

What it scans, conservatively (it runs BEFORE the command, so a chained
`git add . && git commit` has not staged anything yet):
  - staged changes, unstaged changes to tracked files, untracked non-ignored files
  - the command text itself (catches a key pasted into `-m "..."` or `git add -f .env`)

Stdlib only, so it runs with any Python 3 on PATH.
"""
import json
import os
import re
import subprocess
import sys

# Key-like tail is required so that docs mentioning the bare prefixes don't trip it.
KEY_RE = re.compile(r"(?<![A-Za-z0-9])(?:AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{20,})")
COMMIT_RE = re.compile(r"\bgit\b(?:\s+-[cC]\s+\S+)*\s+commit\b")
# Only `git add ... .env` in the command text, so a commit *message* mentioning .env is fine.
ENV_TOKEN_RE = re.compile(r"\bgit\s+add\b[^;&|\r\n]*?[\s/\\'\"]\.env(?=$|[\s'\";|&)])")


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def is_env_file(path):
    return os.path.basename(path.strip().strip('"')) == ".env"


def block(reason):
    print(f"BLOCKED by .claude/hooks/block_secrets.py: {reason}", file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # not our business
    command = (data.get("tool_input") or {}).get("command") or ""
    if not COMMIT_RE.search(command):
        return
    cwd = data.get("cwd") or os.getcwd()

    if KEY_RE.search(command):
        block("command text contains a Google API key pattern (AIza... / AQ....).")
    if ENV_TOKEN_RE.search(command):
        block("command references a file named .env.")

    staged = git(cwd, "diff", "--cached", "--name-only").splitlines()
    unstaged = git(cwd, "diff", "--name-only").splitlines()
    untracked = git(cwd, "ls-files", "--others", "--exclude-standard").splitlines()
    for p in staged + unstaged + untracked:
        if p and is_env_file(p):
            block(f"a file named .env would be committed: {p}")

    diff_text = git(cwd, "diff", "--cached", "-U0") + git(cwd, "diff", "-U0")
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++") and KEY_RE.search(line):
            block("staged/unstaged changes add a Google API key pattern (AIza... / AQ....).")

    for p in untracked:
        full = os.path.join(cwd, p)
        try:
            if os.path.getsize(full) > 5_000_000:
                continue
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                if KEY_RE.search(fh.read()):
                    block(f"untracked file contains a Google API key pattern: {p}")
        except OSError:
            continue


if __name__ == "__main__":
    main()
