"""Blind AI cross-check: compare an AI labeller's blind worksheet with the DRAFT ground truth.

This is an adapter around eval/blind/agreement.py (which is not edited). It makes NO LLM calls
and never writes to data/ or to the verified_by_a / verified_by_b columns.

Two steps:

  # 1. network: fetch each AI source URL once (polite delay) and check the quoted strings
  python eval/blind/cross_check.py fetch eval/blind/external/blind_ai_claude.csv

  # 2. offline: compare and write docs/ai-cross-check.md
  python eval/blind/cross_check.py report eval/blind/external/blind_ai_claude.csv

Column mapping for the AI file (adapter): `comment` -> reason, `source_url_used` -> source URL,
`notes` -> extra notes. The worksheet columns (blind_id, labeller, vendor, product, version,
lane) are read as agreement.py reads them.
"""
from __future__ import annotations

import argparse
import csv
import html
import math
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "eval", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import agreement  # noqa: E402  (eval/blind/agreement.py, reused as is)
from offline_analysis import alias_match  # noqa: E402  (same POST-HOC alias table)

REQUIRED = ("blind_id", "labeller", "vendor", "product", "version", "lane")
# Adapter: AI-file column -> our name. Each tuple lists accepted header spellings in order.
OPTIONAL = {"reason": ("comment", "reason"),
            "source_url": ("source_url_used", "source_url", "url"),
            "notes": ("notes",)}
CHECKS_CSV = HERE / "external" / "source_checks.csv"
CHECK_COLS = ("blind_id", "url", "http_status", "page_status", "claim", "claim_found", "checked_at")
NEEDS_HUMAN = "needs human check in a browser"
USER_AGENT = "Mozilla/5.0 (compatible; deming-crosscheck/0.1)"


# ---------------------------------------------------------------- adapter

def read_ai(path: Path) -> tuple[list[dict], dict[str, str]]:
    """Read the AI worksheet. Returns rows (with reason/source_url/notes keys) and the column
    mapping actually used, so the report can say which columns were mapped."""
    rows = agreement.read_csv(path)
    header = list(rows[0].keys()) if rows else []
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise ValueError(f"{path}: missing required column(s) {missing}; header is {header}")
    used: dict[str, str] = {}
    for ours, options in OPTIONAL.items():
        used[ours] = next((o for o in options if o in header), "")
    out = []
    for r in rows:
        r = dict(r)
        for ours, col in used.items():
            r[ours] = r.get(col, "") if col else ""
        out.append(r)
    return out, used


# ---------------------------------------------------------------- metrics

def kappa_se(po: float, pe: float, n: int) -> float | None:
    """Approximate SE of Cohen's kappa, sqrt(po(1-po) / (n(1-pe)^2)) (McHugh 2012).
    Large-sample formula: at small n it is only a rough guide."""
    if n == 0 or pe >= 1:
        return None
    return math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))


def lane_metrics(ai_lanes: list[str], truth_lanes: list[str]) -> dict:
    n = len(ai_lanes)
    agree = sum(a == b for a, b in zip(ai_lanes, truth_lanes))
    po = agree / n if n else 0.0
    from collections import Counter
    ca, cb = Counter(ai_lanes), Counter(truth_lanes)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n) if n else 0.0
    k = agreement.cohen_kappa(ai_lanes, truth_lanes)
    se = kappa_se(po, pe, n)
    ci = None if k is None or se is None else (max(-1.0, k - 1.96 * se), min(1.0, k + 1.96 * se))
    return {"n": n, "agree": agree, "po": po, "pe": pe, "kappa": k, "se": se, "ci": ci,
            "ai_counts": dict(ca), "truth_counts": dict(cb)}


# Severity of a lane disagreement (lower = more severe). Not a judgement of who is right.
#  1: one side says fine, the other says patch/retire: if `fine` is wrong, a device that needs
#     action gets none.
#  2: patch vs retire: both act, but the owner action differs (update vs replace).
#  3: one side says unknown: the device goes to a human either way.
#  4: lane agrees, but vendor/product/version differ even after the post-hoc alias view.
def severity(ai_lane: str, truth_lane: str, lane_agree: bool) -> int:
    if lane_agree:
        return 4
    pair = {ai_lane, truth_lane}
    if "unknown" in pair:
        return 3
    if "fine" in pair:
        return 1
    return 2


