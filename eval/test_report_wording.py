"""The evaluation report must not claim more about the labels than data/ground_truth_meta.json says.

While `label_status` is `ai_drafted_unverified`, no report text (fresh or committed) may say the
labels were made or checked by people. See docs/limits.md section 2.
"""
import json
import re
from pathlib import Path

import pytest

import run_eval
from io_utils import read_csv
from report import LABEL_STATUS_TEXT, synthetic_statement

REPO = Path(__file__).resolve().parent.parent
META = REPO / "data/ground_truth_meta.json"


def _committed_reports() -> list[Path]:
    """Reports tracked by git (eval/results/ is gitignored; published runs are force-added).
    Without git, every report on disk is checked."""
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files", "eval/results/*/report.md"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
        return sorted(REPO / line for line in out.splitlines() if line)
    except (OSError, subprocess.CalledProcessError):
        return sorted((REPO / "eval/results").glob("*/report.md"))


COMMITTED_REPORTS = _committed_reports()

# Phrases that claim people made or checked the labels.
HUMAN_LABEL_CLAIM = re.compile(
    r"label(?:l)?ed by (?:people|humans?|a human|hand|reviewers)"
    r"|human[- ]label(?:l)?ed|hand[- ]label(?:l)?ed"
    r"|a human (?:label(?:l)?ed|could not identify)"
    r"|verified by (?:people|humans?)",
    re.IGNORECASE,
)


def _meta_status() -> str:
    return json.loads(META.read_text(encoding="utf-8")).get("label_status", "ai_drafted_unverified")


def _unverified() -> bool:
    return _meta_status() == "ai_drafted_unverified"


def test_meta_label_status_is_known():
    assert _meta_status() in LABEL_STATUS_TEXT


def test_meta_status_matches_ground_truth_rows():
    """`human_verified` in the meta is only allowed when every row has two different reviewers."""
    from metrics import is_verified
    rows = read_csv(REPO / "data/ground_truth.csv")
    if _meta_status() == "human_verified":
        assert all(is_verified(r) for r in rows)
    else:
        assert not all(is_verified(r) for r in rows) or not rows, \
            "every row is verified; update label_status in data/ground_truth_meta.json"


def test_statement_follows_meta():
    stmt = synthetic_statement(_meta_status())
    if _unverified():
        assert not HUMAN_LABEL_CLAIM.search(stmt), stmt
        assert "No person has verified them" in stmt


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        synthetic_statement("labelled_by_people")


def test_fresh_report_makes_no_human_label_claim(tmp_path):
    out_dir = run_eval.main(["--fixture", "--out-root", str(tmp_path)])
    texts = [(out_dir / "report.md").read_text(encoding="utf-8"),
             (out_dir / "failures.csv").read_text(encoding="utf-8")]
    assert synthetic_statement(_meta_status()) in texts[0]
    if _unverified():
        for t in texts:
            m = HUMAN_LABEL_CLAIM.search(t)
            assert m is None, f"report claims human labelling: {m.group(0)!r}"


@pytest.mark.parametrize("path", COMMITTED_REPORTS, ids=lambda p: p.parent.name)
def test_committed_reports_make_no_human_label_claim(path):
    """Committed (published) reports must be regenerated when the wording rule changes."""
    if not _unverified():
        pytest.skip("labels are human-verified")
    for f in (path, path.with_name("failures.csv")):
        if f.exists():
            m = HUMAN_LABEL_CLAIM.search(f.read_text(encoding="utf-8"))
            assert m is None, f"{f.relative_to(REPO)} claims human labelling: {m.group(0)!r}"
