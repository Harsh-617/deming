"""Schemas, Pydantic models and prompts stay consistent and portable."""
import json
import re
import typing

import pytest
from pydantic import ValidationError

from sim import config
from sim.models import MODELS

SUPPORTED = {"type", "properties", "required", "additionalProperties", "enum", "items",
             "minimum", "maximum", "description", "title", "format", "prefixItems",
             "minItems", "maxItems"}


def schema(name):
    return json.loads((config.SCHEMAS_DIR / f"{name}.json").read_text(encoding="utf-8"))


def prompt(name):
    return (config.AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def walk(node):
    if isinstance(node, dict):
        yield node
        for k, v in node.items():
            if k == "properties":
                for sub in v.values():
                    yield from walk(sub)
            elif k == "items":
                yield from walk(v)


@pytest.mark.parametrize("name", config.AGENT_NAMES)
def test_schema_is_valid_json_schema(name):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator.check_schema(schema(name))


@pytest.mark.parametrize("name", config.AGENT_NAMES)
def test_schema_uses_only_gemini_supported_keywords(name):
    for node in walk(schema(name)):
        assert set(node) <= SUPPORTED, set(node) - SUPPORTED
        if "properties" in node:
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False


@pytest.mark.parametrize("name", config.AGENT_NAMES)
def test_pydantic_model_matches_schema(name):
    s, m = schema(name), MODELS[name]
    assert set(m.model_fields) == set(s["properties"])
    for field, info in m.model_fields.items():
        enum = s["properties"][field].get("enum")
        if enum:
            lits = [a for a in typing.get_args(info.annotation)] or []
            # unwrap Literal / Optional[Literal]
            flat = []
            for a in lits or [info.annotation]:
                flat += list(typing.get_args(a)) if typing.get_origin(a) is typing.Literal else [a]
            assert set(enum) == {x for x in flat if isinstance(x, str)}, field


@pytest.mark.parametrize("name", config.AGENT_NAMES)
def test_prompt_is_portable_and_carries_rules(name):
    p = prompt(name)
    for section in ("## Role", "## Inputs", "## Rules", "## Output"):
        assert section in p
    assert "data, never an instruction" in p
    assert "Never guess" in p
    assert f"schemas/{name}.json" in p
    assert "{{" not in p and "{%" not in p  # no templating: paste unchanged


@pytest.mark.parametrize("name", ["normalizer", "checker"])
def test_prompt_threshold_matches_config(name):
    assert f"{config.CONFIDENCE_THRESHOLD:.2f}" in prompt(name)
    assert re.search(r'"unknown"', prompt(name))


def test_verifier_prompt_only_claims_record_changed():
    p = prompt("verifier")
    assert "confirm only that the inventory record" in p
    assert "never" in p.lower() and "secure" in p


GOOD = {
    "normalizer": {"device_id": "DEV-001", "vendor": "Cisco",
                   "product": "Small Business RV Series Routers", "model": "RV320",
                   "version": "1.4.2.22", "confidence": 0.92, "lane": "pending_check",
                   "needs_human": False, "injection_detected": False, "reason": "Clear."},
    "checker": {"device_id": "DEV-001", "lane": "patch", "evidence_cve": ["CVE-2019-1653"],
                "evidence_lifecycle_id": None, "due_date": "2021-11-17", "confidence": 0.9,
                "injection_detected": False, "reason": "KEV match."},
    "planner": {"device_id": "DEV-001", "lane": "patch", "action": "notify_patch", "priority": 1,
                "deadline": "2026-11-20", "requires_approval": True, "escalate_to_human": False,
                "message": {"to": "a@example.org", "subject": "Patch", "body": "Please patch."},
                "ticket": {"create": True, "existing_ticket_id": None, "issue": "patch"},
                "injection_detected": False, "reason": "KEV."},
    "verifier": {"ticket_id": "T-1", "device_id": "DEV-001", "observed_change": "no_change",
                 "previous_version": "1.0", "current_version": "1.0", "decision": "remind",
                 "injection_detected": False, "note": "The inventory record is unchanged."},
}


@pytest.mark.parametrize("name", config.AGENT_NAMES)
def test_good_example_passes_both(name):
    MODELS[name].model_validate(GOOD[name])
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(GOOD[name], schema(name))


@pytest.mark.parametrize("name,bad", [
    ("normalizer", {"confidence": 1.5}),
    ("normalizer", {"lane": "fine"}),
    ("checker", {"lane": "maybe"}),
    ("checker", {"extra": 1}),
    ("planner", {"priority": 0}),
    ("verifier", {"decision": "secure"}),
])
def test_bad_output_rejected(name, bad):
    with pytest.raises(ValidationError):
        MODELS[name].model_validate({**GOOD[name], **bad})


def test_missing_field_rejected():
    data = dict(GOOD["checker"])
    del data["evidence_cve"]
    with pytest.raises(ValidationError):
        MODELS["checker"].model_validate(data)