SEVERITY_TEXT = {1: "fine vs action", 2: "patch vs retire", 3: "unknown vs decided",
                 4: "identity only, lane agrees"}


def compare(ai_rows: list[dict], key_rows: list[dict], gt_rows: list[dict],
            lc_rows: list[dict]) -> list[dict]:
    gt = {r["device_id"]: r for r in gt_rows}
    lc = {r["lifecycle_id"]: r for r in lc_rows}
    blind_to_dev = {k["blind_id"]: k["device_id"] for k in key_rows}
    out = []
    for r in ai_rows:
        did = blind_to_dev.get(r["blind_id"])
        if did is None or did not in gt:
            raise ValueError(f"{r['blind_id']}: not in blind key / ground truth")
        t = gt[did]
        exact = {f: agreement.norm(f, r.get(f, "")) == agreement.norm(f, t.get(f, ""))
                 for f in ("vendor", "product", "version", "lane")}
        al = alias_match(t, r)
        lane_ok = exact["lane"]
        ids = [x for x in (t.get("evidence_lifecycle_id") or "").split(";") if x]
        # A `fine` label carries no evidence id; its note may still name the lifecycle row.
        ids += [x for x in re.findall(r"\bLC-\d{3}\b", t.get("source_row_note") or "") if x not in ids]
        out.append({
            "blind_id": r["blind_id"], "device_id": did, "device_name_raw": r.get("device_name_raw", ""),
            "firmware_version_raw": r.get("firmware_version_raw", ""),
            "ai": {f: r.get(f, "") for f in ("vendor", "product", "version", "lane")},
            "truth": {f: t.get(f, "") for f in ("vendor", "product", "version", "lane")},
            "exact": exact,
            "alias_vendor": al["vendor"], "alias_product": al["product"],
            "ai_reason": r.get("reason", ""), "ai_notes": r.get("notes", ""),
            "ai_source_url": r.get("source_url", ""),
            "truth_cve": t.get("evidence_cve", ""), "truth_lc": ";".join(ids),
            "truth_lc_urls": [lc[i]["source_url"] for i in ids if i in lc and lc[i].get("source_url")],
            "truth_note": t.get("source_row_note", ""),
            "severity": severity(agreement.norm("lane", r.get("lane", "")), t.get("lane", ""), lane_ok),
            "identity_disagree": not (exact["version"] and al["vendor"] and al["product"]),
        })
    return out


# ---------------------------------------------------------------- source claims

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
_MON = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
_MON.update({m: i + 1 for i, m in enumerate(MONTHS)})
_MON_RE = "|".join(sorted(_MON, key=len, reverse=True))

DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(rf"\b({_MON_RE})\.? (\d{{1,2}}),? (\d{{4}})\b", re.I),
     lambda m: (int(m[3]), _MON[m[1].lower()], int(m[2]))),
    (re.compile(rf"\b(\d{{1,2}}) ({_MON_RE})\.? (\d{{4}})\b", re.I),
     lambda m: (int(m[3]), _MON[m[2].lower()], int(m[1]))),
    # US style, as D-Link writes it (MM/DD/YYYY)
    (re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"), lambda m: (int(m[3]), int(m[1]), int(m[2]))),
]
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
# A range such as "12.0-12.11.3" yields both ends.
VERSION_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)+(?:-h\d+|R\d+(?:\.\d+)?)?(?![\w.])")
QUOTED_RE = re.compile(r'"([^"]{6,})"')


def date_variants(y: int, m: int, d: int) -> list[str]:
    try:
        dt = date(y, m, d)
    except ValueError:
        return []
    full, short = MONTHS[m - 1].capitalize(), MONTHS[m - 1][:3].capitalize()
    return [dt.isoformat(), f"{full} {d}, {y}", f"{short} {d}, {y}", f"{short}. {d}, {y}",
            f"{d} {full} {y}", f"{d} {short} {y}", f"{d:02d} {full} {y}", f"{d:02d} {short} {y}",
            f"{d}-{short}-{y}", f"{d:02d}-{short}-{y}", f"{m:02d}/{d:02d}/{y}", f"{d:02d}/{m:02d}/{y}",
            f"{m}/{d}/{y}", f"{full} {d:02d}, {y}"]


