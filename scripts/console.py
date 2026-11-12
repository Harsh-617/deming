r"""Deming Console: a local page that walks through the demo loop with human clicks.

    python scripts/console.py              # then open http://127.0.0.1:8765/
    python scripts/console.py --port 9000
    .\.venv\Scripts\python.exe scripts\console.py   # Windows, with the repo venv

Python standard library only (http.server) plus one self-contained page, scripts/console.html
(no CDN, no network at runtime). Binds to 127.0.0.1 only. All devices are synthetic and the
outbox is simulated: nothing is sent anywhere.

It reuses the existing code and adds no lane, approval or verification logic of its own:
- sim/demo_scenario.py: fresh_state (the five demo devices, demo lifecycle rows, expected
  verification), human_edits_inventory (what owners do between runs), DAY1/DAY2, KEV fixture;
- sim/loop.py: run_loop (always with approver=None), record_approval + apply_approvals (only
  from the Approve click), State, typed_settings, make_runner;
- sim/pipeline.run_device and sim/guards (through the pipeline) for "Try a device".

It writes only under console_state/ (gitignored): console_state/demo/ is the loop state,
console_state/gemini_cache/ the response cache for "Try a device". Never data/ or sim/state.

Gemini key: "Try a device" uses GEMINI_API_KEY from the process environment or, if that is
unset, reads only that one line from the repo-root .env (load_key). The key is never printed,
logged, returned in a response or written to a file; every response and log line is scrubbed.

Approvals: the only code path that records an approval is POST /api/approve, which takes one
proposal_id and uses the approver from Settings. Nothing approves automatically.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim import config, demo_scenario, guards, retrieval  # noqa: E402
from sim import loop as simloop  # noqa: E402
from sim.gemini_runner import GeminiRunner  # noqa: E402
from sim.pipeline import run_device  # noqa: E402

HOST = "127.0.0.1"  # loopback only; there is deliberately no option to change it
DEFAULT_PORT = 8765
DEFAULT_ROOT = ROOT / "console_state"
PAGE = Path(__file__).with_name("console.html")
ENV_FILE = ROOT / ".env"  # read only for the GEMINI_API_KEY line; tests point this elsewhere
KEY_NAME = "GEMINI_API_KEY"
STEP_FILE = ".console_owners_updated"  # inside the demo folder, so Reset clears it
GEMINI_TIMEOUT_S = 20
MAX_BODY = 16 * 1024
BANNER = "Synthetic data, simulated outbox"
STEPS = ["Run 1", "Approve", "Owners update inventory", "Run 2 verify"]
# Same Google key shapes scripts/block_secrets.py blocks (AIza..., AQ....).
KEY_RE = re.compile(r"(?<![A-Za-z0-9])(?:AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{20,})")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# Every key value load_key has returned, so scrub() can redact it even if it came from .env.
_LOADED_KEYS: set[str] = set()
_ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?" + KEY_NAME + r"\s*=\s*(.*?)\s*$")


def _parse_env_value(raw: str) -> str:
    """Value part of KEY=value: quoted ("..." or '...') or bare with an optional # comment."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        return raw[1:end].strip() if end > 0 else ""  # unterminated quote: treat as unset
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def load_key(env_file: str | Path | None = None) -> tuple[str, str]:
    """(key, source). source is "environment", ".env" or "" (no key).

    The environment wins. Otherwise only the GEMINI_API_KEY line of .env is read; every other
    line is ignored and nothing is put into os.environ. The key is never printed or logged.
    """
    key = os.environ.get(KEY_NAME, "").strip()
    source = "environment" if key else ""
    if not key:
        path = Path(env_file) if env_file is not None else ENV_FILE
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            text = ""
        for line in text.splitlines():
            m = _ENV_LINE_RE.match(line)
            if m:
                key = _parse_env_value(m.group(1))  # last assignment wins, like python-dotenv
        source = ".env" if key else ""
    if key:
        _LOADED_KEYS.add(key)
    return key, source


class UserError(Exception):
    """A request the console refuses (shown on the page, HTTP 400/409)."""

    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


