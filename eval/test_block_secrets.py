"""Tests for .claude/hooks/block_secrets.py. Uses throwaway git repos in tmp_path.

Fake keys are assembled at runtime so no key-shaped literal lives in this file.
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "block_secrets.py"
FAKE_AIZA = "AI" + "za" + "Sy" + "X" * 33
FAKE_AQ = "AQ" + "." + "Ab" + "Y" * 40


def run_hook(cwd, command, tool="PowerShell"):
    payload = {"tool_name": tool, "cwd": str(cwd), "tool_input": {"command": command}}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True)


def make_repo(tmp_path):
    def g(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    (tmp_path / ".gitignore").write_text(".env\n")
    (tmp_path / "ok.py").write_text("print('hi')\n")
    g("add", ".")
    g("commit", "-qm", "init")
    return g


def test_blocks_staged_env_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=x\n")
    g("add", "-f", ".env")
    r = run_hook(tmp_path, 'git commit -m "add config"')
    assert r.returncode == 2, r.stderr
    assert ".env" in r.stderr


def test_blocks_nested_env_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / ".env").write_text("A=1\n")
    g("add", "-f", "sub/.env")
    assert run_hook(tmp_path, "git commit -m x", tool="Bash").returncode == 2


def test_blocks_aiza_key_in_staged_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "config.py").write_text(f'KEY = "{FAKE_AIZA}"\n')
    g("add", "config.py")
    r = run_hook(tmp_path, "git commit -m x")
    assert r.returncode == 2 and "key" in r.stderr


def test_blocks_aq_key_in_staged_file(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "config.py").write_text(f'KEY = "{FAKE_AQ}"\n')
    g("add", "config.py")
    assert run_hook(tmp_path, "git commit -m x").returncode == 2


def test_blocks_chained_add_then_commit(tmp_path):
    make_repo(tmp_path)
    (tmp_path / "new.py").write_text(f"k = '{FAKE_AQ}'\n")  # untracked, not yet staged
    assert run_hook(tmp_path, "git add .; git commit -m x").returncode == 2


def test_blocks_key_in_commit_message(tmp_path):
    make_repo(tmp_path)
    assert run_hook(tmp_path, f'git commit -m "{FAKE_AIZA}"').returncode == 2


def test_blocks_force_add_env_in_command(tmp_path):
    make_repo(tmp_path)
    assert run_hook(tmp_path, "git add -f .env && git commit -m x", tool="Bash").returncode == 2


def test_allows_clean_commit(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=x\n")  # present but gitignored
    (tmp_path / ".env.example").write_text("GEMINI_API_KEY=\n")
    (tmp_path / "notes.md").write_text('Keys start with "AIza" or "AQ." (docs mention).\n')
    g("add", ".")
    r = run_hook(tmp_path, "git commit -m 'clean'")
    assert r.returncode == 0, r.stderr


def test_allows_commit_message_mentioning_env(tmp_path):
    g = make_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    g("add", "a.py")
    assert run_hook(tmp_path, 'git commit -m "block commits with a .env file"').returncode == 0


def test_ignores_non_commit_commands(tmp_path):
    make_repo(tmp_path)
    (tmp_path / "x.py").write_text(f"k='{FAKE_AIZA}'\n")
    assert run_hook(tmp_path, "git status").returncode == 0
