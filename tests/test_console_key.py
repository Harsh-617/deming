"""Deming Console key loading: GEMINI_API_KEY from the environment, else only that one line of
.env. The key must never appear in a response, a log line, the console's stdout/stderr or any
file the console writes, and without a key the console falls back to the mock.

Fake .env files and fake keys only. No network and no LLM calls (a fake client stands in for
Gemini). The real repo-root .env is never read: every test points the console elsewhere.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import console as cs  # noqa: E402
from sim import config  # noqa: E402
from test_console import Server, _fake_gemini, try_body  # noqa: E402

# Built at runtime so the source never contains a key-shaped string (scripts/block_secrets.py).
FAKE_KEY = "AI" + "za" + "SyFAKE" + "x" * 30
# A key that does not match the Google key pattern, so only the exact-value redaction can hide it.
PLAIN_KEY = "plain-fake-key-" + "q" * 24


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cs, "ENV_FILE", tmp_path / "no-such-dir" / ".env")
    cs._LOADED_KEYS.clear()
    yield
    cs._LOADED_KEYS.clear()


def write_env(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "fake.env"
    p.write_text(text, encoding="utf-8")
    return p


# ---- parsing -----------------------------------------------------------------------------
@pytest.mark.parametrize("line", [
    f"GEMINI_API_KEY={PLAIN_KEY}",
    f'GEMINI_API_KEY="{PLAIN_KEY}"',
    f"GEMINI_API_KEY='{PLAIN_KEY}'",
    f"  GEMINI_API_KEY = {PLAIN_KEY}  ",
    f"export GEMINI_API_KEY={PLAIN_KEY}",
    f"GEMINI_API_KEY={PLAIN_KEY}  # comment",
    f'GEMINI_API_KEY="{PLAIN_KEY}" # comment',
])
def test_reads_only_the_key_line_with_quotes(tmp_path, line):
    env = write_env(tmp_path, "\n".join([
        "# a comment", "OTHER_SECRET=should-not-be-read", line, "GEMINI_MODEL=not-this", ""]))
    assert cs.load_key(env) == (PLAIN_KEY, ".env")


def test_other_lines_are_ignored_and_not_exported(tmp_path, monkeypatch):
    monkeypatch.delenv("OTHER_SECRET", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    env = write_env(tmp_path, "OTHER_SECRET=x\nGEMINI_MODEL=y\nNOT_GEMINI_API_KEY=z\n"
                              "GEMINI_API_KEY_OLD=old\n")
    assert cs.load_key(env) == ("", "")
    import os
    assert "OTHER_SECRET" not in os.environ and "GEMINI_MODEL" not in os.environ
    assert "GEMINI_API_KEY" not in os.environ  # .env value is never put into the environment


@pytest.mark.parametrize("text", ["GEMINI_API_KEY=\n", 'GEMINI_API_KEY=""\n',
                                  'GEMINI_API_KEY="unterminated\n', "# GEMINI_API_KEY=x\n", ""])
def test_empty_or_commented_key_counts_as_no_key(tmp_path, text):
    assert cs.load_key(write_env(tmp_path, text)) == ("", "")


def test_missing_env_file_means_no_key(tmp_path):
    assert cs.load_key(tmp_path / "nope.env") == ("", "")


def test_environment_wins_over_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    env = write_env(tmp_path, f"GEMINI_API_KEY={PLAIN_KEY}\n")
    assert cs.load_key(env) == (FAKE_KEY, "environment")


def test_bom_and_crlf_env_file(tmp_path):
    p = tmp_path / "bom.env"
    p.write_bytes(("﻿GEMINI_API_KEY=" + PLAIN_KEY + "\r\nX=1\r\n").encode("utf-8"))
    assert cs.load_key(p) == (PLAIN_KEY, ".env")


def test_default_env_file_is_repo_root_dot_env():
    # Tests patch the constant; the source must point it at the repo-root .env.
    src = (ROOT / "scripts" / "console.py").read_text(encoding="utf-8")
    assert 'ENV_FILE = ROOT / ".env"' in src and cs.ROOT == ROOT


# ---- fallback to the mock without a key ------------------------------------------------------
def test_no_key_anywhere_falls_back_to_mock(tmp_path):
    env = write_env(tmp_path, "OTHER=1\n")
    c = cs.Console(tmp_path / "cs", env_file=env)
    called = []
    c.gemini_client_factory = lambda key: called.append(key)  # must never be called
    out = c.try_device(try_body())
    assert out["model"] == "model: mock"
    assert "not set in the environment or .env" in out["fallback"]
    assert out["lane"] == "retire" and called == []


def test_key_from_env_file_is_used(tmp_path):
    env = write_env(tmp_path, f'X=1\nGEMINI_API_KEY="{FAKE_KEY}"\n')
    c = cs.Console(tmp_path / "cs", env_file=env)
    c.gemini_client_factory = _fake_gemini(c)  # asserts it receives FAKE_KEY
    out = c.try_device(try_body())
    assert out["model"] == f"model: {config.GEMINI_MODEL}" and out["fallback"] == ""


def test_http_status_is_shown_on_failure_but_not_the_message(tmp_path):
    env = write_env(tmp_path, f"GEMINI_API_KEY={PLAIN_KEY}\n")
    c = cs.Console(tmp_path / "cs", env_file=env)

    class QuotaError(Exception):
        code = 429

    def factory(key):
        raise QuotaError(f"quota exceeded for key {key}")
    c.gemini_client_factory = factory
    out = c.try_device(try_body())
    assert out["model"] == "model: mock"
    assert "QuotaError, HTTP 429" in out["fallback"] and "quota exceeded" not in out["fallback"]
    assert PLAIN_KEY not in json.dumps(out)


# ---- the key never leaves the process ------------------------------------------------------
@pytest.mark.parametrize("key", [FAKE_KEY, PLAIN_KEY])
def test_env_file_key_never_in_responses_logs_or_files(tmp_path, capsys, caplog, key):
    caplog.set_level(logging.DEBUG)
    env = write_env(tmp_path, f"OTHER=1\nGEMINI_API_KEY='{key}'\n")
    c = cs.Console(tmp_path / "cs", env_file=env)

    def factory(k):
        assert k == key
        raise RuntimeError(f"API key {k} not valid")  # an error text that echoes the key
    c.gemini_client_factory = factory
    s = Server(c)
    try:
        texts = [s.request("POST", "/api/try", try_body())[1],
                 s.request("POST", "/api/try", try_body(name=f"router {key}"))[1],
                 s.request("GET", "/")[1], s.request("GET", "/api/state")[1],
                 s.request("GET", f"/api/state?k={key}")[1],
                 s.request("POST", f"/api/nope?{key}", {})[1]]
        for path in ("/api/run1", "/api/approve", "/api/settings"):
            texts.append(s.request("POST", path, {"proposal_id": key})[1])
        texts.append(s.request("POST", "/api/try", raw=key.encode())[1])
    finally:
        s.close()
    first = json.loads(texts[0])
    assert first["model"] == "model: mock" and "RuntimeError" in first["fallback"]
    logs = capsys.readouterr()
    for t in texts + [logs.out, logs.err, caplog.text]:
        assert key not in t
    for f in (tmp_path / "cs").rglob("*"):
        if f.is_file():
            assert key not in f.read_text(encoding="utf-8", errors="replace")


def test_main_startup_line_never_prints_the_key(tmp_path, monkeypatch, capsys):
    env = write_env(tmp_path, f"GEMINI_API_KEY={PLAIN_KEY}\n")
    monkeypatch.setattr(cs, "ENV_FILE", env)

    class StopServer:
        server_address = ("127.0.0.1", 0)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass
    monkeypatch.setattr(cs, "make_server", lambda console, port: StopServer())
    real = cs.Console
    monkeypatch.setattr(cs, "Console", lambda: real(tmp_path / "cs"))
    assert cs.main([]) == 0
    out = capsys.readouterr()
    assert "found in the .env" in out.out
    assert PLAIN_KEY not in out.out + out.err


def test_scrub_redacts_a_loaded_key_without_the_google_shape(tmp_path):
    cs.load_key(write_env(tmp_path, f"GEMINI_API_KEY={PLAIN_KEY}\n"))
    assert cs.scrub(f"x {PLAIN_KEY} y") == "x [redacted] y"


# ---- password managers ---------------------------------------------------------------------
IGNORE_ATTRS = ['autocomplete="off"', 'data-lpignore="true"', "data-1p-ignore", "data-op-ignore",
                'data-bwignore="true"', 'data-form-type="other"']


def test_every_input_and_select_opts_out_of_autofill():
    import re
    page = (ROOT / "scripts" / "console.html").read_text(encoding="utf-8")
    tags = re.findall(r"<(?:input|select|textarea)\b[^>]*>", page)
    assert len(tags) >= 6
    for tag in tags:
        for attr in IGNORE_ATTRS:
            assert re.search(r"\s" + re.escape(attr) + r"(?=[\s>])", tag), (attr, tag)
    # No script builds form fields at runtime (they would miss the attributes).
    assert not re.search(r"createElement\(\s*['\"](?:input|select|textarea)", page)
