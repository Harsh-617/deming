"""eval/live_fixture_run.py wiring, with the rule-based mock client instead of Gemini."""
import json

import live_fixture_run as live
from sim import retrieval
from sim.mock_llm import rule_based_client


def test_live_harness_with_mock(tmp_path, monkeypatch):
    kev = retrieval.KevIndex.build(retrieval.load_kev(live.FIX / "feeds" / "kev.json"))
    lc = retrieval.load_lifecycle(live.FIX / "lifecycle.csv")
    catalog = list(kev.keys) + [(r["vendor"], r["product"]) for r in lc]
    orig = live.TimedRunner.__init__
    monkeypatch.setattr(live.TimedRunner, "__init__",
                        lambda self: orig(self, rule_based_client(catalog), cache_dir=None))
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    assert live.main(["--repeats", "2", "--out-root", str(tmp_path)]) == 0
    [summary] = tmp_path.glob("live-summary-*.json")
    s = json.loads(summary.read_text(encoding="utf-8"))
    assert s["settings"]["retire_days"] == 30 and s["settings"]["approver_email"]  # defaults, not {}
    assert s["schema_failures"] == [] and s["errors"] == []
    st = s["stability"]
    assert set(st) == {"structured", "planner_structured", "free_text"}
    assert st["structured"]["all"] == "8/8"  # deterministic mock
    assert summary.with_suffix(".md").exists()
    # Fixture truth for DEV-001/002/007 is unknown (KEV match, no fixed_version); the guards agree.
    assert s["lanes"]["DEV-001"] == {"pred": ["unknown", "unknown"], "truth": "unknown"}
    assert s["lane_correct_per_repeat"] == [8, 8]
