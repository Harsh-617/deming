"""Runner behaviour with a mock client: config, cache, retry, validation, repeats, key hygiene."""
import json
import logging

import pytest
from google.genai import errors

from sim import config, gemini_runner
from sim.gemini_runner import GeminiRunner, SchemaValidationFailed
from mock_gemini import FakeClient
from test_agent_schemas import GOOD

PAYLOAD = {"device_id": "DEV-001", "device_name_raw": "cisco rv320", "firmware_version_raw": "1.4"}


def err(code, status):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": "x", "status": status}})


def runner(tmp_path, responder, **kw):
    sleeps = []
    r = GeminiRunner(FakeClient(responder), cache_dir=tmp_path, sleep=sleeps.append, **kw)
    return r, sleeps


def ok(agent, payload, i):
    return GOOD[agent]


def test_request_uses_structured_output_temperature_zero_and_prompt(tmp_path):
    r, _ = runner(tmp_path, ok)
    res = r.run("normalizer", PAYLOAD)
    call = r.client.models.calls[0]
    assert call.model == config.GEMINI_MODEL == "gemini-3.5-flash-lite"
    assert call.config.response_mime_type == "application/json"
    assert call.config.response_json_schema == json.loads(
        (config.SCHEMAS_DIR / "normalizer.json").read_text(encoding="utf-8"))
    assert call.config.temperature == 0
    assert call.config.system_instruction == gemini_runner.load_prompt("normalizer")
    assert call.payload == PAYLOAD
    assert res.output.vendor == "Cisco" and not res.cache_hit


def test_cache_hit_skips_client_and_survives_new_runner(tmp_path):
    r, _ = runner(tmp_path, ok)
    first = r.run("normalizer", PAYLOAD)
    second = r.run("normalizer", PAYLOAD)
    assert len(r.client.models.calls) == 1
    assert second.cache_hit and second.output == first.output
    r2, _ = runner(tmp_path, ok)
    assert r2.run("normalizer", PAYLOAD).cache_hit
    assert r2.client.models.calls == []


def test_cache_key_changes_with_input_agent_model_and_repeat(tmp_path):
    r, _ = runner(tmp_path, ok)
    base = r.cache_key("normalizer", PAYLOAD)
    assert base == r.cache_key("normalizer", dict(reversed(PAYLOAD.items())))  # order-insensitive
    assert base != r.cache_key("normalizer", {**PAYLOAD, "firmware_version_raw": "1.5"})
    assert base != r.cache_key("checker", PAYLOAD)
    assert base != r.cache_key("normalizer", PAYLOAD, repeat_index=1)
    assert base != GeminiRunner(None, model="other", cache_dir=tmp_path).cache_key("normalizer", PAYLOAD)


@pytest.mark.parametrize("code,status", [(503, "UNAVAILABLE"), (429, "RESOURCE_EXHAUSTED")])
def test_retries_then_succeeds(tmp_path, code, status):
    def flaky(agent, payload, i):
        return err(code, status) if i < 2 else GOOD[agent]
    r, sleeps = runner(tmp_path, flaky)
    res = r.run("checker", PAYLOAD)
    assert res.attempts == 3 and len(r.client.models.calls) == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] > 0  # exponential backoff
    assert r.stats["retries"] == 2


def test_backoff_is_capped(tmp_path):
    r, sleeps = runner(tmp_path, lambda a, p, i: err(503, "UNAVAILABLE") if i < 6 else GOOD[a],
                       max_retries=6, backoff_max=4)
    r.run("checker", PAYLOAD)
    assert max(sleeps) <= 4 * 1.5


def test_gives_up_after_max_retries(tmp_path):
    r, sleeps = runner(tmp_path, lambda a, p, i: err(503, "UNAVAILABLE"), max_retries=3)
    with pytest.raises(errors.ServerError):
        r.run("checker", PAYLOAD)
    assert len(r.client.models.calls) == 4 and len(sleeps) == 3


@pytest.mark.parametrize("code,status", [(400, "INVALID_ARGUMENT"), (500, "INTERNAL")])
def test_other_errors_not_retried(tmp_path, code, status):
    r, sleeps = runner(tmp_path, lambda a, p, i: err(code, status))
    with pytest.raises(errors.APIError):
        r.run("checker", PAYLOAD)
    assert len(r.client.models.calls) == 1 and sleeps == []


@pytest.mark.parametrize("raw", ["not json", "{}", json.dumps({**GOOD["checker"], "lane": "maybe"})])
def test_invalid_response_raises_and_is_not_cached(tmp_path, raw):
    r, _ = runner(tmp_path, lambda a, p, i: raw)
    with pytest.raises(SchemaValidationFailed):
        r.run("checker", PAYLOAD)
    assert not list(tmp_path.rglob("*.json"))


def test_run_repeated_makes_n_calls_and_reports_stability(tmp_path):
    r, _ = runner(tmp_path, ok)
    rep = r.run_repeated("verifier", PAYLOAD, n=3)
    assert rep["stable"] and rep["n"] == 3 and len(r.client.models.calls) == 3
    again = r.run_repeated("verifier", PAYLOAD, n=3)
    assert all(x.cache_hit for x in again["results"]) and len(r.client.models.calls) == 3


def test_run_repeated_detects_instability(tmp_path):
    def wobbly(agent, payload, i):
        return {**GOOD[agent], "decision": "remind" if i % 2 == 0 else "keep_open"}
    r, _ = runner(tmp_path, wobbly)
    rep = r.run_repeated("verifier", PAYLOAD, n=3)
    assert not rep["stable"] and rep["distinct_outputs"] == 2


def test_api_key_never_logged_or_cached(tmp_path, monkeypatch, caplog):
    # Built at runtime so the file holds no key-shaped literal (scripts/block_secrets.py).
    secret = "AI" + "za" + "FAKE" * 8 + "123"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    caplog.set_level(logging.DEBUG)
    r, _ = runner(tmp_path, lambda a, p, i: err(503, "UNAVAILABLE") if i == 0 else GOOD[a])
    r.run("normalizer", PAYLOAD)
    assert secret not in caplog.text
    assert all(secret not in p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json"))
    assert secret not in json.dumps(vars(r), default=str)


def test_make_client_without_key_fails_without_network(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "ROOT", tmp_path)  # no .env there
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gemini_runner.make_client()
