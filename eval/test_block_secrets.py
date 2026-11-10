"""Tests for scripts/block_secrets.py in both modes, using throwaway git repos in tmp_path.

Fake keys are assembled at runtime so no key-shaped literal lives in this file.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "block_secrets.py"
HOOKS_DIR = ROOT / "scripts" / "githooks"
FAKE_AIZA = "AI" + "za" + "Sy" + "X" * 33
FAKE_AQ = "AQ" + "." + "Ab" + "Y" * 40


def run_claude_hook(cwd, command, tool="PowerShell"):
    payload = {"tool_name": tool, "cwd": str(cwd), "tool_input": {"command": command}}
    return subprocess.run([sys.executable, str(SCRIPT), "--claude-hook"],
                          input=json.dumps(payload), capture_output=True, text=True)


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)

    def g(*a, check=True):
        return subprocess.run(["git", *a], cwd=path, check=check, capture_output=True, text=True)
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    (path / ".gitignore").write_text(".env\n")
    (path / "ok.py").write_text("print('hi')\n")
    g("add", ".")
    g("commit", "-qm", "init")
    return g


# ---------- Claude Code PreToolUse mode ----------

def test_claude_blocks_staged_env_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=x\n")
    g("add", "-f", ".env")
    r = run_claude_hook(tmp_path, 'git commit -m "add config"')
    assert r.returncode == 2, r.stderr
    assert ".env" in r.stderr


def test_claude_blocks_nested_env_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / ".env").write_text("A=1\n")
    g("add", "-f", "sub/.env")
    assert run_claude_hook(tmp_path, "git commit -m x", tool="Bash").returncode == 2


def test_claude_blocks_aiza_key_in_staged_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "config.py").write_text(f'KEY = "{FAKE_AIZA}"\n')
    g("add", "config.py")
    r = run_claude_hook(tmp_path, "git commit -m x")
    assert r.returncode == 2 and "key" in r.stderr


def test_claude_blocks_aq_key_in_staged_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "config.py").write_text(f'KEY = "{FAKE_AQ}"\n')
    g("add", "config.py")
    assert run_claude_hook(tmp_path, "git commit -m x").returncode == 2


def test_claude_blocks_chained_add_then_commit(tmp_path):
    make_repo(tmp_path)
    (tmp_path / "new.py").write_text(f"k = '{FAKE_AQ}'\n")  # untracked, not yet staged
    assert run_claude_hook(tmp_path, "git add .; git commit -m x").returncode == 2


def test_claude_blocks_key_in_commit_message(tmp_path):
    make_repo(tmp_path)
    assert run_claude_hook(tmp_path, f'git commit -m "{FAKE_AIZA}"').returncode == 2


def test_claude_blocks_force_add_env_in_command(tmp_path):
    make_repo(tmp_path)
    assert run_claude_hook(tmp_path, "git add -f .env && git commit -m x", tool="Bash").returncode == 2


def test_claude_allows_clean_commit(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=x\n")  # present but gitignored
    (tmp_path / ".env.example").write_text("GEMINI_API_KEY=\n")
    (tmp_path / "notes.md").write_text('Keys start with "AIza" or "AQ." (docs mention).\n')
    g("add", ".")
    r = run_claude_hook(tmp_path, "git commit -m 'clean'")
    assert r.returncode == 0, r.stderr


def test_claude_allows_commit_message_mentioning_env(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    g("add", "a.py")
    assert run_claude_hook(tmp_path, 'git commit -m "block commits with a .env file"').returncode == 0


def test_claude_ignores_non_commit_commands(tmp_path):
    make_repo(tmp_path)
    (tmp_path / "x.py").write_text(f"k='{FAKE_AIZA}'\n")
    assert run_claude_hook(tmp_path, "git status").returncode == 0


# ---------- Real git hook mode (actual `git commit`, hook installed via core.hooksPath) ----------

def install(g):
    g("config", "core.hooksPath", HOOKS_DIR.as_posix())


def test_git_hook_blocks_staged_fake_key(tmp_path):
    g = make_repo(tmp_path)
    install(g)
    (tmp_path / "config.py").write_text(f'KEY = "{FAKE_AQ}"\n')
    g("add", "config.py")
    r = g("commit", "-m", "x", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr, r.stderr
    assert g("rev-list", "--count", "HEAD").stdout.strip() == "1"


def test_git_hook_blocks_staged_env(tmp_path):
    g = make_repo(tmp_path)
    install(g)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=x\n")
    g("add", "-f", ".env")
    r = g("commit", "-m", "x", check=False)
    assert r.returncode != 0 and ".env" in r.stderr, r.stderr


def test_git_hook_allows_clean_commit(tmp_path):
    g = make_repo(tmp_path)
    install(g)
    (tmp_path / "notes.md").write_text('Mentions "AIza" and "AQ." and .env only.\n')
    g("add", "notes.md")
    r = g("commit", "-m", "clean", check=False)
    assert r.returncode == 0, r.stderr


def test_git_hook_blocks_merge_commit_with_key(tmp_path):
    g = make_repo(tmp_path)
    install(g)
    g("checkout", "-q", "-b", "feature")
    (tmp_path / "leak.py").write_text(f"k = '{FAKE_AIZA}'\n")
    g("add", "leak.py")
    g("commit", "-q", "--no-verify", "-m", "sneaky")  # bypassed on the branch
    g("checkout", "-q", "main")
    (tmp_path / "main.py").write_text("y = 2\n")
    g("add", "main.py")
    g("commit", "-qm", "diverge")
    r = g("merge", "--no-ff", "-m", "merge", "feature", check=False)
    assert r.returncode != 0 and "BLOCKED" in r.stderr, r.stdout + r.stderr


def test_git_hook_applies_in_worktree(tmp_path):
    main_repo = tmp_path / "main"
    g = make_repo(main_repo)
    install(g)
    wt = tmp_path / "wt"
    g("worktree", "add", "-q", "-b", "wtbranch", str(wt))

    def gw(*a, check=True):
        return subprocess.run(["git", *a], cwd=wt, check=check, capture_output=True, text=True)
    assert gw("config", "core.hooksPath").stdout.strip() == HOOKS_DIR.as_posix()
    (wt / ".env").write_text("A=1\n")
    gw("add", "-f", ".env")
    r = gw("commit", "-m", "x", check=False)
    assert r.returncode != 0 and ".env" in r.stderr, r.stderr
