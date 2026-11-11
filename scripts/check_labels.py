"""Mechanical checks on the human ground-truth labels (no LLM calls, read-only on data/).

Checks data/ground_truth.csv against data/inventory.csv, data/lifecycle.csv and
data/feeds/kev.json, as of data/ground_truth_meta.json:

1. every evidence CVE exists in kev.json and its vendorProject/product equals the label's;
2. every evidence lifecycle_id exists, its vendor/product equals the label's, and its
   model_pattern fits the device;
3. the lane is recomputed from the label's fields with the contract tie-break
   (unknown, retire, patch, fine) and any disagreement is flagged; it is recomputed a second time
   with the inventory's raw firmware, which is what the Checker's version guard compares;
4. version comparisons use the shared parser in sim/guards.py; firmware that doesn't parse is
   flagged;
5. each source URL is fetched once (polite delay). The HTTP status is recorded and, for text
   pages, whether the label's fixed_version, support date and quoted phrases appear on it.
   Blocked pages (401/403/429) get "needs human check in a browser", never "ok".

Writes docs/label-check-report.md (human report) and review/label_checks.json (machine-readable,
read by scripts/build_review_page.py; it also caches the URL results for --offline).

Run:
  python scripts/check_labels.py              # fetch URLs (about 2 s per URL)
  python scripts/check_labels.py --offline    # reuse URL results cached in review/label_checks.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim.guards import compare_versions, parse_version, select_train_fixes  # noqa: E402
from sim.retrieval import is_software_row, pattern_matches, pattern_specificity  # noqa: E402

LANES = ("patch", "retire", "fine", "unknown")
USER_AGENT = "deming-label-check/1.0 (hackathon label verification; one request per URL)"
DEFAULT_DELAY = 2.0
MAX_BYTES = 4_000_000
BLOCKED = {401, 403, 429}
HUMAN_BROWSER = "needs human check in a browser"
# KEV requiredAction text that says the product itself is end of life (contract: a KEV entry with
# no fix whose required action is to stop using the product -> retire). Not plain "discontinue":
# nearly every KEV entry says "... or discontinue use of the product if mitigations are unavailable".
_KEV_EOL = re.compile(r"end[- ]of[- ](life|service)|\beol\b|\beos\b|legacy|no longer supported",
                      re.IGNORECASE)
# 'quoted phrase' in a note: opening quote after start/space/(/:, closing quote before space/punct.
_QUOTE = re.compile(r"(?:^|(?<=[\s(:]))'([^'\s][^']{3,}?[^'\s])'(?=[\s.,;:)]|$)")
_URL = re.compile(r"https://[^\s,;)\"']+")

# Severity for ordering (higher = review first).
SEVERITY = {"lane_mismatch": 3, "evidence": 3, "firmware": 2, "firmware_parse": 1, "pattern": 1,
            "source": 1, "info": 0}


# ---------------------------------------------------------------- loading

def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(f)]


def load_inputs(root: Path = ROOT) -> dict:
    data = root / "data"
    kev = json.loads((data / "feeds" / "kev.json").read_text(encoding="utf-8"))["vulnerabilities"]
    review_path = root / "docs" / "label-review.csv"
    return {
        "gt": read_csv(data / "ground_truth.csv"),
        "inventory": {r["device_id"]: r for r in read_csv(data / "inventory.csv")},
        "lifecycle": read_csv(data / "lifecycle.csv"),
        "kev": {v["cveID"]: v for v in kev},
        "as_of": dt.date.fromisoformat(
            json.loads((data / "ground_truth_meta.json").read_text(encoding="utf-8"))["as_of_date"]),
        "review_urls": ({r["device_id"]: [u for u in r.get("source_url", "").split(";") if u]
                         for r in read_csv(review_path)} if review_path.exists() else {}),
    }


def _same(a: str | None, b: str | None) -> bool:
    return bool((a or "").strip()) and (a or "").strip().casefold() == (b or "").strip().casefold()


# ---------------------------------------------------------------- lifecycle row selection

def _name_suffixes(name: str) -> list[str]:
    """Every suffix of the raw name that starts at a word: 'Cisco RV320 router' ->
    ['cisco rv320 router', 'rv320 router', 'router']. Hardware globs (RV32*, XG *) are tested
    against these, which is how a model number inside free text is found."""
    words = (name or "").split()
    return [" ".join(words[i:]) for i in range(len(words))]


def row_fits(row: dict, label: dict, inv: dict) -> bool | None:
    """Does the lifecycle row's model_pattern fit this device? Uses sim.retrieval.pattern_matches.
    True / False, or None when the pattern is blank (whole product) or nothing can be tested."""
    if not (row.get("model_pattern") or "").strip():
        return None
    if is_software_row(row):
        return pattern_matches(row, {"version": label.get("version"),
                                     "firmware_version_raw": inv.get("firmware_version_raw")})
    results = [pattern_matches(row, {"product": label.get("product"), "model": s})
               for s in _name_suffixes(inv.get("device_name_raw", "")) or [""]]
    if any(r is True for r in results):
        return True
    return False if any(r is False for r in results) else None


def find_lifecycle_row(label: dict, inv: dict, rows: list[dict]) -> dict | None:
    """The governing row for the label's vendor/product: the most specific row whose pattern fits
    (non-blank beats blank; then most literal characters, sim.retrieval.pattern_specificity)."""
    best = None
    for r in rows:
        if not (_same(r["vendor"], label["vendor"]) and _same(r["product"], label["product"])):
            continue
        fit = row_fits(r, label, inv)
        if fit is False or (fit is None and (r.get("model_pattern") or "").strip()):
            continue
        key = (1 if fit else 0, pattern_specificity(r.get("model_pattern", "")))
        if best is None or key > best[0]:
            best = (key, r)
    return best[1] if best else None


# ---------------------------------------------------------------- lane recompute

def recompute_lane(label: dict, row: dict | None, kev_entries: list[dict], as_of: dt.date,
                   version: str | None) -> tuple[str, str]:
    """Contract tie-break on the label's fields. Returns (lane, reason).

    1. identity incomplete (vendor or product blank) -> unknown
    2. governing row past last_security_support_date (or eol_date when blank) -> retire;
       KEV-listed with patch_available=false -> retire (no fix; stop using);
       KEV says the product is end of life and no fixed version is documented -> retire
    3. KEV-listed: needs a lifecycle row with a fixed_version on the version's train, and both
       versions must parse in the same family (sim.guards); below -> patch, at/above -> fine,
       anything else -> unknown (as the Checker's version guard does)
    4. otherwise -> fine
    """
    if not label.get("vendor", "").strip() or not label.get("product", "").strip():
        return "unknown", "identity incomplete (vendor or product blank)"
    if row:
        cutoff = row.get("last_security_support_date") or row.get("eol_date")
        if cutoff and dt.date.fromisoformat(cutoff) < as_of:
            which = "last_security_support_date" if row.get("last_security_support_date") else "eol_date"
            return "retire", f"{row['lifecycle_id']} {which} {cutoff} is before {as_of}"
        if kev_entries and (row.get("patch_available") or "").strip().lower() == "false":
            return "retire", f"in KEV and {row['lifecycle_id']} patch_available=false (no fix)"
    if not kev_entries:
        return "fine", "no KEV entry for this vendor/product and not past support"
    fixed = ((row or {}).get("fixed_version") or "").strip()
    if not fixed and any(_KEV_EOL.search(e.get("requiredAction", "")) for e in kev_entries):
        return "retire", "KEV requiredAction says the product is end of life; no fixed version"
    if not row:
        return "unknown", "in KEV but no lifecycle row (contract 1.4)"
    if not fixed:
        return "unknown", f"in KEV but {row['lifecycle_id']} has no fixed_version"
    version = (version or "").strip()
    if not version:
        return "unknown", "in KEV, version blank, so it can't be compared with the fix"
    train, why = select_train_fixes(fixed, version)
    if why:
        return "unknown", why
    if parse_version(version) is None:
        return "unknown", f"version {version!r} does not parse (sim.guards grammar)"
    bad = [f for f in train if compare_versions(version, f) is None]
    if bad:
        return "unknown", f"{version!r} and fixed {';'.join(bad)!r} are in different version families"
    below = {compare_versions(version, f) < 0 for f in train}
    if len(below) > 1:
        return "unknown", f"{version} is between fixed versions {';'.join(train)} on its train"
    if below == {True}:
        return "patch", f"{version} is below fixed {';'.join(train)} ({row['lifecycle_id']})"
    return "fine", f"{version} is at or above fixed {';'.join(train)} ({row['lifecycle_id']})"


# ---------------------------------------------------------------- per-device mechanical checks

def _finding(kind: str, text: str) -> dict:
    return {"kind": kind, "severity": SEVERITY[kind], "text": text}


def check_device(label: dict, inputs: dict) -> dict:
    did = label["device_id"]
    inv = inputs["inventory"].get(did)
    findings: list[dict] = []
    out = {"device_id": did, "findings": findings, "recomputed_lane": None, "recompute_reason": "",
           "firmware_lane": None, "firmware_reason": "", "governing_lifecycle_id": None}
    if inv is None:
        findings.append(_finding("evidence", f"{did} is in ground_truth.csv but not in inventory.csv"))
        return out
    lc_by = {r["lifecycle_id"]: r for r in inputs["lifecycle"]}
    kev = inputs["kev"]

    # 1. evidence CVEs
    cves = [c for c in label.get("evidence_cve", "").split(";") if c]
    for c in cves:
        e = kev.get(c)
        if e is None:
            findings.append(_finding("evidence", f"evidence {c} is not in kev.json"))
        elif not (_same(e["vendorProject"], label["vendor"]) and _same(e["product"], label["product"])):
            findings.append(_finding("evidence", (
                f"evidence {c} is KEV '{e['vendorProject']} / {e['product']}', but the label says "
                f"'{label['vendor']} / {label['product']}'")))

    # 2. lifecycle row
    cited_id = label.get("evidence_lifecycle_id", "").strip()
    cited = lc_by.get(cited_id) if cited_id else None
    if cited_id and cited is None:
        findings.append(_finding("evidence", f"evidence_lifecycle_id {cited_id} is not in lifecycle.csv"))
    if cited:
        if not (_same(cited["vendor"], label["vendor"]) and _same(cited["product"], label["product"])):
            findings.append(_finding("evidence", (
                f"{cited_id} is '{cited['vendor']} / {cited['product']}', but the label says "
                f"'{label['vendor']} / {label['product']}'")))
        fit = row_fits(cited, label, inv)
        if fit is False:
            target = "version" if is_software_row(cited) else "raw device name"
            findings.append(_finding("pattern", (
                f"{cited_id} model_pattern '{cited['model_pattern']}' does not match the {target}; "
                "the identity is a human reading of a messy name, check it")))
    found = find_lifecycle_row(label, inv, inputs["lifecycle"])
    row = cited or found
    out["governing_lifecycle_id"] = (row or {}).get("lifecycle_id")
    if cited and found and found["lifecycle_id"] != cited_id:
        findings.append(_finding("evidence", (
            f"label cites {cited_id}, but the most specific row for these fields is {found['lifecycle_id']}")))
    if not cited and found and label["lane"] in ("patch", "retire"):
        findings.append(_finding("evidence", f"lane {label['lane']} cites no lifecycle row; {found['lifecycle_id']} fits"))

    # 3. lane recompute: label version, then raw firmware (what the version guard compares)
    kev_entries = [e for e in kev.values()
                   if _same(e["vendorProject"], label["vendor"]) and _same(e["product"], label["product"])]
    lane, why = recompute_lane(label, row, kev_entries, inputs["as_of"], label.get("version"))
    out["recomputed_lane"], out["recompute_reason"] = lane, why
    if lane != label["lane"]:
        findings.append(_finding("lane_mismatch",
                                 f"label lane {label['lane']}, recomputed {lane}: {why}"))

    fw = (inv.get("firmware_version_raw") or "").strip()
    if fw:
        if parse_version(fw) is None:
            findings.append(_finding("firmware_parse", (
                f"firmware '{fw}' does not parse (sim.guards grammar)"
                + (f"; label version is '{label['version']}'" if label.get("version") else ""))))
        fw_lane, fw_why = recompute_lane(label, row, kev_entries, inputs["as_of"], fw)
        out["firmware_lane"], out["firmware_reason"] = fw_lane, fw_why
        if fw_lane != lane:
            findings.append(_finding("firmware", (
                f"with the raw firmware '{fw}' the lane would be {fw_lane} ({fw_why}), "
                f"not {lane}: the Checker's version guard reads the raw firmware")))
    else:
        findings.append(_finding("info", "no firmware in the inventory"))

    # 4. contract evidence shape
    if label["lane"] in ("patch", "retire") and not (cves or cited_id):
        findings.append(_finding("evidence", f"lane {label['lane']} has no evidence"))
    if label["lane"] in ("fine", "unknown") and (cves or cited_id):
        findings.append(_finding("evidence", f"lane {label['lane']} must not carry evidence ids"))
    if label["lane"] not in LANES:
        findings.append(_finding("evidence", f"lane {label['lane']!r} is not in the lane enum"))
    return out


# ---------------------------------------------------------------- source strings and URLs

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"]


def date_variants(iso: str) -> list[str]:
    """Ways a vendor page may write an ISO date (2024-12-31 -> 'December 31, 2024', '31 Dec 2024', ...)."""
    d = dt.date.fromisoformat(iso)
    m, mo = _MONTHS[d.month - 1], _MONTHS[d.month - 1][:3]
    out = {iso, f"{d.year}/{d.month:02d}/{d.day:02d}", f"{d.month:02d}/{d.day:02d}/{d.year}",
           f"{d.month}/{d.day}/{d.year}", f"{d.day:02d}/{d.month:02d}/{d.year}",
           f"{d.day}/{d.month}/{d.year}", f"{d.year}.{d.month:02d}.{d.day:02d}",
           f"{d.day:02d}.{d.month:02d}.{d.year}"}
    for day in {str(d.day), f"{d.day:02d}"}:
        for name in (m, mo, mo + "."):
            out |= {f"{name} {day}, {d.year}", f"{name} {day} {d.year}", f"{day} {name} {d.year}",
                    f"{day}-{name}-{d.year}", f"{day} {name}, {d.year}"}
    return sorted(out)


def needles_for(label: dict, row: dict | None) -> list[dict]:
    """Strings that should appear on at least one of the device's sources."""
    out: list[dict] = []
    if row:
        fixed = (row.get("fixed_version") or "").strip()
        if fixed:
            train, _ = select_train_fixes(fixed, label.get("version") or "")
            for f in train or [e for e in fixed.split(";") if e]:
                out.append({"kind": "fixed_version", "text": f, "variants": [f]})
        for col in ("last_security_support_date", "eol_date"):
            if row.get(col):
                out.append({"kind": col, "text": row[col], "variants": date_variants(row[col])})
    for src in (label.get("source_row_note", ""), (row or {}).get("notes", "")):
        for q in _QUOTE.findall(src or ""):
            if not any(n["text"] == q for n in out):
                out.append({"kind": "quote", "text": q, "variants": [q]})
    return out


def urls_for(label: dict, row: dict | None, review_urls: dict) -> list[str]:
    urls = list(review_urls.get(label["device_id"], []))
    if row:
        urls.append(row["source_url"])
        urls += _URL.findall(row.get("notes", ""))
    seen, out = set(), []
    for u in urls:
        u = u.strip().rstrip(".")
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def normalize_text(s: str) -> str:
    s = html.unescape(s)
    s = (s.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'")
          .replace("\u201c", '"').replace("\u201d", '"').replace("\u2013", "-").replace("\u2014", "-")
          .replace("\uff3f", "_"))
    return re.sub(r"\s+", " ", s).strip().casefold()


def page_text(raw: str) -> str:
    """Visible text plus the raw markup (some vendor pages carry their table in inline JSON)."""
    visible = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    visible = re.sub(r"(?s)<[^>]+>", " ", visible)
    return normalize_text(visible) + " \n " + normalize_text(raw)


def fetch(url: str, timeout: float = 25.0) -> dict:
    """One polite GET. Returns status, content_type, final_url, text (None if not text), error."""
    import requests  # local import: tests and --offline never touch the network
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
                         timeout=timeout, allow_redirects=True, stream=True)
        body = r.raw.read(MAX_BYTES, decode_content=True) or b""
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        text = None
        if ctype.startswith("text/") or ctype in ("application/json", "application/xhtml+xml",
                                                  "application/xml", ""):
            text = body.decode(r.encoding or "utf-8", errors="replace")
        return {"status": r.status_code, "content_type": ctype, "final_url": r.url, "text": text,
                "error": None}
    except Exception as e:  # network errors are results, not crashes
        return {"status": None, "content_type": "", "final_url": url, "text": None,
                "error": f"{type(e).__name__}: {e}"[:300]}