# ---- the console's own state (wraps sim.loop.State) ----------------------------------------
class Console:
    def __init__(self, root: str | Path = DEFAULT_ROOT, gemini_client_factory=None,
                 env_file: str | Path | None = None):
        self.root = Path(root)
        self.env_file = env_file  # None: ENV_FILE (repo-root .env)
        self.demo = self.root / "demo"
        self.cache = self.root / "gemini_cache"
        self.lock = threading.Lock()
        self._feeds = None
        # Tests swap this to simulate a failing or slow Gemini client. Default: the real one.
        self.gemini_client_factory = gemini_client_factory or _gemini_client
        if not (self.demo / demo_scenario.MARKER).exists():
            self.reset()

    # -- state helpers
    def state(self) -> simloop.State:
        return simloop.State(self.demo)

    def owners_updated(self) -> bool:
        return (self.demo / STEP_FILE).exists()

    def step(self, st: simloop.State) -> int:
        """1..4 = the step to do next; 5 = done."""
        runs = len(st.runs)
        if runs == 0:
            return 1
        if runs >= 2:
            return 5
        if self.owners_updated():
            return 4
        return 2 if any(p["status"] == "pending" for p in st.proposals) else 3

    # -- actions (each one is a human click on the page)
    def reset(self) -> None:
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True)
            demo_scenario.fresh_state(self.demo)  # deletes only a folder it created (marker)

    def _run(self, day: str) -> simloop.RunReport:
        # approver=None always: run_loop records no decisions; only the Approve click does.
        return simloop.run_loop(self.state(), as_of=day, now=f"{day}T01:00:00Z", mock=True,
                                approver=None, kev_path=demo_scenario.KEV,
                                lifecycle_path=self.demo / "lifecycle.csv")

    def run1(self) -> None:
        with self.lock:
            if len(self.state().runs) != 0:
                raise UserError("Run 1 has already happened. Reset to start again.", 409)
            self._run(demo_scenario.DAY1)

    def approve(self, proposal_id: str) -> str:
        with self.lock:
            st = self.state()
            approver = (st.settings_raw.get("approver_email") or "").strip()
            if not approver:
                raise UserError("Settings has no approver_email; set one before approving.")
            p = st.proposal(proposal_id)
            if p is None:
                raise UserError(f"No proposal {proposal_id!r}.", 404)
            if p["status"] != "pending":
                raise UserError(f"{proposal_id} is already {p['status']}.", 409)
            on = st.last_as_of()
            stamp = on + dt.datetime.now(dt.timezone.utc).strftime("T%H:%M:%SZ")
            simloop.record_approval(st, proposal_id, "approved", approver, stamp,
                                    "approved by a click in the Deming Console")
            lines = simloop.apply_approvals(st, on)
            st.save()
            simloop.save_metrics(st)
            return "; ".join(lines)

    def owners_update(self) -> None:
        with self.lock:
            st = self.state()
            if len(st.runs) != 1 or self.owners_updated():
                raise UserError("Owners update the inventory after Run 1 and before Run 2.", 409)
            demo_scenario.human_edits_inventory(self.demo)
            (self.demo / STEP_FILE).write_text("owners edited the inventory\n", encoding="utf-8")

    def run2(self) -> None:
        with self.lock:
            st = self.state()
            if len(st.runs) != 1 or not self.owners_updated():
                raise UserError("Run 2 comes after Run 1 and the owners' inventory update.", 409)
            self._run(demo_scenario.DAY2)

    def set_approver(self, email: str) -> None:
        email = (email or "").strip()
        if not EMAIL_RE.fullmatch(email) or len(email) > 120:
            raise UserError("approver_email must look like name@example.org.")
        with self.lock:
            st = self.state()
            raw = {**simloop.SETTINGS_DEFAULTS, **st.settings_raw, "approver_email": email}
            simloop.write_rows(self.demo / "settings.csv", ["key", "value"],
                               [{"key": k, "value": v} for k, v in raw.items()])

    # -- read model for the page
    def view(self) -> dict:
        with self.lock:
            st = self.state()
            step = self.step(st)
            lifecycle = {r["lifecycle_id"]: r for r in simloop.read_rows(self.demo / "lifecycle.csv")}
            latest: dict[str, dict] = {}
            for r in st.decision_log:
                if r["proposed_action"] not in ("verify", "remind"):
                    latest[r["device_id"]] = r
            escalated = {t["device_id"]: t for t in st.tickets if t["status"] == "escalated"}
            devices = []
            for d in st.inventory:
                log = latest.get(d["device_id"], {})
                devices.append({k: d.get(k, "") for k in (
                    "device_id", "device_name_raw", "location", "owner_email",
                    "firmware_version_raw", "internet_facing", "criticality", "do_not_touch",
                    "vendor", "product", "version", "match_confidence")}
                    | {"lane": log.get("lane", ""), "evidence": log.get("evidence", ""),
                       "escalated": d["device_id"] in escalated,
                       "escalation_reason": escalated.get(d["device_id"], {}).get("last_note", "")})
            proposals = []
            for p in st.proposals:
                ev = [x for x in p["evidence"].split(";") if x]
                log = next((r for r in st.decision_log if r["proposal_id"] == p["proposal_id"]
                            and r["proposed_action"] != "verify"), {})
                proposals.append({k: p[k] for k in (
                    "proposal_id", "kind", "device_id", "lane", "priority", "deadline", "actions",
                    "to", "cc", "subject", "body", "status", "decided_by", "decided_at",
                    "escalate_to_human", "ticket_id")} | {
                    "evidence": [{"id": x, "kind": "CISA KEV" if x.startswith("CVE-") else
                                  "lifecycle row", "note": (lifecycle.get(x) or {}).get("notes", "")}
                                 for x in ev],
                    "confidence": log.get("confidence", ""), "guard_notes": log.get("notes", ""),
                    "logged_action": log.get("action_taken", "")})
            outbox = []
            for f in sorted(st.outbox.glob("*.json")):
                rec = json.loads(f.read_text(encoding="utf-8"))
                outbox.append({"file": f.name, **rec})
            tickets = [{k: t[k] for k in ("ticket_id", "device_id", "issue", "status", "opened",
                                          "due", "flags", "last_note", "closed_on")}
                       for t in st.tickets]
            return {
                "banner": BANNER,
                "steps": STEPS, "step": step,
                "days": {"run1": demo_scenario.DAY1, "run2": demo_scenario.DAY2},
                "settings": {"approver_email": st.settings_raw.get("approver_email", "")},
                "devices": devices, "proposals": proposals, "outbox": outbox, "tickets": tickets,
                "escalations": [{"ticket_id": t["ticket_id"], "device_id": t["device_id"],
                                 "reason": t["last_note"], "flags": t["flags"]}
                                for t in escalated.values()],
                "decision_log": [{k: r[k] for k in ("run_id", "device_id", "lane",
                                                    "proposed_action", "decision", "outcome",
                                                    "verification_note")}
                                 for r in st.decision_log],
                "runs": [{k: r[k] for k in ("run_seq", "run_id", "as_of", "mode")} for r in st.runs],
                "verifier_wording": "The Verifier confirms the inventory record changed, "
                                    "not that the device is secure.",
            }

    # -- Try a device ----------------------------------------------------------------------
    def feeds(self):
        if self._feeds is None:
            kev = config.ROOT / "data" / "feeds" / "kev.json"
            kev = kev if kev.exists() else demo_scenario.KEV
            lifecycle = retrieval.load_lifecycle(config.ROOT / "data" / "lifecycle.csv")
            self._feeds = (retrieval.KevIndex.build(retrieval.load_kev(kev)), lifecycle)
        return self._feeds

    def try_device(self, form: dict) -> dict:
        device = _try_record(form)
        kev_index, lifecycle = self.feeds()
        with self.lock:
            settings = simloop.typed_settings(self.state().settings_raw)
        as_of = config.load_as_of_date()
        key, _source = load_key(self.env_file)
        fallback = ""
        result = None
        if key:
            try:
                runner = GeminiRunner(self.gemini_client_factory(key), cache_dir=self.cache,
                                      max_retries=0)
                result = _with_timeout(lambda: _run_recorded(runner, device, kev_index, lifecycle,
                                                             as_of, settings), GEMINI_TIMEOUT_S)
                model = f"model: {runner.model}"
            except Exception as exc:  # noqa: BLE001 - any failure falls back to the mock
                # Only the exception type: its text could echo request details.
                code = getattr(exc, "code", None)  # HTTP status from google-genai errors
                code = f", HTTP {code}" if isinstance(code, int) else ""
                fallback = (f"Gemini call failed ({type(exc).__name__}{code}); used the mock instead"
                            if not isinstance(exc, TimeoutError) else
                            f"Gemini did not answer within {GEMINI_TIMEOUT_S} s; used the mock instead")
                result = None
        else:
            fallback = "GEMINI_API_KEY is not set in the environment or .env; used the mock"
        if result is None:
            runner = simloop.make_runner(True, kev_index, lifecycle)
            result = _run_recorded(runner, device, kev_index, lifecycle, as_of, settings)
            model = "model: mock"
            fallback += (". The mock is a rule-based stand-in, not a model: it sends most messy "
                         "names to unknown.")
        return {"model": model, "fallback": fallback, "as_of_date": as_of,
                "device": device, **result,
                "note": "Try a device writes nothing to the outbox, tickets or inventory. "
                        "Synthetic input; the result is not a real-world assessment."}


