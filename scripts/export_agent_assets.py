"""Build the files to upload to Gemini Enterprise Agent Designer, and print the upload checklist.

Run from the repo root:
    python scripts/export_agent_assets.py                 # build dist/agent-designer/
    python scripts/export_agent_assets.py --sync-guide    # also refresh pasted prompts in the guide
    python scripts/export_agent_assets.py --check-guide   # exit 1 if the guide's prompts are stale

Reads  data/feeds/kev.json (raw CISA KEV, contracts.md) and data/lifecycle.csv.
Writes dist/agent-designer/ with
    kev_products.csv   one row per KEV vendorProject/product (built from kev.json)
    kev_entries.csv    one slim row per CVE (description trimmed)
    lifecycle.csv      byte-for-byte copy of data/lifecycle.csv
    prompts/*.txt      agents/*.md, ready to paste
    manifest.json      sizes, sha256, rough token counts, KEV catalog version

No network access, no API key. Stdlib + sim.retrieval only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim import retrieval  # noqa: E402

GUIDE = ROOT / "docs" / "agent-designer-port.md"
PROMPTS = ("main_agent", "normalizer", "checker", "planner", "verifier")
LIFECYCLE_HEADER = ["lifecycle_id", "vendor", "product", "model_pattern", "eol_date",
                    "last_security_support_date", "patch_available", "replacement_hint",
                    "source_url", "verified_on", "notes", "fixed_version"]
KNOWLEDGE_TOKEN_LIMIT = 800_000  # combined limit for uploaded Knowledge files (Google docs)
BLOCK_RE = re.compile(
    r"(<!-- BEGIN paste: agents/(?P<name>\w+)\.md -->\n````text\n)(?P<body>.*?)\n?(````\n"
    r"<!-- END paste: agents/(?P=name)\.md -->)", re.DOTALL)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rough_tokens(path: Path) -> int:
    # About 4 characters per token for English/CSV text. An estimate, not a tokenizer count.
    return len(path.read_text(encoding="utf-8")) // 4


def _write_csv(path: Path, columns, rows) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8", newline="")


def prompt_text(name: str) -> str:
    return (ROOT / "agents" / f"{name}.md").read_text(encoding="utf-8").replace("\r\n", "\n")


def sync_guide(check_only: bool = False) -> list[str]:
    """Replace each pasted-prompt block in the guide with the current agents/<name>.md.

    Returns the names whose block was (or, with check_only, would be) changed.
    """
    text = GUIDE.read_text(encoding="utf-8").replace("\r\n", "\n")
    stale: list[str] = []

    def repl(m: re.Match) -> str:
        current = prompt_text(m["name"]).rstrip("\n")
        if m["body"] != current:
            stale.append(m["name"])
        return m.group(1) + current + "\n" + m.group(4)

    new = BLOCK_RE.sub(repl, text)
    found = {m["name"] for m in BLOCK_RE.finditer(text)}
    missing = [p for p in PROMPTS if p not in found]
    if missing:
        raise SystemExit(f"guide has no paste block for: {', '.join(missing)}")
    if stale and not check_only:
        GUIDE.write_text(new, encoding="utf-8", newline="\n")
    return stale


def export(kev_path: Path, lifecycle_path: Path, out: Path) -> dict:
    if not kev_path.exists():
        raise SystemExit(f"KEV feed not found: {kev_path}\n"
                         "Fetch it first (see docs/contracts.md, data/feeds/kev.json).")
    raw = json.loads(kev_path.read_text(encoding="utf-8"))
    vulns = raw["vulnerabilities"]
    if raw.get("count") is not None and raw["count"] != len(vulns):
        raise SystemExit(f"kev.json count {raw['count']} != {len(vulns)} entries")

    out.mkdir(parents=True, exist_ok=True)
    (out / "prompts").mkdir(exist_ok=True)
    index = retrieval.KevIndex.build(vulns)
    products = retrieval.kev_products_rows(index)
    _write_csv(out / "kev_products.csv", retrieval.KEV_PRODUCTS_COLUMNS, products)
    _write_csv(out / "kev_entries.csv", retrieval.KEV_ENTRIES_COLUMNS,
               retrieval.kev_entries_rows(vulns))

    files = ["kev_products.csv", "kev_entries.csv"]
    lifecycle_rows = None
    if lifecycle_path.exists():
        with open(lifecycle_path, encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            lifecycle_rows = sum(1 for _ in reader)
        if header != LIFECYCLE_HEADER:
            raise SystemExit(f"{lifecycle_path} header does not match docs/contracts.md:\n"
                             f"  got      {header}\n  expected {LIFECYCLE_HEADER}")
        shutil.copyfile(lifecycle_path, out / "lifecycle.csv")
        files.append("lifecycle.csv")
    elif (out / "lifecycle.csv").exists():
        (out / "lifecycle.csv").unlink()  # never ship a stale copy

    for name in PROMPTS:
        (out / "prompts" / f"{name}.txt").write_text(prompt_text(name), encoding="utf-8",
                                                     newline="\n")

    meta_path = kev_path.with_name("kev_meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    manifest = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kev_catalogVersion": raw.get("catalogVersion"),
        "kev_count": len(vulns),
        "kev_fetched_at": meta.get("fetched_at"),
        "kev_sha256": _sha256(kev_path),
        "kev_products": len(products),
        "lifecycle_rows": lifecycle_rows,
        "files": {f: {"bytes": (out / f).stat().st_size, "sha256": _sha256(out / f),
                      "rough_tokens": _rough_tokens(out / f)} for f in files},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def checklist(manifest: dict, out: Path) -> str:
    total = sum(f["rough_tokens"] for f in manifest["files"].values())
    lines = [
        "",
        "Deming: Agent Designer upload checklist",
        "=======================================",
        f"Built {manifest['built_at']} from KEV catalog {manifest['kev_catalogVersion']} "
        f"({manifest['kev_count']} CVEs, {manifest['kev_products']} products).",
        f"Folder: {out}",
        "",
        "Upload to the Drive folder 'Deming/agent-assets' (replace the old files, keep the names):",
    ]
    for name, f in manifest["files"].items():
        lines.append(f"  [ ] {name:<18} {f['bytes']:>9,} bytes  ~{f['rough_tokens']:>7,} tokens  "
                     f"sha256 {f['sha256'][:12]}")
    if "lifecycle.csv" not in manifest["files"]:
        lines.append("  [!] lifecycle.csv      MISSING: data/lifecycle.csv not found. The Checker "
                     "cannot decide 'retire' without it.")
    lines += [
        f"  Total ~{total:,} tokens of the {KNOWLEDGE_TOKEN_LIMIT:,}-token Knowledge limit "
        f"({100 * total / KNOWLEDGE_TOKEN_LIMIT:.0f}%). Rough estimate (chars / 4).",
        "",
        "Then in Agent Designer:",
        "  [ ] Main agent > Knowledge > Add files (or Add from Drive): the files above.",
        "  [ ] If a file was already attached, remove the old one and attach the new one.",
        "  [ ] Paste prompts from prompts/*.txt if agents/*.md changed since the last port",
        "      (main_agent.txt into the main agent; one file per subagent).",
        "  [ ] Preview: ask 'Check DEV-T01' and confirm the evidence ids exist in kev_products.csv.",
        "  [ ] Record the KEV catalog version above in the run notes / Decision Log.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kev", type=Path, default=ROOT / "data" / "feeds" / "kev.json")
    ap.add_argument("--lifecycle", type=Path, default=ROOT / "data" / "lifecycle.csv")
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "agent-designer")
    ap.add_argument("--sync-guide", action="store_true",
                    help="rewrite the pasted prompt blocks in docs/agent-designer-port.md")
    ap.add_argument("--check-guide", action="store_true",
                    help="only check the guide's pasted prompts; exit 1 if stale")
    args = ap.parse_args(argv)

    if args.check_guide:
        stale = sync_guide(check_only=True)
        print("guide prompts stale: " + ", ".join(stale) if stale else "guide prompts up to date")
        return 1 if stale else 0

    manifest = export(args.kev, args.lifecycle, args.out)
    print(checklist(manifest, args.out))
    if args.sync_guide:
        stale = sync_guide()
        print("guide updated: " + ", ".join(stale) if stale else "guide prompts already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
