"""docs/demo/index.html: rebuilt from the recorded demo and result files, self-contained, labelled."""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_demo_page as bdp  # noqa: E402

PAGE = REPO / "docs" / "demo" / "index.html"


def _data(html: str) -> dict:
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_committed_page_is_up_to_date():
    assert PAGE.read_text(encoding="utf-8") == bdp.build()
    assert (REPO / "docs" / ".nojekyll").exists()


def test_label_and_no_external_requests():
    html = PAGE.read_text(encoding="utf-8")
    assert "Recorded replay on synthetic data, simulated outbox, not a live system" in html
    assert "client-side replay" in html
    assert not re.search(r"<(script|link|img|iframe)[^>]+(src|href)=", html, re.I)
    assert "@import" not in html and "url(" not in html
    urls = set(re.findall(r"https?://[^\"\\\s<]+", html))
    assert urls <= {bdp.REPO_URL, bdp.README_URL}


def test_numbers_come_from_result_files():
    d = _data(PAGE.read_text(encoding="utf-8"))["results"]
    scores = json.loads(bdp.RESULTS.read_text(encoding="utf-8"))["scores"]
    lane = next(r for r in d["rows"] if r["key"] == "lane_accuracy")
    assert lane["baseline"] == scores["baseline"]["all"]["lane_accuracy"]
    assert lane["deming"] == scores["deming_rep0"]["all"]["lane_accuracy"]
    rt = d["redteam"]
    assert rt["before"] == {"mock": [33, 45], "obedient": [15, 45]}
    assert rt["after"] == {"mock": [45, 45], "obedient": [43, 45]}
    assert [f["id"] for f in rt["open_findings"]] == ["F5", "F7"]


def test_demo_replay_content():
    s = _data(PAGE.read_text(encoding="utf-8"))["demo"]["stages"]
    assert len(s) == 3
    assert s[0]["outbox"] == [] and all(p["status"] == "pending" for p in s[0]["proposals"])
    assert s[1]["outbox"] and all(o["note"].startswith("SIMULATED") for o in s[1]["outbox"])
    t = {x["device_id"]: x for x in s[2]["tickets"]}
    assert t["DEV-101"]["status"] == "closed" and t["DEV-102"]["status"] == "closed"
    assert t["DEV-104"]["status"] == "escalated" and "still below" in t["DEV-104"]["last_note"]
