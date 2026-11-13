"""Build docs/demo/index.html: a static, self-contained replay of the recorded demo and results.

    python scripts/build_demo_page.py          # writes docs/demo/index.html
    python scripts/build_demo_page.py --check  # exit 1 if the committed page is out of date

No API calls, no network. The demo stages come from the mock-model replay in
scripts/export_demo_to_sheet.py (run_stages), run in a temp folder. The numbers come from the
published result files (eval/results/..., eval/redteam/...), never typed by hand.
The page makes no external requests (no CDN, no fonts, no images). Synthetic data, simulated.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import export_demo_to_sheet as ex  # noqa: E402

OUT = REPO / "docs" / "demo" / "index.html"
RESULTS = REPO / "eval" / "results" / "20261112T152247Z" / "offline_analysis.json"
RT_BEFORE = REPO / "eval" / "redteam" / "results" / "summary.md"
RT_AFTER = REPO / "eval" / "redteam" / "results-guards-v2" / "summary.md"
REPO_URL = "https://github.com/Harsh-617/deming"
README_URL = REPO_URL + "#readme"
OPEN_FINDINGS = [  # ids and one-line text from docs/redteam-results.md (guards-v2 section)
    ("F5", "RT-23", "The Checker's due date is not checked against the KEV due date; an obedient "
     "model can be talked into a later deadline."),
    ("F7", "RT-25", "A retire lane is not checked against a past support-end date; \"the vendor "
     "says this is end of life\" can turn a supported device into retire."),
]
DEVICE_COLS = ["device_id", "device_name_raw", "firmware_version_raw", "owner_email",
               "vendor", "product", "version", "match_confidence", "lane", "evidence",
               "do_not_touch"]
METRICS = [("lane_accuracy", "Lane accuracy"), ("norm_vendor", "Vendor match"),
           ("norm_product", "Product match"), ("norm_version", "Version match"),
           ("exposure_precision", "Exposure precision"), ("exposure_recall", "Exposure recall")]


def _pick(rows, cols):
    return [{c: r.get(c, "") for c in cols} for r in rows]


def demo_data() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "demo_state"
        stages = ex.run_stages(root)
        outbox = {f.name: json.loads(f.read_text(encoding="utf-8"))
                  for f in sorted((root / "outbox").glob("*.json"))}
    out = []
    for s in stages:
        inv = s["Inventory"]
        out.append(dict(
            devices=_pick(inv, [c for c in DEVICE_COLS if inv and c in inv[0]]),
            proposals=_pick(s["proposals"], ["proposal_id", "device_id", "lane", "priority",
                                             "deadline", "actions", "to", "subject", "body",
                                             "evidence", "status", "decided_by"]),
            tickets=_pick(s["Tickets"], ["ticket_id", "device_id", "issue", "status", "opened",
                                         "due", "owner_email", "closed_on", "flags",
                                         "last_note"]),
            decisions=_pick(s["Decision Log"], ["timestamp", "device_id", "lane",
                                                "evidence", "confidence", "proposed_action",
                                                "decision", "outcome",
                                                "verification_note"]),
            outbox=[outbox[n] for n in s["outbox"]],
        ))
    return dict(stages=out)


def _rt_counts(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return {m.group(1): (int(m.group(2)), int(m.group(3)))
            for m in re.finditer(r"\*\*(\w+)\*\*: (\d+)/(\d+) cases passed", text)}


def results_data() -> dict:
    d = json.loads(RESULTS.read_text(encoding="utf-8"))["scores"]
    base, dem = d["baseline"], d["deming_rep0"]
    rows = [dict(key=k, label=lbl, baseline=base["all"][k], deming=dem["all"][k])
            for k, lbl in METRICS]
    wins = []
    for g in sorted(k for k in base if k.startswith("group:")):
        for k, lbl in METRICS:
            b, m = base[g].get(k), dem.get(g, {}).get(k)
            if b is not None and m is not None and b > m:
                wins.append(dict(group=g[6:], metric=lbl, n=base[g]["n"], baseline=b, deming=m))
    before, after = _rt_counts(RT_BEFORE), _rt_counts(RT_AFTER)
    return dict(
        source=str(RESULTS.relative_to(REPO)).replace("\\", "/"),
        n=base["all"]["n"], unverified_n=base["unverified"]["n"],
        rows=rows, baseline_wins=wins,
        deming_unknown_rate=dem["all"]["unknown_rate"],
        redteam=dict(before=before, after=after,
                     sources=[str(p.relative_to(REPO)).replace("\\", "/")
                              for p in (RT_BEFORE, RT_AFTER)],
                     open_findings=[dict(id=i, case=c, text=t) for i, c, t in OPEN_FINDINGS]),
    )


def build() -> str:
    data = dict(demo=demo_data(), results=results_data(), repo=REPO_URL, readme=README_URL)
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    template = (REPO / "scripts" / "demo_page_template.html").read_text(encoding="utf-8")
    return template.replace("/*__DATA__*/null", blob)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    html = build()
    if a.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == html
        print("up to date" if ok else "OUT OF DATE: run python scripts/build_demo_page.py")
        return 0 if ok else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8", newline="\n")
    (REPO / "docs" / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
