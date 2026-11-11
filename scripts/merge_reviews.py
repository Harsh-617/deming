"""Merge two reviewers' exports from review/review.html into data/ground_truth.reviewed.csv.

  python scripts/merge_reviews.py review_A.csv review_B.csv

The first file fills verified_by_a, the second verified_by_b, and ONLY on rows where that
reviewer chose "verified" (the value written is the reviewer field of the export: their
initials). Every other column is copied unchanged from data/ground_truth.csv, which is never
overwritten. Rows where either reviewer chose disagree or unsure, left the decision blank, or the
two reviewers differ are listed in docs/label-disagreements.md with both reviewers' notes.

Checks: exact export header (device_id,reviewer,decision,notes), one non-blank reviewer per
file, two different reviewers, known device_ids, no duplicate rows, decisions in
verified|disagree|unsure|blank. Anything else stops the merge with an error.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_HEADER = ["device_id", "reviewer", "decision", "notes"]
DECISIONS = {"verified", "disagree", "unsure", ""}


class MergeError(ValueError):
    pass


def read_review(path: Path, known_ids: set[str]) -> tuple[str, dict[str, dict]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if list(reader.fieldnames or []) != EXPORT_HEADER:
            raise MergeError(f"{path}: header must be {','.join(EXPORT_HEADER)}, got {reader.fieldnames}")
        rows = list(reader)
    reviewers = {(r["reviewer"] or "").strip() for r in rows}
    if len(reviewers) != 1 or "" in reviewers:
        raise MergeError(f"{path}: expected exactly one non-blank reviewer, got {sorted(reviewers)}")
    out: dict[str, dict] = {}
    for i, r in enumerate(rows, 2):
        did = (r["device_id"] or "").strip()
        dec = (r["decision"] or "").strip().lower()
        if did not in known_ids:
            raise MergeError(f"{path}:{i}: unknown device_id {did!r}")
        if did in out:
            raise MergeError(f"{path}:{i}: duplicate row for {did}")
        if dec not in DECISIONS:
            raise MergeError(f"{path}:{i}: decision {r['decision']!r} is not verified|disagree|unsure|blank")
        out[did] = {"decision": dec, "notes": (r["notes"] or "").strip()}
    return reviewers.pop(), out


def merge(gt_rows: list[dict], a: tuple[str, dict], b: tuple[str, dict]) -> tuple[list[dict], list[dict]]:
    """Returns (reviewed ground-truth rows, rows needing discussion)."""
    (who_a, rev_a), (who_b, rev_b) = a, b
    if who_a.casefold() == who_b.casefold():
        raise MergeError(f"both files are from reviewer {who_a!r}; two different reviewers are required")
    merged, issues = [], []
    for g in gt_rows:
        row = dict(g)
        da = rev_a.get(g["device_id"], {"decision": "", "notes": ""})
        db = rev_b.get(g["device_id"], {"decision": "", "notes": ""})
        if da["decision"] == "verified":
            row["verified_by_a"] = who_a
        if db["decision"] == "verified":
            row["verified_by_b"] = who_b
        merged.append(row)
        if not (da["decision"] == db["decision"] == "verified"):
            issues.append({"device_id": g["device_id"], "lane": g["lane"], "label": g,
                           "a": da, "b": db})
    return merged, issues


def _md(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ") or "-"


def render_disagreements(issues: list[dict], who_a: str, who_b: str, total: int,
                         sources: tuple[str, str]) -> str:
    both = total - len(issues)
    def count(pred):
        return sum(1 for i in issues if pred(i))
    lines = [
        "# Label disagreements",
        "",
        f"Merged by `scripts/merge_reviews.py` from `{sources[0]}` (reviewer A: {who_a}) and "
        f"`{sources[1]}` (reviewer B: {who_b}). Output: `data/ground_truth.reviewed.csv`; "
        "`data/ground_truth.csv` is unchanged.",
        "",
        f"- Verified by both: {both} of {total}.",
        f"- Listed below: {len(issues)} (any row not verified by both).",
        f"- A disagree: {count(lambda i: i['a']['decision'] == 'disagree')}, "
        f"B disagree: {count(lambda i: i['b']['decision'] == 'disagree')}.",
        f"- A unsure: {count(lambda i: i['a']['decision'] == 'unsure')}, "
        f"B unsure: {count(lambda i: i['b']['decision'] == 'unsure')}.",
        f"- Undecided (blank) by A: {count(lambda i: not i['a']['decision'])}, "
        f"by B: {count(lambda i: not i['b']['decision'])}.",
        f"- Reviewers chose differently: {count(lambda i: i['a']['decision'] != i['b']['decision'])}.",
        "",
        "Rows here stay unverified for that reviewer. Fix a label only on `main`, then re-review it.",
        "",
    ]
    if issues:
        lines += ["| Device | Label | A decision | A notes | B decision | B notes |",
                  "|---|---|---|---|---|---|"]
        for i in issues:
            g = i["label"]
            label = f"{g['lane']}: {g['vendor']} / {g['product']} {g['version']}".strip()
            lines.append(f"| {i['device_id']} | {_md(label)} | {i['a']['decision'] or '(blank)'} | "
                         f"{_md(i['a']['notes'])} | {i['b']['decision'] or '(blank)'} | {_md(i['b']['notes'])} |")
    else:
        lines.append("No disagreements: every row was verified by both reviewers.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("review_a", type=Path, help="reviewer A's export (fills verified_by_a)")
    ap.add_argument("review_b", type=Path, help="reviewer B's export (fills verified_by_b)")
    ap.add_argument("--ground-truth", type=Path, default=ROOT / "data" / "ground_truth.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "ground_truth.reviewed.csv")
    ap.add_argument("--disagreements", type=Path, default=ROOT / "docs" / "label-disagreements.md")
    a = ap.parse_args(argv)
    if a.out.resolve() == a.ground_truth.resolve():
        print("error: --out must not be the original ground truth file", file=sys.stderr)
        return 2
    with a.ground_truth.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        gt_rows = list(reader)
    for col in ("device_id", "verified_by_a", "verified_by_b"):
        if col not in header:
            print(f"error: {a.ground_truth} has no {col} column", file=sys.stderr)
            return 2
    ids = {r["device_id"] for r in gt_rows}
    try:
        ra = read_review(a.review_a, ids)
        rb = read_review(a.review_b, ids)
        merged, issues = merge(gt_rows, ra, rb)
    except MergeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(merged)
    a.disagreements.parent.mkdir(parents=True, exist_ok=True)
    a.disagreements.write_text(render_disagreements(issues, ra[0], rb[0], len(gt_rows),
                                                    (a.review_a.name, a.review_b.name)), encoding="utf-8")
    print(f"{len(gt_rows) - len(issues)} of {len(gt_rows)} rows verified by both; "
          f"{len(issues)} listed in {a.disagreements}. Wrote {a.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