def extract_claims(reason: str, notes: str = "", own_version: str = "") -> list[dict]:
    """Checkable strings the AI quoted: dates, versions and CVE ids in the reason, plus any
    double-quoted phrase in the reason or notes. The device's own firmware (`own_version`) comes
    from the blind prompt, not from the source, so it is a claim only when the reason names
    nothing else. Each claim has `text` and `variants`."""
    claims: list[dict] = []
    seen: set[str] = set()

    skip = (own_version or "").strip().lower()

    def add(text: str, variants: list[str]) -> None:
        if text.lower() != skip and text.lower() not in seen:
            seen.add(text.lower())
            claims.append({"text": text, "variants": variants or [text]})

    rest = reason or ""
    for rx, parse in DATE_PATTERNS:
        for m in rx.finditer(rest):
            add(m[0], [m[0], *date_variants(*parse(m))])
        rest = rx.sub(" ", rest)
    for m in CVE_RE.finditer(rest):
        add(m[0].upper(), [m[0].upper()])
    rest = CVE_RE.sub(" ", rest)
    for m in VERSION_RE.finditer(rest):
        add(m[0], [m[0]])
    for src in (reason or "", notes or ""):
        for m in QUOTED_RE.finditer(src):
            add(m[1], [m[1]])
    if not claims and skip and skip in (reason or "").lower():
        # Nothing else to check: the page must at least mention the device's version.
        claims.append({"text": own_version.strip(), "variants": [own_version.strip()]})
    return claims


def page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", raw).strip()


def claim_found(text: str, claim: dict) -> bool:
    low = text.lower()
    return any(re.sub(r"\s+", " ", v).lower() in low for v in claim["variants"])


def classify(status: int | None, text: str, raw: str) -> str:
    if status is None:
        return "error"
    if status in (401, 403, 429) or status >= 500:
        return NEEDS_HUMAN
    if status >= 400:
        return f"http {status}"
    js_note = re.search(r"enable javascript|requires javascript|javascript is (disabled|required)", text, re.I)
    if len(text) < 400 or (js_note and len(text) < 3000):
        return NEEDS_HUMAN  # little or no server-rendered text: JS-rendered or a challenge page
    return "opened"


