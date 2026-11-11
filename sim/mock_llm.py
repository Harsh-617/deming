"""A deterministic, rule-based stand-in for Gemini, for `python -m sim.loop --mock`.

It follows the written rules in agents/*.md literally, so the loop can be run end to end
without an API key. It is NOT an evaluation of the prompts: a real model can disagree with it,
and the guards in sim/guards.py and sim/loop.py are what make the loop safe either way.

Makes no network calls. The client mimics the one method GeminiRunner uses:
`client.models.generate_content(model=..., contents=..., config=...)`.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from types import SimpleNamespace

from . import guards

INJECTION = re.compile(r"ignore (all |any )?(previous|prior) instructions|\bsystem:|skip approval|"
                        r"mark as (fine|verified)|close this ticket|send this now", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9.\-]*")
# Words that say what kind of device it is, not which product.
_GENERIC = {"router", "routers", "small", "business", "and", "series", "web", "the", "pro",
            "secure", "policy", "firewall", "gateway", "vpn", "wifi", "printer", "switch",
            "access", "point", "server"}


def _tokens(s: str | None) -> set[str]:
    return {t.strip(".-") for t in _TOKEN.findall((s or "").lower())} - {""}


def _same(a, b) -> bool:
    return (a or "").strip().casefold() == (b or "").strip().casefold() and bool(a)


class MockModel:
    """Rule-based answers per agent. `catalog` = (vendor, product) pairs from KEV + lifecycle."""

    def __init__(self, catalog: list[tuple[str, str]]):
        seen, self.catalog = set(), []
        for v, p in catalog:
            k = (v.casefold(), p.casefold())
            if v and p and k not in seen:
                seen.add(k)
                self.catalog.append((v, p))

    # ---- normalizer -------------------------------------------------------------------
    def normalizer(self, d: dict) -> dict:
        name = d.get("device_name_raw") or ""
        low, toks = name.lower(), _tokens(name)
        scored = []
        for vendor, product in self.catalog:
            if vendor.lower() not in low:
                continue
            ptoks = {t for t in _tokens(product) if t not in _GENERIC and len(t) >= 3}
            hits = ptoks & toks
            if hits:
                scored.append((len(hits), any(c.isdigit() for h in hits for c in h), vendor, product))
        scored.sort(reverse=True)
        fw = (d.get("firmware_version_raw") or "").strip()
        version = fw[1:] if fw[:1] in "vV" and fw[1:2].isdigit() else (fw or None)
        model = next((t for t in sorted(toks) if any(c.isdigit() for c in t)
                      and guards.parse_version(t) is None), None)
        injection = bool(INJECTION.search(json.dumps(d)))
        top = scored[0] if scored else None
        tie = len(scored) > 1 and scored[1][:2] == top[:2] and scored[1][3] != top[3]
        if top and not tie:
            return dict(device_id=d["device_id"], vendor=top[2], product=top[3], model=model,
                        version=version, confidence=0.92, lane="pending_check",
                        needs_human=False, injection_detected=injection,
                        reason=f"Name matches {top[2]} {top[3]}.")
        vendor = next((v for v, _ in self.catalog if v.lower() in low), None)
        return dict(device_id=d["device_id"], vendor=vendor, product=None, model=model,
                    version=version, confidence=0.55 if tie else 0.40, lane="unknown",
                    needs_human=True, injection_detected=injection,
                    reason="Several products fit this name." if tie
                    else "No product can be matched from this name.")

    # ---- checker ----------------------------------------------------------------------
    def checker(self, p: dict) -> dict:
        d, as_of = p["device"], p["as_of_date"]
        mine = lambda r, vk, pk: _same(r.get(vk), d.get("vendor")) and _same(r.get(pk), d.get("product"))
        lc = next((r for r in p["lifecycle_candidates"] if mine(r, "vendor", "product")), None)
        kev = [c for c in p["kev_candidates"] if mine(c, "vendorProject", "product")]
        cves = sorted({c["cveID"] for c in kev})
        dues = sorted(c["dueDate"] for c in kev if c.get("dueDate"))
        base = dict(device_id=d["device_id"], confidence=0.90,
                    injection_detected=bool(INJECTION.search(json.dumps(d))))
        end = lc and (lc.get("last_security_support_date") or lc.get("eol_date"))
        if lc and end and end < as_of:
            return dict(base, lane="retire", evidence_cve=cves, evidence_lifecycle_id=lc["lifecycle_id"],
                        due_date=dues[0] if dues else None,
                        reason=f"Security support ended {end} ({lc['lifecycle_id']}).")
        if kev:
            fw = (d.get("firmware_version_raw") or d.get("version") or "").strip()
            fixed = (lc or {}).get("fixed_version", "").strip()
            cmp = guards.compare_versions(fw, fixed) if fixed else None
            if cmp is not None and cmp >= 0:
                return dict(base, lane="fine", evidence_cve=[], evidence_lifecycle_id=None,
                            due_date=None, reason=f"Version {fw} is at or above fixed {fixed}.")
            return dict(base, lane="patch", evidence_cve=cves,
                        evidence_lifecycle_id=lc["lifecycle_id"] if lc else None,
                        due_date=dues[0] if dues else None,
                        reason=f"Listed in KEV ({';'.join(cves)}) and a fix exists.")
        return dict(base, lane="fine", evidence_cve=[], evidence_lifecycle_id=None, due_date=None,
                    reason="No KEV entry and support has not ended.")

    # ---- planner ----------------------------------------------------------------------
    def planner(self, p: dict) -> dict:
        d, c, s, today = p["device"], p["check"], p["settings"], p["today"]
        lane = c["lane"]
        dnt = str(d.get("do_not_touch")).lower() == "true"
        inet = str(d.get("internet_facing")).lower() == "true"
        crit = d.get("criticality") in ("high", "critical")
        prio = 4 if lane in ("fine", "unknown") else 1 if inet and crit else 2 if inet or crit else 3
        inj = bool(INJECTION.search(json.dumps(d)))
        out = dict(device_id=d["device_id"], lane=lane, priority=prio, requires_approval=True,
                   escalate_to_human=dnt, injection_detected=inj, deadline=None)
        if lane == "fine":
            return dict(out, action="log_only", message=None, ticket=None, reason="No known issue.")
        ev = ";".join(c.get("evidence_cve", []) + ([c["evidence_lifecycle_id"]]
                                                   if c.get("evidence_lifecycle_id") else [])) or "none"
        ident = " ".join(x for x in (d.get("vendor"), d.get("product"), d.get("version")) if x)
        # Rule 8: a KEV due date before as_of_date has passed -> as_of + kev_overdue_grace_days.
        due, passed = c.get("due_date"), ""
        as_of = p.get("as_of_date") or today
        if lane == "patch" and due and due < as_of:
            grace = int(s.get("kev_overdue_grace_days", 14))
            new_due = (dt.date.fromisoformat(as_of) + dt.timedelta(days=grace)).isoformat()
            passed = (f" The CISA KEV due date {due} has passed, so the deadline is {new_due} "
                      f"({grace} days from {as_of}).")
            due = new_due
        if lane == "patch":
            deadline, action = due, "notify_patch"
            ask = f"Please apply the vendor fix by {deadline or 'the earliest maintenance window'}."
        elif lane == "retire":
            # Rule 8: deadline = as_of_date + retire_days; the support end date is evidence only.
            as_of_d = dt.date.fromisoformat(as_of)
            days, iso = int(s.get("retire_days", 30)), int(s.get("retire_isolation_days", 7))
            deadline = (as_of_d + dt.timedelta(days=days)).isoformat()
            action = "notify_retire"
            ended = f"Vendor support ended on {due}. " if due else ""
            ask = (f"{ended}Please replace or decommission the device by {deadline} ({days} days "
                   f"from {as_of}). Until then, isolate it from the network within {iso} days "
                   f"(by {as_of_d + dt.timedelta(days=iso)}).")
        else:
            deadline, action = None, "ask_identify"
            ask = "Please identify this device (vendor, product, version) in the inventory."
        if dnt and lane != "unknown":
            ended = f"Vendor support ended on {due}. " if lane == "retire" and due else ""
            ask = (f"{ended}This device is flagged do-not-touch, so a named person must decide "
                   f"the next step by {deadline}. Deming proposes no change to it.")
        issue = {"patch": "patch", "retire": "retire", "unknown": "identify"}[lane]
        existing = next((t for t in p.get("open_tickets", []) if t.get("issue") == issue), None)
        body = (f"Device {d['device_id']} ({ident or 'unidentified'}) at {d.get('location')}: "
                f"lane {lane}. Evidence: {ev}. {ask}{passed}")
        return dict(out, action=action, deadline=deadline,
                    message=dict(subject=f"[Deming] {lane}: {d['device_id']}", body=body),
                    ticket=dict(create=existing is None,
                                existing_ticket_id=existing["ticket_id"] if existing else None,
                                issue=issue),
                    reason=f"Lane {lane} from the Checker.")

    # ---- verifier ---------------------------------------------------------------------
    def verifier(self, p: dict) -> dict:
        t, now, re_, s = p["ticket"], p["record_now"], p["recheck"], p["settings"]
        prev = (p["record_at_ticket"] or {}).get("firmware_version_raw") or None
        cur = (now or {}).get("firmware_version_raw") or None
        change = ("device_removed" if now is None else
                  "version_changed" if (prev or "") != (cur or "") else "no_change")
        today = dt.date.fromisoformat(p["today"])
        opened = dt.date.fromisoformat(t["opened"])
        last = max(opened, dt.date.fromisoformat(t["last_reminder"])) if t.get("last_reminder") else opened
        rl = (re_ or {}).get("lane")
        if change == "device_removed" or (change == "version_changed" and rl == "fine"):
            dec = "close"
        elif (today >= opened + dt.timedelta(days=int(s["days_until_escalation"]))
              or (change == "version_changed" and rl != "fine") or rl == "unknown"):
            dec = "escalate"
        elif today >= last + dt.timedelta(days=int(s["days_until_reminder"])):
            dec = "remind"
        else:
            dec = "keep_open"
        note = {"device_removed": "The device no longer appears in the inventory.",
                "version_changed": f"The inventory record now shows version {cur}; the re-check lane is {rl}.",
                "no_change": f"The inventory record still shows version {cur}."}[change]
        return dict(ticket_id=t["ticket_id"], device_id=t["device_id"], observed_change=change,
                    previous_version=prev, current_version=cur, decision=dec,
                    injection_detected=bool(INJECTION.search(json.dumps(now or {}))), note=note)


def _agent(system_instruction: str) -> str:
    first = system_instruction.splitlines()[0].lower()
    for name in ("normalizer", "checker", "planner", "verifier"):
        if name in first:
            return name
    raise ValueError(f"unrecognised prompt header: {first!r}")


class _Models:
    def __init__(self, responder):
        self.responder = responder
        self.calls = 0

    def generate_content(self, *, model, contents, config):
        agent = _agent(config.system_instruction)
        payload = json.loads(contents.split("<data>\n", 1)[1].rsplit("\n</data>", 1)[0])
        self.calls += 1
        return SimpleNamespace(text=json.dumps(self.responder(agent, payload), default=str))


class MockClient:
    """Drop-in for google.genai.Client. `responder(agent, payload) -> dict`."""

    def __init__(self, responder):
        self.models = _Models(responder)


def rule_based_client(catalog: list[tuple[str, str]]) -> MockClient:
    m = MockModel(catalog)
    return MockClient(lambda agent, payload: getattr(m, agent)(payload))