def _try_record(form: dict) -> dict:
    name = str(form.get("device_name_raw", "")).strip()
    fw = str(form.get("firmware_version_raw", "")).strip()
    crit = str(form.get("criticality", "medium")).strip().lower()
    if not name or len(name) > 200 or len(fw) > 64:
        raise UserError("Give a raw device name (up to 200 characters) and firmware up to 64.")
    if crit not in ("low", "medium", "high", "critical"):
        raise UserError("criticality must be low, medium, high or critical.")
    return dict(device_id="TRY-001", device_name_raw=name, location="Console try-a-device",
                owner_email="owner@example.org", firmware_version_raw=fw,
                internet_facing=str(form.get("internet_facing") is True).lower(),
                criticality=crit, do_not_touch=str(form.get("do_not_touch") is True).lower(),
                last_updated=config.load_as_of_date())


class _Recorder:
    """Passes calls to a GeminiRunner and keeps each agent's answer before the guards run."""

    def __init__(self, inner):
        self.inner = inner
        self.stats = inner.stats
        self.calls: dict[str, dict] = {}

    def run(self, agent, payload, repeat_index=0):
        res = self.inner.run(agent, payload, repeat_index)
        self.calls[agent] = {"output": res.output.model_dump(mode="json"),
                             "cache_hit": res.cache_hit}
        return res


