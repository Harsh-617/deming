"""Frozen files: agents/ and schemas/ must be identical to main.

sim/guards.py was frozen the same way until the guards-v2 fixes (docs/redteam-results.md), which
were allowed to change it; see test_guards_pinned below.

The prompts, schemas and guards are the published, evaluated contract (docs/prompts-freeze.md).
New work (for example the Deming Console) must not change them. The test compares the working
tree with `main` (or `origin/main` in a clone without a local main). It skips only when git or
both refs are unavailable, for example in a source tarball.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ["agents", "schemas"]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _base_ref() -> str:
    if shutil.which("git") is None or _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout")
    for ref in ("main", "origin/main"):
        if _git("rev-parse", "--verify", "--quiet", ref + "^{commit}").returncode == 0:
            return ref
    pytest.skip("no main or origin/main ref to compare with")


def test_frozen_files_match_main():
    ref = _base_ref()
    # Working tree (staged or not) against main; --ignore-cr-at-eol for Windows checkouts.
    diff = _git("diff", "--ignore-cr-at-eol", "--name-status", ref, "--", *FROZEN)
    assert diff.returncode == 0, diff.stderr
    assert diff.stdout.strip() == "", f"frozen files differ from {ref}:\n{diff.stdout}"
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", *FROZEN)
    assert untracked.stdout.strip() == "", f"new untracked files under frozen paths:\n{untracked.stdout}"


# sim/guards.py as of the guards-v2 fixes (F1, F2, F3, F4, F6, F8; docs/redteam-results.md).
# sha256 of the file with CRLF normalised to LF. Change it only together with a red-team re-run
# and the offline re-scoring check described in docs/redteam-results.md.
GUARDS_V2_SHA256 = "8ac7ee8d4419399f24064b04679f751974149efa946fa92b4c970c8bf3d35786"


def test_guards_pinned():
    import hashlib
    data = (ROOT / "sim/guards.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == GUARDS_V2_SHA256, (
        "sim/guards.py changed since guards-v2: re-run eval/redteam/run.py and the offline "
        "scoring comparison, then update GUARDS_V2_SHA256")