def fetch(url: str, timeout: int = 25) -> tuple[int | None, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(5_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # network error, TLS, timeout
        return None, f"{type(e).__name__}: {e}"


def run_fetch(ai_rows: list[dict], out: Path, delay: float = 3.0, fetcher=fetch) -> list[dict]:
    """Fetch each distinct URL once, check every row's claims against it, write `out`."""
    pages: dict[str, tuple[int | None, str, str]] = {}
    rows: list[dict] = []
    for r in ai_rows:
        url = (r.get("source_url") or "").strip()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        claims = extract_claims(r.get("reason", ""), r.get("notes", ""), r.get("firmware_version_raw", ""))
        if not url:
            rows.append({"blind_id": r["blind_id"], "url": "", "http_status": "", "page_status": "missing",
                         "claim": "", "claim_found": "", "checked_at": now})
            continue
        if url not in pages:
            if pages:
                time.sleep(delay)
            status, raw = fetcher(url)
            text = page_text(raw) if status else ""
            pages[url] = (status, text, classify(status, text, raw))
        status, text, ps = pages[url]
        for c in claims or [None]:
            found = "" if c is None or ps != "opened" else str(claim_found(text, c)).lower()
            rows.append({"blind_id": r["blind_id"], "url": url, "http_status": "" if status is None else status,
                         "page_status": ps, "claim": "" if c is None else c["text"],
                         "claim_found": found, "checked_at": now})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CHECK_COLS)
        w.writeheader()
        w.writerows(rows)
    return rows


def source_summary(check_rows: list[dict]) -> dict[str, dict]:
    """Per blind_id: page status, claims found / checked, and whether the claim is supported.
    Supported = page opened AND at least one checkable string AND every string found."""
    by: dict[str, dict] = {}
    for r in check_rows:
        s = by.setdefault(r["blind_id"], {"url": r["url"], "http_status": r["http_status"],
                                          "page_status": r["page_status"], "claims": [], "missing": []})
        if r["claim"]:
            s["claims"].append(r["claim"])
            if r["claim_found"] != "true":
                s["missing"].append(r["claim"])
    for s in by.values():
        opened = s["page_status"] == "opened"
        s["supported"] = opened and bool(s["claims"]) and not s["missing"]
        if not s["url"]:
            s["verdict"] = "no source: unsupported"
        elif not opened:
            s["verdict"] = f"{s['page_status']}: unsupported until checked"
        elif not s["claims"]:
            s["verdict"] = "opened; no date/version string to check: unsupported"
        elif s["missing"]:
            s["verdict"] = "opened; not found on page: " + "; ".join(s["missing"])
        else:
            s["verdict"] = f"opened; all {len(s['claims'])} quoted string(s) found"
    return by


# ---------------------------------------------------------------- report

def _yn(b: bool) -> str:
    return "yes" if b else "**no**"


def _cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def render(cmp: list[dict], lm: dict, src: dict[str, dict], used: dict[str, str],
           ai_path: str, labeller: str) -> str:
    k = "n/a" if lm["kappa"] is None else f"{lm['kappa']:.2f}"
    ci = "n/a" if lm["ci"] is None else f"{lm['ci'][0]:.2f} to {lm['ci'][1]:.2f}"
    n = lm["n"]
    ex = {f: sum(c["exact"][f] for c in cmp) for f in ("vendor", "product", "version")}
    al_v = sum(c["alias_vendor"] for c in cmp)
    al_p = sum(c["alias_product"] for c in cmp)
    sup = sum(src.get(c["blind_id"], {}).get("supported", False) for c in cmp)
    L = [
        "# AI cross-check of the draft labels (blind, n=15)",
        "",
        "> **This is NOT human verification.** A separate Claude Code session (labeller "
        f"`{labeller}`) labelled 15 devices blind, from the device name and firmware only. It is "
        "the same model family that helped draft the labels and the code, so the two share blind "
        "spots that this check cannot reveal. Some of its sources are third-party trackers or "
        "search excerpts, which it says in its notes. The draft ground truth stays unverified: "
        "`verified_by_a` / `verified_by_b` are untouched, and no label was changed.",
        "",
        f"Generated by `python eval/blind/cross_check.py report {ai_path}` (no LLM calls). "
        "Source checks come from `eval/blind/external/source_checks.csv`, written by the "
        "`fetch` step (one request per distinct URL, 3 s apart).",
        "",
        "## Lane agreement with the draft labels",
        "",
        f"- Percent agreement: **{lm['agree']}/{n} = {lm['po']:.0%}**",
        f"- Cohen's kappa: **{k}** (chance agreement p_e = {lm['pe']:.2f}); approximate 95% CI "
        f"{ci} using SE = sqrt(p_o(1-p_o) / (n(1-p_e)^2)) (McHugh 2012).",
        f"- **n = {n} is tiny.** McHugh suggests at least 30 comparisons; the CI is a large-sample "
        "approximation and is only a rough guide here. One device more or less in agreement "
        "moves percent agreement by about 7 points. Treat these numbers as a description of "
        "this sample, not an estimate of label quality.",
        "- Lane counts, AI: " + ", ".join(f"{x} {lm['ai_counts'].get(x, 0)}" for x in agreement.LANES)
        + "; draft: " + ", ".join(f"{x} {lm['truth_counts'].get(x, 0)}" for x in agreement.LANES) + ".",
        "",
        "Identity fields (same 15 devices):",
        "",
        "| Field | Exact (trim, case-insensitive; version drops a leading `v`) | POST-HOC alias view |",
        "|---|---|---|",
        f"| vendor | {ex['vendor']}/{n} | {al_v}/{n} |",
        f"| product | {ex['product']}/{n} | {al_p}/{n} |",
        f"| version | {ex['version']}/{n} | (not aliased) |",
        "",
        "The alias view is the `ALIASES` table from `eval/offline_analysis.py`, unchanged. It was "
        "defined after seeing the main evaluation results (POST-HOC) and was not extended for "
        "this check.",
        "",
        f"AI claims backed by a source that opened and contained every quoted date/version string: "
        f"**{sup}/{n}**. A claim without a working source counts as unsupported.",
        "",
        "## Per device",
        "",
        "| Blind | Device | AI lane | Draft lane | Lane | Vendor exact | Product exact | Product alias | "
        "Version exact | AI source | Source check |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cmp:
        s = src.get(c["blind_id"], {"verdict": "not fetched: unsupported", "url": c["ai_source_url"]})
        L.append(
            f"| {c['blind_id']} | {c['device_id']} | {c['ai']['lane']} | {c['truth']['lane']} | "
            f"{'agree' if c['exact']['lane'] else '**differ**'} | {_yn(c['exact']['vendor'])} | "
            f"{_yn(c['exact']['product'])} | {_yn(c['alias_product'])} | {_yn(c['exact']['version'])} | "
            f"{'present' if c['ai_source_url'] else '**missing**'} | {_cell(s['verdict'])} |")
    L += ["", "Products where the two sides differ:", "",
          "| Blind | AI product | Draft product |", "|---|---|---|"]
    for c in cmp:
        if not c["exact"]["product"]:
            L.append(f"| {c['blind_id']} | {_cell(c['ai']['product'])} | {_cell(c['truth']['product'])} |")

    dis = sorted([c for c in cmp if c["severity"] < 4 or c["identity_disagree"]],
                 key=lambda c: (c["severity"], c["blind_id"]))
    L += ["", "## Disagreements, most severe first (triage only; nobody here decides who is right)", "",
          "Severity: 1 = one side says `fine`, the other says act; 2 = `patch` vs `retire`; "
          "3 = one side says `unknown`; 4 = lanes agree but vendor/product/version differ even "
          "in the alias view.", ""]
    for c in dis:
        s = src.get(c["blind_id"], {})
        what = (f"lane AI `{c['ai']['lane']}` vs draft `{c['truth']['lane']}`" if c["severity"] < 4
                else f"product AI \"{c['ai']['product']}\" vs draft \"{c['truth']['product']}\"")
        if c["severity"] < 4 and c["identity_disagree"]:
            what += f"; product AI \"{c['ai']['product']}\" vs draft \"{c['truth']['product']}\""
        opens = [u for u in [c["ai_source_url"], *c["truth_lc_urls"]] if u]
        opens = list(dict.fromkeys(opens))
        L += [
            f"### {c['blind_id']} / {c['device_id']}: severity {c['severity']} ({SEVERITY_TEXT[c['severity']]})",
            "",
            f"- Device: \"{_cell(c['device_name_raw'])}\", firmware `{c['firmware_version_raw'] or '(blank)'}`.",
            f"- Disagreement: {what}.",
            f"- AI says: {_cell(c['ai_reason'])}. Notes: {_cell(c['ai_notes']) or '(none)'}",
            f"- AI cites: {c['ai_source_url'] or '(no URL)'}; source check: {s.get('verdict', 'not fetched')}.",
            f"- Draft says: {_cell(c['truth_note'])}",
            f"- Draft cites: CVE {c['truth_cve'] or '(none)'}; lifecycle row(s) {c['truth_lc'] or '(none)'}"
            + (f" ({'; '.join(c['truth_lc_urls'])})" if c["truth_lc_urls"] else "") + ".",
            "- A human must open: " + (" and ".join(opens) if opens else "(no URL on either side)")
            + ", and decide from what those pages say for this exact model and firmware.",
            "",
        ]
    weak = [c for c in cmp if c["severity"] == 4 and not c["identity_disagree"]
            and src.get(c["blind_id"]) and not src[c["blind_id"]]["supported"]]
    if weak:
        L += ["## Lanes agree, but the AI's cited source did not back every string", "",
              "Listed for a human to look at; the lane is not in dispute.", ""]
        for c in weak:
            L.append(f"- {c['blind_id']} / {c['device_id']}: {src[c['blind_id']]['verdict']} "
                     f"({c['ai_source_url']}). AI notes: {_cell(c['ai_notes']) or '(none)'} "
                     f"Draft note: {_cell(c['truth_note'])}")
        L.append("")
    n_human = sum(v["page_status"] == NEEDS_HUMAN for v in src.values())
    L += [
        "## Caveats",
        "",
        "- **Same-model-family cross-check.** The labeller is a Claude session; the draft labels "
        "and this code were also written with Claude. Agreement can come from a shared mistake, "
        "so a high number here is weak evidence. It can find disagreements worth a human's time; "
        "it cannot confirm a label.",
        "- **Third-party sources.** Several AI notes say a date came from third-party trackers or "
        "search excerpts because the vendor page would not render (B01, B09, B11, B13).",
        "- **Automatic source check is literal.** It looks for the dates, versions, CVE ids and "
        "quoted phrases from the AI's reason (and quoted phrases from its notes) in the page text, "
        "with common date spellings. A miss can mean the page says it differently, renders the "
        "text with JavaScript, or does not say it. A hit only means the string is on the page, "
        "not that the page says it about this model: the AI's own notes say B13's page is about "
        "the sibling USG60W and B12's is a D-Link Croatia page. The device's own firmware is not "
        "counted as a claim unless the reason names nothing else (B10). Pages that returned "
        "401/403/429/5xx or almost no text are marked \"needs human check in a browser\" "
        f"({n_human} in this run).",
        "- **Not human verification.** Labels count as verified only with two human reviewers' "
        "initials (`docs/ai-and-teamwork.md`). This check does not change that.",
        "",
        "## Input columns",
        "",
        f"File `{ai_path}`. Worksheet columns read as `agreement.py` reads them: "
        f"{', '.join(REQUIRED)}. Adapter mapping (by header name, nothing guessed by position): "
        + ", ".join(f"`{v}` → {k}" if v else f"{k}: not present" for k, v in used.items()) + ". "
        "Extra columns `device_name_raw` and `firmware_version_raw` are the blind prompt, shown in "
        "the triage lines.",
        "",
        "## Sources for the method",
        "",
        "- McHugh ML. Interrater reliability: the kappa statistic. Biochem Med 2012;22(3):276-82. "
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC3900052 (report both percent agreement and kappa; "
        "SE and CI formula; at least 30 comparisons).",
        "",
    ]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("fetch", "report"))
    ap.add_argument("ai_file", type=Path)
    ap.add_argument("--key", type=Path, default=HERE / "blind_key.csv")
    ap.add_argument("--ground-truth", type=Path, default=ROOT / "data/ground_truth.csv")
    ap.add_argument("--lifecycle", type=Path, default=ROOT / "data/lifecycle.csv")
    ap.add_argument("--checks", type=Path, default=CHECKS_CSV)
    ap.add_argument("--out", type=Path, default=ROOT / "docs/ai-cross-check.md")
    ap.add_argument("--delay", type=float, default=3.0)
    a = ap.parse_args(argv)

    ai_rows, used = read_ai(a.ai_file)
    if a.step == "fetch":
        rows = run_fetch(ai_rows, a.checks, delay=a.delay)
        for r in rows:
            print(f"{r['blind_id']} {r['page_status']:<32} {r['claim'][:40]:<40} {r['claim_found']}")
        return 0

    cmp = compare(ai_rows, agreement.read_csv(a.key), agreement.read_csv(a.ground_truth),
                  agreement.read_csv(a.lifecycle))
    lm = lane_metrics([c["ai"]["lane"].strip().lower() for c in cmp], [c["truth"]["lane"] for c in cmp])
    src = source_summary(agreement.read_csv(a.checks)) if a.checks.exists() else {}
    labeller = ai_rows[0].get("labeller", "") if ai_rows else ""
    try:
        shown = a.ai_file.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown = a.ai_file.as_posix()
    a.out.write_text(render(cmp, lm, src, used, shown, labeller), encoding="utf-8")
    kap = "n/a" if lm["kappa"] is None else f"{lm['kappa']:.2f}"
    print(f"lane agreement {lm['agree']}/{lm['n']} = {lm['po']:.0%}; kappa {kap}; wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