def _run_recorded(runner, device, kev_index, lifecycle, as_of, settings) -> dict:
    rec = _Recorder(runner)
    r = run_device(rec, device, kev_index, lifecycle, today=as_of, settings=settings,
                   as_of_date=as_of)
    final = {"normalizer": r.normalized.model_dump(mode="json"),
             "checker": r.check.model_dump(mode="json"),
             "planner": r.plan.model_dump(mode="json")}
    agents = []
    for name in ("normalizer", "checker", "planner"):
        call = rec.calls.get(name)
        agents.append({
            "agent": name, "called": call is not None,
            "model_output": call["output"] if call else None,
            "cache_hit": bool(call and call["cache_hit"]),
            "final_output": final[name],
            "changed_by_guard": call is not None and call["output"] != final[name],
            "skipped_reason": "" if call else
            "Not called: the Normalizer was not confident, so code set lane unknown (never guess)."})
    # The message as sim/loop would put it in a proposal: the loop's own last check
    # (_safe_body) rebuilds a body with injected text or, for do_not_touch, disconnect wording.
    notes = list(r.guard_notes)
    msg = ""
    if r.plan.message:
        dnt = device["do_not_touch"] == "true"
        evidence = ";".join(r.check.evidence_cve + ([r.check.evidence_lifecycle_id]
                                                    if r.check.evidence_lifecycle_id else []))
        msg, note = simloop._safe_body(
            r.plan.message.body or "-", device["device_id"], r.check.lane, evidence,
            r.plan.deadline.isoformat() if r.plan.deadline else "", dnt,
            guards.deadline_sentence(r.check, as_of, settings, dnt))
        if note:
            notes.append(note)
    return {"agents": agents, "guard_notes": notes, "lane": r.check.lane,
            "recipient": r.recipient, "proposal_message": msg,
            "disconnect_wording_in_message": bool(guards._DISCONNECT.search(msg))}


