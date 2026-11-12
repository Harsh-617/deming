"""Deming Console (scripts/console.py): approvals only by click, reset, run 2 matches the demo
scenario, the API key never leaves the process, writes stay under the console's own folder.

No network and no LLM calls: "Try a device" runs the rule-based mock, or a fake client that
stands in for Gemini.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import console as cs  # noqa: E402
from sim import config, demo_scenario  # noqa: E402
from sim import loop as simloop  # noqa: E402
from sim.mock_llm import MockClient, MockModel  # noqa: E402

# Built at runtime so the source never contains a key-shaped string (scripts/block_secrets.py).
FAKE_KEY = "AI" + "za" + "SyFAKE" + "x" * 30


# ---- helpers ---------------------------------------------------------------------------------
class Server:
    def __init__(self, console: cs.Console):
        self.console = console
        self.srv = cs.make_server(console, 0)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def request(self, method, path, body=None, headers=None, raw=None):
        h = {"Content-Type": "application/json"} if method == "POST" else {}
        h.update(headers or {})
        data = raw if raw is not None else (json.dumps(body or {}).encode() if method == "POST" else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                     method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), dict(e.headers)

    def post(self, path, body=None, **kw):
        status, text, _ = self.request("POST", path, body, **kw)
        return status, json.loads(text)

    def state(self):
        return json.loads(self.request("GET", "/api/state")[1])

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = Server(cs.Console(tmp_path / "console_state"))
    yield s
    s.close()


def approve_all(server):
    for p in server.state()["proposals"]:
        if p["status"] == "pending":
            status, body = server.post("/api/approve", {"proposal_id": p["proposal_id"]})
            assert status == 200, body


def full_flow(server):
    assert server.post("/api/run1")[0] == 200
    approve_all(server)
    assert server.post("/api/owners-update")[0] == 200
    assert server.post("/api/run2")[0] == 200


def tree_hash(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


# ---- run 2 matches the demo scenario -----------------------------------------------------------
def test_run2_after_approval_matches_demo_scenario(server, tmp_path):
    full_flow(server)
    st = simloop.State(server.console.demo)
    day2 = {r["run_id"]: r["as_of"] for r in st.runs}
    got = {(day2[r["run_id"]], r["device_id"]): r["decision"]
           for r in st.decision_log if r["proposed_action"] == "verify"}
    for e in demo_scenario.EXPECTED:
        assert got[(e["as_of"], e["device_id"])] == e["expected_decision"], e

    ref = demo_scenario.run_demo(tmp_path / "reference_demo", quiet=True)
    key = lambda t: (t["ticket_id"], t["device_id"], t["issue"], t["status"], t["flags"],
                     t["last_note"])
    assert [key(t) for t in st.tickets] == [key(t) for t in ref.tickets]
    for run in ("deming-20261112T010000Z", "deming-20261113T010000Z"):
        mine = simloop.read_rows(st.root / "runs" / run / "deming.csv")
        theirs = simloop.read_rows(ref.root / "runs" / run / "deming.csv")
        assert mine == theirs
    m = simloop.compute_metrics(st)
    assert m["approval_compliance"]["violations"] == 0
    assert m["verification_correctness"]["value"] == 1.0

    view = server.state()
    assert view["step"] == 5
    assert [e["device_id"] for e in view["escalations"]] == ["DEV-104"]
    assert "still below the fixed version 7.0.14" in view["escalations"][0]["reason"]
    dev104 = next(d for d in view["devices"] if d["device_id"] == "DEV-104")
    assert dev104["escalated"] and "a change is not a fix" in dev104["escalation_reason"]


# ---- approvals can't be bypassed --------------------------------------------------------------
def test_runs_never_approve_anything(server):
    server.post("/api/run1")
    view = server.state()
    assert view["step"] == 2
    assert len(view["proposals"]) == 4 and all(p["status"] == "pending" for p in view["proposals"])
    assert view["outbox"] == [] and view["tickets"] == []
    # Skip approval entirely: owners update and run 2 still send nothing and open no ticket.
    assert server.post("/api/owners-update")[0] == 200
    assert server.post("/api/run2")[0] == 200
    st = simloop.State(server.console.demo)
    assert st.approvals == [] and st.tickets == []
    assert list(st.outbox.glob("*.json")) == []


def test_run_loop_is_always_called_without_an_approver(server, monkeypatch):
    seen = []
    real = simloop.run_loop
    monkeypatch.setattr(simloop, "run_loop", lambda *a, **k: (seen.append(k), real(*a, **k))[1])
    server.post("/api/run1")
    server.post("/api/owners-update")
    server.post("/api/run2")
    assert len(seen) == 2 and all(k["approver"] is None for k in seen)


def test_source_has_one_approval_path_and_no_scripted_approver():
    src = (ROOT / "scripts" / "console.py").read_text(encoding="utf-8")
    assert "ScriptedApprover" not in src
    assert src.count("record_approval(") == 1
    assert src.count('"approved"') == 1  # the decision passed in Console.approve, nowhere else
    assert "/api/approve" in src and "approve_all" not in src
    page = (ROOT / "scripts" / "console.html").read_text(encoding="utf-8")
    # The page only calls /api/approve from a button's click handler.
    assert page.count('"/api/approve"') == 1
    assert 'onclick: () => post("/api/approve"' in page


@pytest.mark.parametrize("body", [{}, {"proposal_id": "*"}, {"proposal_id": ["P-001-DEV-101"]},
                                  {"proposal_id": "P-001-DEV-101", "approver": "x@example.org"},
                                  {"proposal_id": "NOPE"}])
def test_approve_rejects_bad_requests(server, body):
    server.post("/api/run1")
    status, out = server.post("/api/approve", body)
    assert status in (400, 404) and "error" in out
    st = simloop.State(server.console.demo)
    assert st.approvals == [] and list(st.outbox.glob("*.json")) == []


def test_approve_requires_json_same_origin_and_loopback_host(server):
    server.post("/api/run1")
    pid = {"proposal_id": "P-001-DEV-101"}
    form = b"proposal_id=P-001-DEV-101"
    assert server.request("POST", "/api/approve", raw=form,
                          headers={"Content-Type": "application/x-www-form-urlencoded"})[0] == 415
    assert server.post("/api/approve", pid, headers={"Origin": "http://evil.example"})[0] == 403
    assert server.post("/api/approve", pid, headers={"Host": "evil.example"})[0] == 403
    assert server.request("GET", "/api/approve?proposal_id=P-001-DEV-101")[0] == 404
    assert simloop.State(server.console.demo).approvals == []
    # The real page origin works, once.
    origin = {"Origin": f"http://127.0.0.1:{server.port}"}
    assert server.post("/api/approve", pid, headers=origin)[0] == 200
    assert server.post("/api/approve", pid, headers=origin)[0] == 409


def test_approver_comes_from_settings(server):
    server.post("/api/run1")
    assert server.post("/api/settings", {"approver_email": "ciso@example.org"})[0] == 200
    assert server.post("/api/settings", {"approver_email": "not an email"})[0] == 400
    server.post("/api/approve", {"proposal_id": "P-001-DEV-101"})
    st = simloop.State(server.console.demo)
    assert [a["approver"] for a in st.approvals] == ["ciso@example.org"]
    rec = json.loads((st.outbox / "P-001-DEV-101.email.json").read_text(encoding="utf-8"))
    assert rec["approved_by"] == "ciso@example.org"


def test_blank_approver_blocks_approval(server):
    server.post("/api/run1")
    simloop.write_rows(server.console.demo / "settings.csv", ["key", "value"],
                       [{"key": "approver_email", "value": ""}])
    status, out = server.post("/api/approve", {"proposal_id": "P-001-DEV-101"})
    assert status == 400 and "approver" in out["error"]
    assert simloop.State(server.console.demo).approvals == []


def test_steps_are_ordered(server):
    assert server.post("/api/owners-update")[0] == 409
    assert server.post("/api/run2")[0] == 409
    server.post("/api/run1")
    assert server.post("/api/run1")[0] == 409
    assert server.post("/api/run2")[0] == 409


# ---- reset -----------------------------------------------------------------------------------
def test_reset_returns_to_the_start(server):
    full_flow(server)
    server.post("/api/settings", {"approver_email": "ciso@example.org"})
    assert server.post("/api/reset")[0] == 200
    view = server.state()
    assert view["step"] == 1
    assert view["proposals"] == [] and view["outbox"] == [] and view["tickets"] == []
    assert view["decision_log"] == [] and view["runs"] == []
    assert view["settings"]["approver_email"] == simloop.SETTINGS_DEFAULTS["approver_email"]
    inv = simloop.read_rows(server.console.demo / "inventory.csv")
    assert inv == [{k: v for k, v in d.items()} for d in demo_scenario.INVENTORY]
    # and the loop runs again from scratch
    full_flow(server)
    assert server.state()["step"] == 5


def test_reset_never_deletes_a_folder_it_did_not_create(tmp_path):
    (tmp_path / "demo").mkdir(parents=True)
    (tmp_path / "demo" / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit):
        cs.Console(tmp_path)
    assert (tmp_path / "demo" / "keep.txt").exists()


# ---- writes stay in console_state -------------------------------------------------------------
def test_writes_only_under_its_own_folder(server):
    watched = {d: tree_hash(ROOT / d) for d in ("data", "sim", "agents", "schemas")}
    full_flow(server)
    server.post("/api/try", {"device_name_raw": "D-Link DIR-600 router",
                             "firmware_version_raw": "2.18"})
    server.post("/api/reset")
    for d, before in watched.items():
        assert tree_hash(ROOT / d) == before, d
    assert cs.DEFAULT_ROOT == ROOT / "console_state"
    assert "console_state/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_server_binds_loopback_only_and_page_is_self_contained(server):
    assert server.srv.server_address[0] == "127.0.0.1"
    status, html, headers = server.request("GET", "/")
    assert status == 200
    assert "Synthetic data, simulated outbox" in html
    for word in ("Run 1", "Approve", "Owners update inventory", "Run 2 verify", "Reset", "Try a device"):
        assert word in html or word in server.state()["steps"]
    assert "http://" not in html and "https://" not in html  # no CDN, no external fetch
    csp = headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp
    assert "unsafe-inline" not in csp and "{{NONCE}}" not in html
    assert "--host" not in (ROOT / "scripts" / "console.py").read_text(encoding="utf-8")


# ---- Try a device -----------------------------------------------------------------------------
def try_body(dnt=False, name="D-Link DIR-600 router"):
    return {"device_name_raw": name, "firmware_version_raw": "2.18", "criticality": "high",
            "internet_facing": True, "do_not_touch": dnt}


def test_try_device_uses_mock_without_key(server):
    status, out = server.post("/api/try", try_body())
    assert status == 200
    assert out["model"] == "model: mock" and "GEMINI_API_KEY is not set" in out["fallback"]
    assert out["lane"] == "retire"
    assert [a["agent"] for a in out["agents"]] == ["normalizer", "checker", "planner"]
    assert all(a["called"] and a["model_output"] for a in out["agents"])
    # A do-not-touch device never gets disconnect / isolate wording; a normal one does.
    assert out["disconnect_wording_in_message"] is True
    status, dnt = server.post("/api/try", try_body(dnt=True))
    assert dnt["lane"] == "retire" and dnt["disconnect_wording_in_message"] is False
    assert dnt["agents"][2]["final_output"]["escalate_to_human"] is True
    st = simloop.State(server.console.demo)  # nothing written to the loop state
    assert st.proposals == [] and list(st.outbox.glob("*.json")) == []


def test_try_device_unknown_skips_checker(server):
    out = server.post("/api/try", try_body(name="router 2nd floor"))[1]
    assert out["lane"] == "unknown"
    checker = out["agents"][1]
    assert checker["called"] is False and "never guess" in checker["skipped_reason"]


def test_try_device_rejects_bad_input(server):
    assert server.post("/api/try", {"device_name_raw": ""})[0] == 400
    assert server.post("/api/try", {**try_body(), "criticality": "extreme"})[0] == 400
    assert server.post("/api/try", {**try_body(), "device_name_raw": "x" * 201})[0] == 400


def _fake_gemini(console, planner_body=None, delay=0.0, raise_with=None):
    """A stand-in for google.genai.Client built from the rule-based mock (no network)."""
    kev_index, lifecycle = console.feeds()
    model = MockModel(list(kev_index.keys) + [(r["vendor"], r["product"]) for r in lifecycle])

    def responder(agent, payload):
        if delay:
            time.sleep(delay)
        out = getattr(model, agent)(payload)
        if agent == "planner" and planner_body and out.get("message"):
            out["message"]["body"] = planner_body
        return out

    def factory(key):
        assert key == FAKE_KEY
        if raise_with:
            raise RuntimeError(raise_with)
        return MockClient(responder)
    return factory


def test_gemini_path_shows_model_and_guard_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    c = cs.Console(tmp_path / "cs")
    c.gemini_client_factory = _fake_gemini(c, planner_body="Disconnect this router today.")
    s = Server(c)
    try:
        status, out = s.post("/api/try", try_body(dnt=True))
    finally:
        s.close()
    assert status == 200
    assert out["model"] == f"model: {config.GEMINI_MODEL}" and out["fallback"] == ""
    planner = out["agents"][2]
    assert "Disconnect" in planner["model_output"]["message"]["body"]
    assert planner["changed_by_guard"] is True
    assert out["disconnect_wording_in_message"] is False
    assert any("do_not_touch: disconnect/isolate wording removed" in n for n in out["guard_notes"])
    assert any((tmp_path / "cs" / "gemini_cache").rglob("*.json"))  # response cache, own folder


def test_gemini_timeout_falls_back_to_mock(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(cs, "GEMINI_TIMEOUT_S", 0.3)
    c = cs.Console(tmp_path / "cs")
    c.gemini_client_factory = _fake_gemini(c, delay=2.0)
    out = c.try_device(try_body())
    assert out["model"] == "model: mock" and "did not answer within 0.3 s" in out["fallback"]
    assert out["lane"] == "retire"


def test_api_key_never_returned_or_logged(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    c = cs.Console(tmp_path / "cs")
    c.gemini_client_factory = _fake_gemini(c, raise_with=f"API key {FAKE_KEY} not valid")
    s = Server(c)
    try:
        texts = [s.request("POST", "/api/try", try_body())[1],
                 s.request("POST", "/api/try", try_body(name=f"router {FAKE_KEY}"))[1],
                 s.request("GET", "/")[1], s.request("GET", "/api/state")[1]]
        for path in ("/api/run1", "/api/approve", "/api/settings", "/api/nope"):
            texts.append(s.request("POST", path, {"proposal_id": "P-001-DEV-101"})[1])
        texts.append(s.request("POST", "/api/approve", raw=b"not json")[1])
    finally:
        s.close()
    out = json.loads(texts[0])
    assert out["model"] == "model: mock" and "RuntimeError" in out["fallback"]
    logs = capsys.readouterr()
    for t in texts + [logs.out, logs.err]:
        assert FAKE_KEY not in t
    for f in (tmp_path / "cs").rglob("*"):
        if f.is_file():
            assert FAKE_KEY not in f.read_text(encoding="utf-8", errors="replace")
