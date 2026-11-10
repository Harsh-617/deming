"""Deterministic top-k candidate retrieval for the Checker."""
from sim import retrieval

KEV = [
    {"cveID": f"CVE-2020-{i:04d}", "vendorProject": "Cisco",
     "product": "Small Business RV Series Routers",
     "vulnerabilityName": "RV320 bug" if i == 3 else "RV bug", "shortDescription": "desc",
     "requiredAction": "Apply updates.", "dueDate": f"2022-01-{i + 1:02d}",
     "dateAdded": f"2021-01-{i + 1:02d}", "notes": ""} for i in range(12)
] + [
    {"cveID": "CVE-2021-9999", "vendorProject": "Fortinet", "product": "FortiOS",
     "vulnerabilityName": "x", "shortDescription": "y" * 1000, "requiredAction": "Apply updates.",
     "dueDate": "2022-02-01", "dateAdded": "2021-12-01", "notes": ""},
    {"cveID": "CVE-2022-0001", "vendorProject": "Microsoft", "product": "Windows",
     "vulnerabilityName": "w", "shortDescription": "w", "requiredAction": "Apply updates.",
     "dueDate": "2022-03-01", "dateAdded": "2022-01-01", "notes": ""},
]
LIFE = [
    {"lifecycle_id": "LC-001", "vendor": "Cisco", "product": "Small Business RV Series Routers",
     "model_pattern": "RV32*", "eol_date": "2020-01-01",
     "last_security_support_date": "2021-01-01"},
    {"lifecycle_id": "LC-002", "vendor": "Netgear", "product": "ProSAFE", "model_pattern": "",
     "eol_date": "", "last_security_support_date": ""},
]
INDEX = retrieval.KevIndex.build(KEV)


def test_typo_raw_name_finds_cisco_rv():
    c = retrieval.kev_candidates({"device_name_raw": "cisco smal busness rv routr"}, INDEX)
    assert c and c[0]["vendorProject"] == "Cisco"


def test_normalized_fields_preferred_and_capped_per_product():
    dev = {"vendor": "Cisco", "product": "Small Business RV Series Routers", "model": "RV320"}
    c = [x for x in retrieval.kev_candidates(dev, INDEX) if x["vendorProject"] == "Cisco"]
    assert len(c) == retrieval.MAX_CVES_PER_PRODUCT
    assert c[0]["cveID"] == "CVE-2020-0003"  # model token in the name ranks first
    assert c[1]["dateAdded"] > c[2]["dateAdded"]  # then newest first


def test_unrelated_products_filtered_and_descriptions_trimmed():
    c = retrieval.kev_candidates({"vendor": "Fortinet", "product": "FortiOS"}, INDEX)
    assert {x["vendorProject"] for x in c} == {"Fortinet"}
    assert len(c[0]["shortDescription"]) <= retrieval.DESCRIPTION_CHARS + 3


def test_empty_query_returns_nothing():
    assert retrieval.kev_candidates({"device_name_raw": ""}, INDEX) == []
    assert retrieval.lifecycle_candidates({}, LIFE) == []


def test_lifecycle_glob_match_scores_100():
    c = retrieval.lifecycle_candidates(
        {"vendor": "Cisco", "product": "Small Business RV Series Routers", "model": "rv320"}, LIFE)
    assert c[0]["lifecycle_id"] == "LC-001" and c[0]["match_score"] == 100.0
    assert all(x["lifecycle_id"] != "LC-002" for x in c)


def test_retrieval_is_deterministic():
    dev = {"device_name_raw": "Cisco RV320 router"}
    assert retrieval.kev_candidates(dev, INDEX) == retrieval.kev_candidates(dev, INDEX)


def test_kev_products_rows_for_agent_designer():
    rows = retrieval.kev_products_rows(INDEX)
    assert len(rows) == 3
    cisco = next(r for r in rows if r["vendorProject"] == "Cisco")
    assert cisco["cveIDs"].count(";") == 11 and cisco["earliest_dueDate"] == "2022-01-01"
