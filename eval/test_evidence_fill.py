"""Evidence ids are filled by code from the candidate rows (sim/guards.fill_evidence, contracts v1.4)."""
import pytest

from sim import guards
from sim.models import CheckerOutput

LC_RETIRE = {"lifecycle_id": "LC-001", "vendor": "Cisco", "product": "Small Business RV Series Routers",
             "model_pattern": "RV32*", "notes": "", "fixed_version": "",
             "eol_date": "2020-12-31", "last_security_support_date": "2021-12-31"}
LC_GENERIC = {**LC_RETIRE, "lifecycle_id": "LC-099", "model_pattern": ""}
LC_PATCH = {"lifecycle_id": "LC-030", "vendor": "DrayTek", "product": "Vigor Routers",
            "model_pattern": "Vigor2960*", "notes": "", "fixed_version": "1.5.1.5",
            "eol_date": "", "last_security_support_date": ""}
KEV_CISCO = [{"cveID": "CVE-2019-1653", "vendorProject": "Cisco",
              "product": "Small Business RV Series Routers", "dueDate": "2022-05-03"},
             {"cveID": "CVE-2023-20118", "vendorProject": "Cisco",
              "product": "Small Business RV Series Routers", "dueDate": "2025-03-23"}]
KEV_OTHER = [{"cveID": "CVE-2020-0001", "vendorProject": "Cisco", "product": "IOS XE",
              "dueDate": "2022-01-01"}]
KEV_DRAY = [{"cveID": "CVE-2024-12987", "vendorProject": "DrayTek", "product": "Vigor Routers",
             "dueDate": "2025-03-03"}]
CISCO = {"device_id": "DEV-001", "vendor": "Cisco", "product": "Small Business RV Series Routers",
         "model": "RV320", "version": "1.4.2.15", "firmware_version_raw": "1.4.2.15"}
DRAY = {"device_id": "DEV-002", "vendor": "DrayTek", "product": "Vigor Routers",
        "model": "Vigor2960", "version": None, "firmware_version_raw": "1.5.1.4"}


def out(lane, cves=(), lc=None):
    return CheckerOutput(device_id="DEV-001", lane=lane, evidence_cve=list(cves),
                         evidence_lifecycle_id=lc, due_date=None, confidence=0.95,
                         injection_detected=False, reason="r.")


def test_empty_retire_evidence_is_filled_not_forced_unknown():
    fixed, notes = guards.guard_checker(out("retire"), KEV_CISCO + KEV_OTHER, [LC_RETIRE, LC_GENERIC],
                                        device=CISCO)
    assert fixed.lane == "retire"
    assert fixed.evidence_lifecycle_id == "LC-001"            # most specific matching row
    assert fixed.evidence_cve == ["CVE-2019-1653", "CVE-2023-20118"]  # this product's KEV only
    assert any("evidence filled" in n for n in notes)


def test_empty_patch_evidence_is_filled():
    fixed, _ = guards.guard_checker(out("patch"), KEV_DRAY, [LC_PATCH], device=DRAY)
    assert fixed.lane == "patch"
    assert fixed.evidence_cve == ["CVE-2024-12987"] and fixed.evidence_lifecycle_id == "LC-030"


def test_model_ids_kept_when_they_are_candidates():
    fixed, notes = guards.guard_checker(out("retire", ["CVE-2023-20118"], "LC-099"),
                                        KEV_CISCO, [LC_RETIRE, LC_GENERIC], device=CISCO)
    assert fixed.evidence_cve == ["CVE-2023-20118"] and fixed.evidence_lifecycle_id == "LC-099"
    assert notes == []


def test_invented_ids_still_force_unknown():
    fixed, notes = guards.guard_checker(out("retire", ["CVE-1999-9999"]), KEV_CISCO, [LC_RETIRE],
                                        device=CISCO)
    assert fixed.lane == "unknown" and fixed.evidence_cve == [] and fixed.evidence_lifecycle_id is None


def test_fine_gets_the_lifecycle_row_but_no_cves():
    fine_dev = {**DRAY, "firmware_version_raw": "1.5.1.5"}
    fixed, _ = guards.guard_checker(out("fine", ["CVE-2024-12987"]), KEV_DRAY, [LC_PATCH], device=fine_dev)
    assert fixed.lane == "fine" and fixed.evidence_cve == [] and fixed.evidence_lifecycle_id == "LC-030"


def test_fine_without_lifecycle_candidates_stays_empty():
    fixed, notes = guards.guard_checker(out("fine"), [], [], device=CISCO)
    assert fixed.lane == "fine" and fixed.evidence_cve == [] and fixed.evidence_lifecycle_id is None
    assert notes == []


@pytest.mark.parametrize("lane", ["patch", "retire"])
def test_no_candidate_evidence_at_all_goes_unknown(lane):
    fixed, notes = guards.guard_checker(out(lane), KEV_OTHER, [], device=CISCO)
    assert fixed.lane == "unknown" and any("without evidence" in n for n in notes)


@pytest.mark.parametrize("lane", ["patch", "fine"])
def test_kev_match_with_no_lifecycle_row_is_unknown(lane):
    # checker.md rule 4.5: KEV match and no documented fixed_version (here: no row at all).
    fixed, notes = guards.guard_checker(out(lane, ["CVE-2019-1653"] if lane == "patch" else []),
                                        KEV_CISCO, [], device=CISCO)
    assert fixed.lane == "unknown" and fixed.evidence_cve == []
    assert any("fixed version not documented" in n and "no lifecycle row" in n for n in notes)


def test_unknown_carries_no_evidence():
    fixed, _ = guards.guard_checker(out("unknown"), KEV_CISCO, [LC_RETIRE], device=CISCO)
    assert fixed.evidence_cve == [] and fixed.evidence_lifecycle_id is None