def classify(res: dict) -> tuple[str, str]:
    """(result, note) for one fetched URL. Never 'ok' for a blocked or non-text page."""
    st = res.get("status")
    if res.get("error"):
        return "needs_human", f"fetch failed ({res['error']}); {HUMAN_BROWSER}"
    if st in BLOCKED:
        return "needs_human", f"HTTP {st}: the site blocks scripts; {HUMAN_BROWSER}"
    if st is None or not 200 <= st < 300:
        return "needs_human", f"HTTP {st}; {HUMAN_BROWSER}"
    if res.get("text") is None:
        kind = "PDF" if "pdf" in (res.get("content_type") or "") else (res.get("content_type") or "binary")
        return "needs_human", f"HTTP {st}, {kind}: not text-checked; open it and check by eye"
    return "text", f"HTTP {st}, text page"


def check_urls(urls: list[str], needles: list[str], fetcher: Callable[[str], dict] = fetch,
               delay: float = DEFAULT_DELAY, log: Callable[[str], None] = print) -> dict:
    """Fetch every URL once (with `delay` seconds between requests) and record which needle
    variants appear on each text page. The page text itself is not stored."""
    out = {}
    for i, u in enumerate(urls):
        if i and delay:
            time.sleep(delay)
        res = fetcher(u)
        result, note = classify(res)
        entry = {"url": u, "status": res.get("status"), "content_type": res.get("content_type"),
                 "final_url": res.get("final_url"), "result": result, "note": note,
                 "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "found": {}}
        if result == "text":
            text = page_text(res["text"])
            entry["found"] = {n: normalize_text(n) in text for n in needles}
            entry["text_chars"] = len(res["text"])
        out[u] = entry
        log(f"  [{i + 1}/{len(urls)}] {res.get('status')} {result:<11} {u}")
    return out


def source_check(device_urls: list[str], needles: list[dict], url_results: dict,
                 kev_text: str = "", inventory_text: str = "") -> dict:
    """Per-device source result: each needle is found / not_found / unchecked across its URLs.
    A quote found in the device's KEV entries (or the vendor's KEV product names) counts as
    found (where: kev.json); a quote of the inventory row itself (a typo, a raw firmware string)
    counts as found (where: inventory.csv)."""
    per_needle = []
    text_urls = [u for u in device_urls if url_results.get(u, {}).get("result") == "text"]
    for n in needles:
        hits = [u for u in text_urls
                if any(url_results[u]["found"].get(v) for v in n["variants"])]
        q = normalize_text(n["text"])
        in_kev = n["kind"] == "quote" and q in kev_text
        in_inv = n["kind"] == "quote" and q in inventory_text
        missing_cache = [u for u in text_urls
                         if not all(v in url_results[u]["found"] for v in n["variants"])]
        status = ("found" if hits or in_kev or in_inv else "unchecked" if not text_urls or missing_cache
                  else "not_found")
        per_needle.append({**{k: n[k] for k in ("kind", "text")}, "status": status,
                           "where": hits or (["kev.json"] if in_kev else [])
                           + (["inventory.csv"] if in_inv and not hits else [])})
    urls = [{"url": u, **{k: url_results.get(u, {}).get(k) for k in ("status", "result", "note")}}
            for u in device_urls]
    human = [u for u in urls if u["result"] != "text"]
    missing = [n for n in per_needle if n["status"] != "found"]
    return {"result": "needs_human" if (human or missing) else "ok", "urls": urls,
            "needles": per_needle}


# ---------------------------------------------------------------- ordering and report

def exposure(inv: dict | None) -> int:
    if not inv:
        return 0
    crit = {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(inv.get("criticality", ""), 0)
    urgent = inv.get("internet_facing", "").lower() == "true" and crit >= 2
    return 10 * (inv.get("do_not_touch", "").lower() == "true") + 5 * urgent + crit


def finalize(devices: list[dict], inputs: dict) -> list[dict]:
    for d in devices:
        mech = [f for f in d["findings"] if f["kind"] not in ("info",)]
        d["mechanical"] = "flag" if mech else "pass"
        d["max_severity"] = max([f["severity"] for f in mech] + [0])
        if d.get("source", {}).get("result") == "needs_human":
            d["max_severity"] = max(d["max_severity"], SEVERITY["source"])
        d["exposure"] = exposure(inputs["inventory"].get(d["device_id"]))
    return sorted(devices, key=lambda d: (-d["max_severity"], -d["exposure"], d["device_id"]))


def run(inputs: dict, url_results: dict | None = None, fetcher: Callable[[str], dict] | None = fetch,
        delay: float = DEFAULT_DELAY, log: Callable[[str], None] = print) -> dict:
    """All checks. `url_results` reuses cached URL results; missing URLs are fetched with
    `fetcher` unless it is None (then they are recorded as not fetched)."""
    lc_by = {r["lifecycle_id"]: r for r in inputs["lifecycle"]}
    devices, plan = [], []
    for label in inputs["gt"]:
        d = check_device(label, inputs)
        row = lc_by.get(d["governing_lifecycle_id"] or "")
        d["_urls"] = urls_for(label, row, inputs["review_urls"])
        d["_needles"] = needles_for(label, row)
        plan.append(d)
        devices.append(d)
    all_urls = list(dict.fromkeys(u for d in plan for u in d["_urls"]))
    all_needles = sorted({v for d in plan for n in d["_needles"] for v in n["variants"]})
    url_results = dict(url_results or {})
    todo = [u for u in all_urls
            if u not in url_results or (url_results[u].get("result") == "text"
                                        and not all(v in url_results[u]["found"] for v in all_needles))]
    if todo and fetcher is not None:
        log(f"Fetching {len(todo)} URL(s), {delay:.0f} s apart ...")
        url_results.update(check_urls(todo, all_needles, fetcher, delay, log))
    for u in all_urls:
        url_results.setdefault(u, {"url": u, "status": None, "result": "not_fetched",
                                   "note": f"not fetched (offline run); {HUMAN_BROWSER}", "found": {}})
    for d in devices:
        label = next(g for g in inputs["gt"] if g["device_id"] == d["device_id"])
        kev_text = normalize_text(" ".join(
            f"{e.get('shortDescription', '')} {e.get('requiredAction', '')} {e.get('notes', '')} "
            f"{e.get('vulnerabilityName', '')}" for e in inputs["kev"].values()
            if _same(e["vendorProject"], label["vendor"]) and _same(e["product"], label["product"]))
            + " " + " | ".join(sorted({f"{e['vendorProject']} {e['product']}" for e in inputs["kev"].values()
                                       if _same(e["vendorProject"], label["vendor"])})))
        inv = inputs["inventory"].get(d["device_id"]) or {}
        inv_text = normalize_text(f"{inv.get('device_name_raw', '')} | {inv.get('firmware_version_raw', '')}")
        d["source"] = source_check(d.pop("_urls"), d.pop("_needles"), url_results, kev_text, inv_text)
    devices = finalize(devices, inputs)
    return {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "as_of_date": inputs["as_of"].isoformat(), "devices": devices,
            "urls": {u: url_results[u] for u in all_urls}}


def _md(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_report(result: dict, inputs: dict) -> str:
    devs = result["devices"]
    gt_by = {g["device_id"]: g for g in inputs["gt"]}
    flagged = [d for d in devs if d["mechanical"] == "flag"]
    human = [d for d in devs if d["source"]["result"] == "needs_human"]
    kinds: dict[str, list[str]] = {}
    for d in devs:
        for f in d["findings"]:
            if f["kind"] != "info":
                kinds.setdefault(f["kind"], []).append(d["device_id"])
    urls = result["urls"].values()
    url_human = [u for u in urls if u["result"] != "text"]
    L = [
        "# Label check report (mechanical)",
        "",
        f"Generated {result['generated_at']} by `scripts/check_labels.py`, as of "
        f"`{result['as_of_date']}` (data/ground_truth_meta.json). No LLM was used. This report checks "
        "the labels against the repo's own data and the public source pages; it does **not** replace "
        "the two human reviewers, and a `pass` here only means no mechanical rule disagreed.",
        "",
        "## Summary",
        "",
        f"- Devices: {len(devs)}. Mechanical **flag**: {len(flagged)}; pass: {len(devs) - len(flagged)}.",
        f"- Source check **needs human**: {len(human)} devices; ok: {len(devs) - len(human)}.",
        f"- URLs: {len(result['urls'])} unique; {len(url_human)} could not be text-checked by script.",
        "",
        "Flags by kind (a device can have several):",
        "",
    ]
    names = {"lane_mismatch": "recomputed lane differs from the label",
             "evidence": "evidence id missing or vendor/product mismatch",
             "firmware": "raw firmware changes the lane (version guard would differ)",
             "firmware_parse": "raw firmware doesn't parse (sim.guards grammar)",
             "pattern": "cited lifecycle pattern doesn't fit the raw name"}
    for k in ("lane_mismatch", "evidence", "firmware", "firmware_parse", "pattern"):
        ids = sorted(set(kinds.get(k, [])))
        L.append(f"- {names[k]}: {len(ids)}" + (f" ({', '.join(ids)})" if ids else ""))
    L += ["", "URLs that need a human (open them in a browser):", ""]
    for u in sorted(url_human, key=lambda x: x["url"]):
        L.append(f"- {u['url']}: {_md(u['note'])}")
    if not url_human:
        L.append("- none")
    nf = sorted({(n["kind"], n["text"]) for d in devs for n in d["source"]["needles"]
                 if n["status"] == "not_found"})
    L += ["", f"Strings not found on any of the device's text pages: {len(nf)} distinct "
          "(the page may render with JavaScript, use other wording, or the value may come from another page).", ""]
    L += [
        "## How to read this",
        "",
        "- **Ordered by risk**: highest flag severity first (lane / evidence 3, firmware changes "
        "the lane 2, firmware doesn't parse / pattern / source 1), then device exposure (do_not_touch, then internet-facing high/critical, then "
        "criticality), then device_id.",
        "- **Recomputed lane** uses the label's vendor/product/version, the cited lifecycle row "
        "(or the most specific matching row when none is cited) and KEV entries with the same "
        "vendorProject/product, with the contract tie-break: unknown, retire, patch, fine.",
        "- **Firmware lane** repeats that with the inventory's raw `firmware_version_raw`, which "
        "is what the Checker's version guard compares. Versions use `sim/guards.py` only.",
        "- **Source**: `ok` only when every URL returned a text page and every expected string "
        "(fixed_version on the device's train, support / EOL date in common formats, and phrases "
        "quoted in the notes) was found on at least one of them. Quotes found in the device's KEV "
        "entries count as found.",
        "",
        "## Devices",
        "",
        "| # | Device | Label lane | Recomputed | Mechanical | Source | Why |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, d in enumerate(devs, 1):
        g = gt_by[d["device_id"]]
        why = "; ".join(f["text"] for f in d["findings"] if f["kind"] != "info") or "-"
        src = d["source"]
        src_bits = [f"{n['kind']} '{n['text']}' {n['status'].replace('_', ' ')}"
                    for n in src["needles"] if n["status"] != "found"]
        src_bits += [f"{u['url'].split('/')[2]} {u['result'].replace('_', ' ')}"
                     for u in src["urls"] if u["result"] != "text"]
        L.append(f"| {i} | {d['device_id']} | {g['lane']} | {d['recomputed_lane']} | "
                 f"**{d['mechanical']}** | {src['result'].replace('_', ' ')} | {_md(why)}"
                 + (f"<br>Source: {_md('; '.join(src_bits))}" if src_bits else "") + " |")
    L += ["", "## URL results", "", "| URL | HTTP | Result | Note |", "|---|---|---|---|"]
    for u in sorted(urls, key=lambda x: x["url"]):
        L.append(f"| {u['url']} | {u['status']} | {u['result']} | {_md(u['note'])} |")
    L += ["", "## What this cannot verify", "",
          "- Whether a version string on the page applies to this exact model and train (a human reads the table).",
          "- Pages rendered by JavaScript, PDFs and pages that block scripts: listed above for a browser check.",
          "- KEV CVEs that a note says were not re-checked (they are named in the source notes).",
          "- Synthetic firmware builds: they exist only in this inventory.", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--offline", action="store_true",
                    help="don't fetch; reuse URL results cached in --json")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="seconds between requests")
    ap.add_argument("--json", type=Path, default=ROOT / "review" / "label_checks.json")
    ap.add_argument("--report", type=Path, default=ROOT / "docs" / "label-check-report.md")
    ap.add_argument("--refetch", action="store_true", help="ignore cached URL results")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    inputs = load_inputs()
    cached = {}
    if a.json.exists() and not a.refetch:
        cached = json.loads(a.json.read_text(encoding="utf-8")).get("urls", {})
    result = run(inputs, cached, None if a.offline else fetch, a.delay)
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    a.report.write_text(render_report(result, inputs), encoding="utf-8")
    flagged = sum(d["mechanical"] == "flag" for d in result["devices"])
    human = sum(d["source"]["result"] == "needs_human" for d in result["devices"])
    print(f"{flagged} device(s) flagged, {human} need a human source check. "
          f"Wrote {a.report.relative_to(ROOT) if a.report.is_relative_to(ROOT) else a.report} and "
          f"{a.json.relative_to(ROOT) if a.json.is_relative_to(ROOT) else a.json}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
