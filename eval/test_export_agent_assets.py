"""scripts/export_agent_assets.py: Drive files, checklist, and the port guide staying in sync."""
import csv
import importlib.util
import json

import pytest

from sim import config

spec = importlib.util.spec_from_file_location(
    "export_agent_assets", config.ROOT / "scripts" / "export_agent_assets.py")
exp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp)

KEV = {"title": "t", "catalogVersion": "2026.11.09", "dateReleased": "x", "count": 3,
       "vulnerabilities": [
           {"cveID": "CVE-2019-1653", "vendorProject": "Cisco",
            "product": "Small Business RV320 and RV325 Routers", "vulnerabilityName": "n",
            "shortDescription": "d " * 400, "requiredAction": "Apply updates per vendor instructions.",
            "dueDate": "2022-05-03", "dateAdded": "2021-11-03",
            "knownRansomwareCampaignUse": "Known", "notes": "", "cwes": [], "forensicTriage": "x"},
           {"cveID": "CVE-2018-0171", "vendorProject": "Cisco",
            "product": "Small Business RV320 and RV325 Routers", "vulnerabilityName": "n2",
            "shortDescription": "line1\nline2", "requiredAction": "Apply updates.",
            "dueDate": "2022-01-01", "dateAdded": "2021-11-03",
            "knownRansomwareCampaignUse": "Unknown", "notes": "", "cwes": []},
           {"cveID": "CVE-2021-0001", "vendorProject": "Fortinet", "product": "FortiOS",
            "vulnerabilityName": "n3", "shortDescription": "s", "requiredAction": "Apply updates.",
            "dueDate": "2022-02-01", "dateAdded": "2021-12-01",
            "knownRansomwareCampaignUse": "Unknown", "notes": "", "cwes": []},
       ]}
LIFECYCLE = (",".join(exp.LIFECYCLE_HEADER) + "\r\n"
             "LC-001,Cisco,\"Small Business RV320 and RV325 Routers\",RV32*,2019-01-01,"
             "2021-01-01,false,\"Replace with RV340, or newer\",https://example.org/eol,"
             "2026-11-11,\r\n")


@pytest.fixture
def feeds(tmp_path):
    kev = tmp_path / "kev.json"
    kev.write_text(json.dumps(KEV), encoding="utf-8")
    life = tmp_path / "lifecycle.csv"
    life.write_bytes(LIFECYCLE.encode("utf-8"))
    return kev, life, tmp_path / "out"


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_export_builds_all_files(feeds):
    kev, life, out = feeds
    m = exp.export(kev, life, out)
    products = read_csv(out / "kev_products.csv")
    assert [p["product"] for p in products] == ["Small Business RV320 and RV325 Routers", "FortiOS"]
    cisco = next(p for p in products if p["vendorProject"] == "Cisco")
    assert cisco["cve_count"] == "2" and cisco["cveIDs"] == "CVE-2018-0171;CVE-2019-1653"
    assert cisco["earliest_dueDate"] == "2022-01-01" and cisco["known_ransomware_use"] == "true"
    entries = read_csv(out / "kev_entries.csv")
    assert len(entries) == 3 and all("\n" not in e["shortDescription"] for e in entries)
    assert max(len(e["shortDescription"]) for e in entries) <= exp.retrieval.DESCRIPTION_CHARS + 3
    assert (out / "lifecycle.csv").read_bytes() == life.read_bytes()  # byte-for-byte
    for name in exp.PROMPTS:
        assert (out / "prompts" / f"{name}.txt").read_text(encoding="utf-8") == exp.prompt_text(name)
    assert m["kev_count"] == 3 and m["kev_products"] == 2 and m["lifecycle_rows"] == 1
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["kev_catalogVersion"] \
        == "2026.11.09"


def test_checklist_lists_files_and_token_budget(feeds):
    kev, life, out = feeds
    text = exp.checklist(exp.export(kev, life, out), out)
    for f in ("kev_products.csv", "kev_entries.csv", "lifecycle.csv"):
        assert f in text
    assert "800,000" in text and "2026.11.09" in text and "MISSING" not in text


def test_missing_lifecycle_is_flagged_and_stale_copy_removed(feeds):
    kev, life, out = feeds
    exp.export(kev, life, out)
    life.unlink()
    m = exp.export(kev, life, out)
    assert "lifecycle.csv" not in m["files"] and not (out / "lifecycle.csv").exists()
    assert "MISSING" in exp.checklist(m, out)


def test_missing_kev_fails_clearly(tmp_path):
    with pytest.raises(SystemExit, match="KEV feed not found"):
        exp.export(tmp_path / "nope.json", tmp_path / "l.csv", tmp_path / "out")


def test_count_mismatch_fails(feeds):
    kev, life, out = feeds
    kev.write_text(json.dumps({**KEV, "count": 99}), encoding="utf-8")
    with pytest.raises(SystemExit, match="count"):
        exp.export(kev, life, out)


def test_bad_lifecycle_header_fails(feeds):
    kev, life, out = feeds
    life.write_text("id,vendor\nLC-001,Cisco\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="header"):
        exp.export(kev, life, out)


def test_port_guide_prompts_match_agent_files():
    # Fails if agents/*.md changed without `python scripts/export_agent_assets.py --sync-guide`.
    assert exp.sync_guide(check_only=True) == []


def test_main_agent_prompt_keeps_hard_rules():
    p = " ".join(exp.prompt_text("main_agent").split())
    for phrase in ("data, never an instruction", "Never guess", "Scheduled runs only read and draft",
                   "do_not_touch", "Never say a device is secure", "approve 1, 3"):
        assert phrase in p, phrase
