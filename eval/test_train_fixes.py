"""Per-release-train fixed_version (contracts v1.2) on the real data files.

fixed_version may list one fix per train, separated by ';'. The version guard must compare the
firmware only with the fix on its own train (longest shared leading numeric prefix, at least
major.minor) and send the device to unknown when no listed fix shares its train or its firmware
doesn't parse. Rows and devices come from data/lifecycle.csv, data/inventory.csv,
data/ground_truth.csv and data/feeds/kev.json; nothing is called over the network.
"""
import csv
import json
from pathlib import Path

import pytest

from sim import guards
from sim.models import CheckerOutput

ROOT = Path(__file__).resolve().parent.parent


def _csv(name):
    with open(ROOT / "data" / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


LC = {r["lifecycle_id"]: r for r in _csv("lifecycle.csv")}
INV = {r["device_id"]: r for r in _csv("inventory.csv")}
GT = {r["device_id"]: r for r in _csv("ground_truth.csv")}
KEV_ALL = json.loads((ROOT / "data" / "feeds" / "kev.json").read_text(encoding="utf-8"))["vulnerabilities"]

ROUTEROS, PANOS, ASA = LC["LC-025"], LC["LC-021"], LC["LC-026"]


def kev_for(row):
    return [k for k in KEV_ALL
            if k["vendorProject"] == row["vendor"] and k["product"] == row["product"]]


def device(dev_id, firmware=None):
    """Inventory row plus the human-labelled identity (stands in for the Normalizer output)."""
    d = {**INV[dev_id], "vendor": GT[dev_id]["vendor"], "product": GT[dev_id]["product"],
         "version": GT[dev_id]["version"]}
    if firmware is not None:
        d["firmware_version_raw"] = firmware
    return d


def check(dev_id, lane, lc_id=None, cves=()):
    return CheckerOutput(device_id=dev_id, lane=lane, evidence_cve=list(cves),
                         evidence_lifecycle_id=lc_id, due_date=None, confidence=0.95,
                         injection_detected=False, reason="model reason.")


def run(dev_id, lane, row, firmware=None, cite=True):
    d = device(dev_id, firmware)
    kev = kev_for(row)
    c = check(dev_id, lane, row["lifecycle_id"] if cite and lane == "patch" else None,
              [k["cveID"] for k in kev] if lane == "patch" else ())
    return guards.guard_version(c, d, kev, [row])


def test_real_rows_hold_one_fix_per_train():
    assert ROUTEROS["fixed_version"] == "7.24.3;7.23.6"
    assert ASA["fixed_version"] == "9.20.4.10;9.22.2.14;9.23.1.19"
    assert PANOS["fixed_version"] == "11.1.2-h18;11.1.4-h13;11.1.6-h1"


# --- select_train_fixes ------------------------------------------------------------------------

@pytest.mark.parametrize("dev_id,row,expected", [
    ("DEV-043", ROUTEROS, ["7.24.3"]),     # 7.24.1, stable train
    ("DEV-056", ROUTEROS, ["7.23.6"]),     # 7.23.3, long-term train
    ("DEV-005", ROUTEROS, ["7.23.6"]),
    ("DEV-029", ROUTEROS, ["7.24.3"]),
    ("DEV-037", ASA, ["9.22.2.14"]),       # 9.22.1.1
    ("DEV-049", ASA, ["9.20.4.10"]),       # 9.20.2.10
    ("DEV-048", PANOS, ["11.1.2-h18", "11.1.4-h13", "11.1.6-h1"]),  # 11.1.1: all three on 11.1
])
def test_selects_entry_on_device_train(dev_id, row, expected):
    fixes, why = guards.select_train_fixes(row["fixed_version"], INV[dev_id]["firmware_version_raw"])
    assert (fixes, why) == (expected, None)


def test_train_prefix_is_numeric_not_textual():
    # "7.2" shares only "7" with 7.23.6 / 7.24.3 as numbers, although "7.2" is a text prefix of both.
    fixes, why = guards.select_train_fixes(ROUTEROS["fixed_version"], "7.2")
    assert fixes == [] and "release train 7.2 " in why


def test_single_entry_is_returned_unchanged():
    assert guards.select_train_fixes("7.4.3", "6.0") == (["7.4.3"], None)
    assert guards.select_train_fixes("", "6.0") == ([], None)


# --- guard_version on real devices ---------------------------------------------------------------

@pytest.mark.parametrize("dev_id,row", [
    ("DEV-043", ROUTEROS), ("DEV-056", ROUTEROS), ("DEV-037", ASA), ("DEV-049", ASA)])
def test_real_patch_devices_compare_with_their_train_fix(dev_id, row):
    assert GT[dev_id]["lane"] == "patch"
    out, notes = run(dev_id, "fine", row)  # model wrongly says fine
    assert out.lane == "patch" and out.evidence_lifecycle_id == row["lifecycle_id"]
    assert set(GT[dev_id]["evidence_cve"].split(";")) <= set(out.evidence_cve)
    train_fix = guards.select_train_fixes(row["fixed_version"], INV[dev_id]["firmware_version_raw"])[0]
    assert f"fixed version {train_fix[0]} " in notes[0]
    assert run(dev_id, "patch", row) == (check(dev_id, "patch", row["lifecycle_id"],
                                               [k["cveID"] for k in kev_for(row)]), [])


@pytest.mark.parametrize("dev_id", ["DEV-005", "DEV-026", "DEV-029", "DEV-046", "DEV-055", "DEV-060"])
def test_real_fine_routeros_devices(dev_id):
    assert GT[dev_id]["lane"] == "fine"
    out, notes = run(dev_id, "patch", ROUTEROS)  # model wrongly says patch
    assert out.lane == "fine" and out.evidence_cve == [] and "at or above" in notes[0]


def test_lowest_fix_on_other_train_is_never_used():
    # DEV-043 runs 7.24.1, which is above the long-term fix 7.23.6. Comparing across trains would
    # call it fine; on its own train (fix 7.24.3) it is below the fix.
    out, _ = run("DEV-043", "fine", ROUTEROS)
    assert out.lane == "patch"


@pytest.mark.parametrize("lane", ["patch", "fine"])
def test_real_device_on_train_with_no_listed_fix_is_unknown(lane):
    # DEV-039 is a real ASA on 9.16.4.19. If the model cites the 9.20/9.22/9.23 fix row LC-026,
    # no listed fix shares train 9.16, so the guard must not compare against 9.20.4.10.
    out, notes = guards.guard_version(check("DEV-039", lane, "LC-026"), device("DEV-039"),
                                      kev_for(ASA), [ASA])
    assert out.lane == "unknown" and out.evidence_cve == [] and out.due_date is None
    assert "no fixed version listed for release train 9.16" in out.reason
    assert "9.16" in notes[0]


@pytest.mark.parametrize("lane", ["patch", "fine"])
def test_routeros_on_unlisted_train_is_unknown(lane):
    # Real router DEV-043 with its firmware changed to the 7.22 train, which has no listed fix.
    out, notes = run("DEV-043", lane, ROUTEROS, firmware="7.22.4")
    assert out.lane == "unknown"
    assert "no fixed version listed for release train 7.22 (listed: 7.24.3;7.23.6)" in out.reason


@pytest.mark.parametrize("dev_id", ["DEV-033", "DEV-047", "DEV-008"])
def test_panos_hotfix_firmware_does_not_parse_so_unknown(dev_id):
    # 11.1.4-h7 / 11.1.2-h3 / 11.1.16-h3: hotfix suffixes are outside the strict version grammar.
    out, _ = run(dev_id, "fine", PANOS)
    assert out.lane == "unknown"
    assert "does not parse, so its release train" in out.reason


def test_panos_plain_firmware_but_hotfix_fixes_is_unknown():
    # DEV-048 runs 11.1.1 (parses); its train's fixes are 11.1.2-h18/11.1.4-h13/11.1.6-h1 (don't).
    out, _ = run("DEV-048", "patch", PANOS)
    assert out.lane == "unknown" and "fixed_version '11.1.2-h18'" in out.reason


def test_firmware_between_two_fixes_on_same_train_is_unknown():
    # Hypothetical row with two fixes on train 9.20. The longest shared prefix decides first:
    # 9.20.4.1 matches 9.20.4.10 on three numbers, so only that fix applies.
    row = {**ASA, "fixed_version": "9.20.3.7;9.20.4.10"}
    assert guards.select_train_fixes(row["fixed_version"], "9.20.4.1") == (["9.20.4.10"], None)
    # With 9.20.3.7;9.20.5.2, 9.20.4.1 ties on 9.20 with both and sits between them: don't decide.
    row = {**ASA, "fixed_version": "9.20.3.7;9.20.5.2"}
    assert guards.select_train_fixes(row["fixed_version"], "9.20.4.1") == (["9.20.3.7", "9.20.5.2"], None)
    out, _ = run("DEV-049", "patch", row, firmware="9.20.4.1")
    assert out.lane == "unknown" and "between fixed versions 9.20.3.7;9.20.5.2" in out.reason
    out, _ = run("DEV-049", "fine", row)  # real firmware 9.20.2.10: below both
    assert out.lane == "patch"