def _with_timeout(fn, seconds: float):
    """Run fn in a daemon thread; raise TimeoutError if it takes longer than `seconds`."""
    box: dict = {}

    def target():
        try:
            box["ok"] = fn()
        except BaseException as exc:  # noqa: BLE001
            box["err"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError
    if "err" in box:
        raise box["err"]
    return box["ok"]


def _gemini_client(key: str):
    """google-genai client with a 20 s HTTP timeout and no SDK retry. The key is not kept."""
    from google import genai
    from google.genai import types
    return genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=GEMINI_TIMEOUT_S * 1000,  # milliseconds
        retry_options=types.HttpRetryOptions(attempts=1)))


# ---- HTTP --------------------------------------------------------------------------------
def scrub(text: str) -> str:
    """Belt and braces: the key never leaves the process, even if some text echoed it."""
    keys = set(_LOADED_KEYS)
    env_key = os.environ.get(KEY_NAME, "").strip()
    if env_key:
        keys.add(env_key)
    for key in sorted(keys, key=len, reverse=True):
        text = text.replace(key, "[redacted]")
    return KEY_RE.sub("[redacted]", text)


def make_handler(console: Console):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DemingConsole"
        sys_version = ""

        def log_message(self, fmt, *args):  # method, path and status only; no bodies
            sys.stderr.write(scrub(f"{self.command} {self.path.split('?')[0]} "
                                   f"{args[1] if len(args) > 1 else ''}\n"))

        # -- checks against other web pages driving this local server
        def _host_ok(self) -> bool:
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            port = self.server.server_address[1]
            return origin is None or origin in (f"http://127.0.0.1:{port}",
                                                f"http://localhost:{port}")

        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            body = scrub(json.dumps(obj, ensure_ascii=False, default=str)).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad Host header"})
            path = self.path.split("?")[0]
            if path == "/":
                nonce = secrets.token_urlsafe(16)
                html = PAGE.read_text(encoding="utf-8").replace("{{NONCE}}", nonce)
                csp = (f"default-src 'none'; script-src 'nonce-{nonce}'; "
                       f"style-src 'nonce-{nonce}'; connect-src 'self'; img-src 'self' data:; "
                       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8",
                                  {"Content-Security-Policy": csp, "X-Frame-Options": "DENY"})
            if path == "/api/state":
                return self._json(200, console.view())
            return self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or not self._origin_ok():
                return self._json(403, {"error": "requests must come from the console page"})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "Content-Type must be application/json"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_BODY:
                return self._json(413, {"error": "body too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"error": "body must be a JSON object"})
            path = self.path.split("?")[0]
            try:
                msg = ""
                if path == "/api/reset":
                    console.reset()
                elif path == "/api/run1":
                    console.run1()
                elif path == "/api/approve":
                    if set(body) != {"proposal_id"} or not isinstance(body["proposal_id"], str):
                        raise UserError("Send exactly one proposal_id. The approver comes from "
                                        "Settings, not from the request.")
                    msg = console.approve(body["proposal_id"])
                elif path == "/api/owners-update":
                    console.owners_update()
                elif path == "/api/run2":
                    console.run2()
                elif path == "/api/settings":
                    if set(body) != {"approver_email"}:
                        raise UserError("Only approver_email can be changed here.")
                    console.set_approver(str(body["approver_email"]))
                elif path == "/api/try":
                    return self._json(200, console.try_device(body))
                else:
                    return self._json(404, {"error": "not found"})
                return self._json(200, {"ok": True, "message": msg, "state": console.view()})
            except UserError as exc:
                return self._json(exc.status, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                return self._json(500, {"error": f"internal error ({type(exc).__name__})"})

    return Handler


def make_server(console: Console, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), make_handler(console))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Deming Console (local, synthetic data).")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args(argv)
    console = Console()
    srv = make_server(console, args.port)
    _key, source = load_key(console.env_file)
    del _key  # only whether a key exists and where it came from is shown, never the value
    key = (f"found in the {source} (Try a device will call Gemini)" if source
           else "not found in the environment or .env (Try a device uses the mock)")
    print(f"Deming Console on http://{HOST}:{srv.server_address[1]}/  ({BANNER})")
    print(f"State: {console.root}   GEMINI_API_KEY: {key}   Ctrl+C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
