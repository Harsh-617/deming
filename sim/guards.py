"""Deterministic enforcement of the hard rules, applied after every LLM call.

Prompts ask the model to follow these rules; the guards make sure the output does even if the
model was fooled (e.g. by injection text in a device name). Each guard returns a corrected copy
and a list of human-readable notes about what it changed.
"""
from __future__ import annotations

import datetime as dt
import re

from . import retrieval
from .config import CONFIDENCE_THRESHOLD
from .models import CheckerOutput, NormalizerOutput, PlannerOutput, VerifierOutput

_DISCONNECT = re.compile(r"\b(disconnect|isolat\w*|unplug|shut\s*down|power\s*off|decommission)\b",
                         re.IGNORECASE)
_SECURE_CLAIM = re.compile(r"\b(is|now|are)\s+(secure|safe|fixed|patched)\b", re.IGNORECASE)


def guard_normalizer(out: NormalizerOutput, threshold: float = CONFIDENCE_THRESHOLD):
    notes = []
    upd = {}
    if out.confidence < threshold and out.lane != "unknown":
        upd.update(lane="unknown", needs_human=True)
        notes.append(f"confidence {out.confidence:.2f} < {threshold:.2f}: forced lane unknown")
    if out.confidence >= threshold and out.lane == "unknown":
        upd.update(needs_human=True)
    return out.model_copy(update=upd), notes


def guard_checker(out: CheckerOutput, kev_candidates: list[dict], lifecycle_candidates: list[dict],
                  normalizer: NormalizerOutput | None = None,
                  threshold: float = CONFIDENCE_THRESHOLD, device: dict | None = None):
    notes = []
    allowed_cve = {c["cveID"] for c in kev_candidates}
    allowed_lc = {c["lifecycle_id"] for c in lifecycle_candidates}
    invented = [c for c in out.evidence_cve if c not in allowed_cve]
    if out.evidence_lifecycle_id and out.evidence_lifecycle_id not in allowed_lc:
        invented.append(out.evidence_lifecycle_id)
    reasons = []
    if invented:
        reasons.append(f"evidence not in candidates: {';'.join(invented)}")
    if out.confidence < threshold:
        reasons.append(f"checker confidence {out.confidence:.2f} < {threshold:.2f}")
    if normalizer is not None and normalizer.lane == "unknown":
        reasons.append("normalizer lane unknown")
    # Without the device record, evidence can't be filled from the candidates (fill_evidence).
    if device is None and out.lane in ("patch", "retire") and not (out.evidence_cve or out.evidence_lifecycle_id):
        reasons.append(f"lane {out.lane} without evidence")
    if reasons:
        notes.append("forced lane unknown: " + "; ".join(reasons))
        return out.model_copy(update=dict(lane="unknown", evidence_cve=[],
                                          evidence_lifecycle_id=None, due_date=None)), notes
    if out.lane == "fine" and out.evidence_cve:
        notes.append("lane fine: KEV evidence cleared")
        out = out.model_copy(update=dict(evidence_cve=[]))
    if device is None:
        if out.lane == "fine" and out.evidence_lifecycle_id:
            out = out.model_copy(update=dict(evidence_lifecycle_id=None))
        return out, notes
    out, n = guard_version(out, device, kev_candidates, lifecycle_candidates)
    notes += n
    out, n = fill_evidence(out, device, kev_candidates, lifecycle_candidates)
    notes += n
    if out.lane in ("patch", "retire") and not (out.evidence_cve or out.evidence_lifecycle_id):
        notes.append(f"forced lane unknown: lane {out.lane} without evidence in the candidates")
        out = out.model_copy(update=dict(lane="unknown", evidence_cve=[],
                                         evidence_lifecycle_id=None, due_date=None))
    return out, notes


def fill_evidence(out: CheckerOutput, device: dict, kev_candidates: list[dict],
                  lifecycle_candidates: list[dict]):
    """Evidence ids are set by code, not left to the model (docs/contracts.md v1.4).

    patch / retire / fine: evidence_lifecycle_id is the model's id if it is a candidate, else the
    governing candidate row (the most specific whose pattern fits the device).
    patch / retire: evidence_cve keeps the model's ids that are candidates; if none, it is filled
    with the KEV candidates whose vendor/product are the governing row's or the device's.
    fine never lists CVEs (that would read as "affected"); unknown carries no evidence.
    Ids outside the candidate lists never get here: guard_checker forces unknown on those.
    """
    if out.lane not in ("patch", "retire", "fine"):
        return out, []
    row = _governing_row(out, device, lifecycle_candidates)
    lc = (row or {}).get("lifecycle_id")  # _governing_row returns the model's row if it is a candidate
    allowed = {k["cveID"] for k in kev_candidates}
    cves = [] if out.lane == "fine" else [c for c in out.evidence_cve if c in allowed]
    if out.lane != "fine" and not cves:
        cves = sorted({c["cveID"] for c in _kev_for(row, device, kev_candidates)})
    if lc == out.evidence_lifecycle_id and cves == list(out.evidence_cve):
        return out, []
    before = set(out.evidence_cve) | {out.evidence_lifecycle_id}
    added = [x for x in cves + ([lc] if lc else []) if x not in before]
    return (out.model_copy(update=dict(evidence_cve=cves, evidence_lifecycle_id=lc)),
            [f"evidence filled from candidates: {';'.join(added) or '(none added)'}"])


def _kev_for(row: dict | None, device: dict, kev_candidates: list[dict]) -> list[dict]:
    """KEV candidates whose vendorProject/product are the lifecycle row's or the device's."""
    row = row or {}
    return [c for c in kev_candidates
            if (_same(c.get("vendorProject"), row.get("vendor")) and _same(c.get("product"), row.get("product")))
            or (_same(c.get("vendorProject"), device.get("vendor")) and _same(c.get("product"), device.get("product")))]


# Strict version grammar (docs/contracts.md "Version grammar"). A version parses only in one of
# these exact forms, each ordered the way the vendor's own advisory orders it:
# - dotted: optional v/V, then dot-separated integers (1.5.1.5, v1.4.2.22);
# - PAN-OS hotfix: major.minor.patch-h<digits> (11.1.4-h7) -> (major, minor, patch, hotfix),
#   hotfix 0 when absent, so it shares the "dotted" family (11.1.4 == 11.1.4-h0);
# - Ivanti Connect Secure: major.minor R release . build, exactly (22.7R2.6), ordered
#   (major, minor, release, build): Ivanti writes "22.7R2.5 and earlier" affected, "fixed in 22.7R2.6";
# - Citrix NetScaler: major.minor-build.sub, exactly (14.1-47.46), ordered (major, minor, build,
#   sub): Citrix writes "14.1 BEFORE 14.1-47.46" affected, "14.1-47.46 and later releases" fixed.
# Each form is its own family; versions from different families are never compared
# (compare_versions returns None), so 22.7.2.6 is not equal to 22.7R2.6. Everything else does not
# parse and the device goes to unknown: "7.0.12 build 523", "7.0.1-5161", "22.7r2.6", "22.3R1",
# "13.1-37.236-FIPS", "11.1.4-H7", "11.1-h3". packaging.version is deliberately not used: PEP 440
# reads "7.0.1-5161" as a post-release (docs/decisions.md, 2026-11-11 version comparison).
# Digits are [0-9], not \d: \d matches non-ASCII digits. Ivanti/NetScaler forms take no v prefix.
_VERSION = re.compile(r"[vV]?([0-9]+(?:\.[0-9]+)*)")
_PANOS_HOTFIX = re.compile(r"[vV]?([0-9]+)\.([0-9]+)\.([0-9]+)-h([0-9]+)")
_IVANTI = re.compile(r"([0-9]+)\.([0-9]+)R([0-9]+)\.([0-9]+)")
_NETSCALER = re.compile(r"([0-9]+)\.([0-9]+)-([0-9]+)\.([0-9]+)")
_FORMS = (("dotted", _PANOS_HOTFIX), ("ivanti", _IVANTI), ("netscaler", _NETSCALER))


def _parse(s: str | None) -> tuple[str, tuple[int, ...]] | None:
    s = (s or "").strip()
    for family, rx in _FORMS:
        if m := rx.fullmatch(s):
            parts = [int(x) for x in m.groups()]
            break
    else:
        if not (m := _VERSION.fullmatch(s)):
            return None
        family, parts = "dotted", [int(x) for x in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:  # 1.5.1 == 1.5.1.0; 11.1.4 == 11.1.4-h0
        parts.pop()
    return family, tuple(parts)


def parse_version(s: str | None) -> tuple[int, ...] | None:
    """Comparable integer tuple, or None if `s` is not in one of the exact forms above."""
    p = _parse(s)
    return p[1] if p else None


def version_family(s: str | None) -> str | None:
    """'dotted' (incl. PAN-OS -h), 'ivanti', 'netscaler', or None if it doesn't parse."""
    p = _parse(s)
    return p[0] if p else None


def compare_versions(a: str | None, b: str | None) -> int | None:
    """-1 / 0 / 1 if both parse in the same family, else None (never compared across formats)."""
    pa, pb = _parse(a), _parse(b)
    if pa is None or pb is None or pa[0] != pb[0]:
        return None
    return (pa[1] > pb[1]) - (pa[1] < pb[1])


_LEADING = re.compile(r"[vV]?([0-9]+(?:\.[0-9]+)*)")


def _leading_numbers(s: str | None) -> tuple[int, ...]:
    """Leading dot-separated integers, untrimmed: '11.1.4-h13' -> (11, 1, 4); 'R81.20' -> ()."""
    m = _LEADING.match((s or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def _shared_prefix(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def select_train_fixes(fixed: str | None, firmware: str | None) -> tuple[list[str], str | None]:
    """Pick the fixed_version entries that apply to this firmware (contracts v1.2).

    fixed_version may hold one value per release train, separated by ';'.
    - One entry: returned as is (no train check; the lifecycle row's pattern scopes it).
    - Several: the firmware must parse; the entries sharing the longest leading numeric prefix
      with it (at least major.minor) are its train. Never compares across trains.
    Returns (entries, None), or ([], reason) when the device must go to unknown.
    """
    entries = [e.strip() for e in (fixed or "").split(";") if e.strip()]
    if len(entries) <= 1:
        return entries, None
    if parse_version(firmware) is None:
        return [], (f"firmware {firmware!r} does not parse, so its release train among "
                    f"fixed versions {';'.join(entries)} can't be identified")
    fw = _leading_numbers(firmware)
    shared = {e: _shared_prefix(fw, _leading_numbers(e)) for e in entries}
    best = max(shared.values())
    if best < 2:
        train = ".".join(str(x) for x in fw[:2])
        return [], (f"no fixed version listed for release train {train} "
                    f"(listed: {';'.join(entries)})")
    return [e for e in entries if shared[e] == best], None


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and (a or "").strip().casefold() == (b or "").strip().casefold()


def _governing_row(out: CheckerOutput, device: dict, lifecycle_candidates: list[dict]):
    if out.evidence_lifecycle_id:
        for r in lifecycle_candidates:
            if r.get("lifecycle_id") == out.evidence_lifecycle_id:
                return r
    # Candidates come most specific first (sim/retrieval.py); take the first whose pattern fits.
    for r in lifecycle_candidates:
        if retrieval.pattern_matches(r, device):
            return r
    return None


def guard_version(out: CheckerOutput, device: dict, kev_candidates: list[dict],
                  lifecycle_candidates: list[dict]):
    """Deterministic patch/fine check for a KEV-listed product with a lifecycle row.

    Applies only when the Checker said patch or fine (retire and unknown are left alone).
    The firmware is the inventory's firmware_version_raw (the Normalizer's version if blank).
    - fixed_version blank, or no lifecycle row at all: unknown, "fixed version not documented"
      (checker.md rule 4.5: a KEV match with no documented fix is never patch or fine).
    - fixed_version with several ';' entries: only the entry on the firmware's release train is
      used (select_train_fixes); no entry on that train, or unparseable firmware: unknown.
    - either version doesn't parse, or they are in different version formats: unknown.
    - both parse: firmware < fixed -> patch, else fine; a contradicting lane is overridden.
    """
    if out.lane not in ("patch", "fine"):
        return out, []
    row = _governing_row(out, device, lifecycle_candidates)
    kev = _kev_for(row, device, kev_candidates)
    if not kev and not (out.lane == "patch" and out.evidence_cve):
        return out, []  # not a KEV-listed product: nothing to compare

    lc_id = row.get("lifecycle_id") if row else "no lifecycle row"
    firmware = (device.get("firmware_version_raw") or "").strip() or (device.get("version") or "").strip()
    fixed = ((row or {}).get("fixed_version") or "").strip()

    def unknown(why: str):
        note = f"version guard: lane {out.lane} -> unknown ({why}; {lc_id})"
        return out.model_copy(update=dict(
            lane="unknown", evidence_cve=[], evidence_lifecycle_id=None, due_date=None,
            reason=f"[version guard] {why}. {out.reason}")), [note]

    if not fixed:
        return unknown("fixed version not documented")
    train, why = select_train_fixes(fixed, firmware)
    if why:
        return unknown(why)
    bad = [f"{k} {v!r}" for k, v in [("firmware", firmware)] + [("fixed_version", f) for f in train]
           if parse_version(v) is None]
    if bad:
        return unknown("version could not be compared: " + ", ".join(bad) + " does not parse")
    mixed = [f for f in train if compare_versions(firmware, f) is None]
    if mixed:
        return unknown(f"firmware {firmware!r} and fixed_version {';'.join(mixed)!r} are written in "
                       "different version formats and can't be compared")
    below = {compare_versions(firmware, f) < 0 for f in train}
    fixed = ";".join(train)
    if len(below) > 1:  # several fixes on the same train and the firmware sits between them
        return unknown(f"firmware {firmware} is between fixed versions {fixed} on its release train")
    cmp = -1 if below == {True} else 1
    expected = "patch" if cmp < 0 else "fine"
    if out.lane == expected:
        return out, []
    why = (f"firmware {firmware} is {'below' if cmp < 0 else 'at or above'} fixed version "
           f"{fixed} ({lc_id}), so lane {expected}, not {out.lane}")
    if expected == "patch":
        cves = sorted({c["cveID"] for c in kev}) or list(out.evidence_cve)
        dues = sorted(c["dueDate"] for c in kev if c.get("dueDate"))
        upd = dict(lane="patch", evidence_cve=cves, evidence_lifecycle_id=lc_id,
                   due_date=dt.date.fromisoformat(dues[0]) if dues else None)
    else:
        upd = dict(lane="fine", evidence_cve=[], evidence_lifecycle_id=None, due_date=None)
    upd["reason"] = f"[version guard override] {why}. {out.reason}"
    return out.model_copy(update=upd), [f"version guard override: {why}"]


# Settings keys (docs/contracts.md, Settings tab) and their defaults.
KEV_OVERDUE_GRACE_KEY = "kev_overdue_grace_days"       # KEV dueDate passed: deadline = as_of + this
KEV_OVERDUE_GRACE_DEFAULT = 14
RETIRE_DAYS_KEY = "retire_days"                        # retire: deadline = as_of + this
RETIRE_DAYS_DEFAULT = 30
RETIRE_ISOLATION_DAYS_KEY = "retire_isolation_days"    # retire: interim isolation within this
RETIRE_ISOLATION_DAYS_DEFAULT = 7
ISSUE_BY_LANE = {"patch": "patch", "retire": "retire", "unknown": "identify"}
_CISA_PASSED = re.compile(r"CISA[^.]*\bpassed\b", re.IGNORECASE)


def _setting(settings: dict | None, key: str, default: int) -> int:
    v = (settings or {}).get(key)
    return int(v) if v not in (None, "") else default


def _date(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def kev_deadline(due_date: dt.date | str | None, as_of_date: dt.date | str,
                 grace_days: int = KEV_OVERDUE_GRACE_DEFAULT) -> tuple[dt.date | None, bool]:
    """Effective deadline from a KEV dueDate. If the dueDate is before as_of_date (CISA's date
    has passed), the deadline is as_of_date + grace_days. Returns (deadline, overdue)."""
    if not due_date:
        return None, False
    due, as_of = _date(due_date), _date(as_of_date)
    if due < as_of:
        return as_of + dt.timedelta(days=int(grace_days)), True
    return due, False


def retire_deadline(as_of_date: dt.date | str, settings: dict | None = None) -> dt.date:
    """Retire action deadline: as_of_date + Settings.retire_days (default 30). The support end
    date is evidence for the message, never the deadline (it is always in the past)."""
    return _date(as_of_date) + dt.timedelta(days=_setting(settings, RETIRE_DAYS_KEY, RETIRE_DAYS_DEFAULT))


def overdue_sentence(due: dt.date | str, deadline: dt.date | str, as_of: str, grace: int) -> str:
    """The sentence the owner message must carry when the KEV due date has passed."""
    as_of_d = _date(as_of)
    why = (f" ({grace} days from {as_of})"
           if str(deadline) == (as_of_d + dt.timedelta(days=int(grace))).isoformat() else "")
    return f"The CISA KEV due date {due} has passed, so the deadline is {deadline}{why}."


def retire_sentence(support_end: dt.date | str | None, as_of: dt.date | str,
                    settings: dict | None = None, dnt: bool = False) -> str:
    """Trusted retire wording, rebuilt from the Checker's date and Settings (never model text).
    do_not_touch devices get no isolation or replacement wording: a named person decides."""
    as_of_d = _date(as_of)
    days = _setting(settings, RETIRE_DAYS_KEY, RETIRE_DAYS_DEFAULT)
    iso = _setting(settings, RETIRE_ISOLATION_DAYS_KEY, RETIRE_ISOLATION_DAYS_DEFAULT)
    deadline = retire_deadline(as_of_d, settings)
    ended = f"Vendor support ended on {support_end}. " if support_end else ""
    if dnt:
        return f"{ended}A named person must decide the next step by {deadline}."
    return (f"{ended}Please replace or decommission the device by {deadline} ({days} days from "
            f"{as_of_d}). Until then, isolate it from the network within {iso} days "
            f"(by {as_of_d + dt.timedelta(days=iso)}).")


def _retire_facts_present(body: str, support_end, as_of, settings, dnt: bool) -> bool:
    b = body.casefold()
    need = [str(retire_deadline(as_of, settings))]
    if support_end:
        need.append(f"support ended on {support_end}")
    if not dnt:
        iso = _setting(settings, RETIRE_ISOLATION_DAYS_KEY, RETIRE_ISOLATION_DAYS_DEFAULT)
        need.append(f"within {iso} days")
    return all(n.casefold() in b for n in need)


def deadline_sentence(check: CheckerOutput, as_of: str | None, settings: dict | None,
                      dnt: bool) -> str:
    """The trusted deadline sentence a message must carry, or '' (patch on time, fine, unknown)."""
    if not as_of:
        return ""
    if check.lane == "retire":
        return retire_sentence(check.due_date, as_of, settings, dnt)
    if check.lane == "patch" and check.due_date:
        grace = _setting(settings, KEV_OVERDUE_GRACE_KEY, KEV_OVERDUE_GRACE_DEFAULT)
        eff, overdue = kev_deadline(check.due_date, as_of, grace)
        if overdue:
            return overdue_sentence(check.due_date, eff, as_of, grace)
    return ""


# owner_email (F1, guards-v2). One plain addr-spec (RFC 5322 3.4.1, local-part "@" domain), in a
# deliberately narrow ASCII subset: dot-atom local part from [A-Za-z0-9._%+-], a dotted DNS
# domain of letter/digit/hyphen labels and an alphabetic TLD. Anything else is not a recipient:
# two addresses (",", ";", space), display names or angle brackets, CR/LF or any control
# character (RFC 5322 2.2: a header field ends at CRLF, so a CRLF in the value starts a new
# header such as "Bcc:"), and every non-ASCII character (a look-alike domain such as Cyrillic
# "еxample.org"; UTS #39 section 4). Punycode labels ("xn--") are refused too: they are how a
# non-ASCII domain is written in ASCII. email.utils.parseaddr is not used: it is lenient by
# design before Python 3.13 (strict=True became the default in 3.13; this repo runs 3.11).
_LOCAL = r"[A-Za-z0-9%+_-]+(?:\.[A-Za-z0-9%+_-]+)*"
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_ADDR = re.compile(rf"{_LOCAL}@(?:{_LABEL}\.)+[A-Za-z]{{2,63}}")


def owner_email_problem(addr) -> str | None:
    """Why `addr` can't be used as a recipient, or None when it is one well-formed address."""
    if not isinstance(addr, str) or not addr:
        return "owner_email is empty"
    if any(c in addr for c in "\r\n"):
        return "owner_email contains a line break (header injection)"
    if any(ord(c) < 32 or ord(c) == 127 for c in addr):
        return "owner_email contains a control character"
    if not addr.isascii():
        return "owner_email contains non-ASCII characters (possible look-alike domain)"
    if addr.count("@") != 1:
        return "owner_email is not exactly one address"
    if len(addr) > 254 or not _ADDR.fullmatch(addr):
        return "owner_email is not one plain address (local@domain)"
    if any(lbl.lower().startswith("xn--") for lbl in addr.split("@")[1].split(".")):
        return "owner_email domain is an internationalized (punycode) name"
    return None


def recipient(lane: str, device: dict, settings: dict | None) -> str:
    """Message recipient, set by rule and never by the model: the approver for unknown devices
    (a human must identify them), else the device's owner_email. An owner_email that is not one
    well-formed ASCII address (owner_email_problem) is never a recipient: the message goes to the
    approver, who reviews the record (human-review path)."""
    approver = (settings or {}).get("approver_email") or "approver@example.org"
    if lane == "unknown":
        return approver
    owner = device.get("owner_email") or ""
    return approver if owner_email_problem(owner) else owner


def guard_planner(out: PlannerOutput, device: dict, checker: CheckerOutput,
                  as_of_date: str | None = None, settings: dict | None = None):
    """Deadlines (agents/planner.md rule 8), when `as_of_date` is given:
    - patch: the Checker's due_date is the KEV dueDate; if it is before as_of_date the deadline is
      as_of_date + kev_overdue_grace_days and the message says the CISA date passed.
    - retire: the Checker's due_date is the support end date, kept as evidence in the message
      ("support ended on X"); the deadline is as_of_date + retire_days, with interim isolation
      advice within retire_isolation_days (none for do_not_touch devices).
    Those sentences are rebuilt from trusted fields, never copied from model text.
    The ticket issue is set from the lane (patch / retire / identify). The recipient is not the
    model's to choose (see `recipient`)."""
    notes = []
    upd = {}
    dnt = _truthy(device.get("do_not_touch"))
    trusted = deadline_sentence(checker, as_of_date, settings, dnt)
    if as_of_date and checker.lane == "retire":
        want = retire_deadline(as_of_date, settings)
        if out.deadline != want:
            upd["deadline"] = want
            notes.append(f"retire deadline {out.deadline} -> {want} (as_of + retire_days)")
        if out.message and not _retire_facts_present(out.message.body, checker.due_date,
                                                     as_of_date, settings, dnt):
            upd["message"] = out.message.model_copy(
                update={"body": f"{out.message.body.rstrip()} {trusted}"})
            notes.append("message: added support end date, retire deadline and isolation advice")
    elif trusted:  # patch whose KEV due date has passed
        want = kev_deadline(checker.due_date, as_of_date,
                            _setting(settings, KEV_OVERDUE_GRACE_KEY, KEV_OVERDUE_GRACE_DEFAULT))[0]
        if out.deadline != want:
            upd["deadline"] = want
            notes.append(f"KEV due date {checker.due_date} passed: deadline {out.deadline} -> {want}")
        if out.message and not _CISA_PASSED.search(out.message.body):
            upd["message"] = out.message.model_copy(
                update={"body": f"{out.message.body.rstrip()} {trusted}"})
            notes.append("message: added that the CISA due date has passed")
    if not out.requires_approval:
        upd["requires_approval"] = True
        notes.append("requires_approval forced true")
    if out.lane != checker.lane:
        upd["lane"] = checker.lane
        notes.append(f"lane {out.lane} replaced by checker lane {checker.lane}")
    issue = ISSUE_BY_LANE.get(checker.lane)
    if out.ticket and issue and out.ticket.issue != issue:
        upd["ticket"] = out.ticket.model_copy(update={"issue": issue})
        notes.append(f"ticket issue {out.ticket.issue} -> {issue} (from lane {checker.lane})")
    if dnt:
        if not out.escalate_to_human:
            upd["escalate_to_human"] = True
            notes.append("do_not_touch: escalate_to_human forced true")
        msg = upd.get("message", out.message)
        if msg and _DISCONNECT.search(msg.body):
            body = ("This device is flagged do-not-touch. Deming makes no disconnection or "
                    "isolation proposal; a named person must decide the next step. "
                    f"Lane: {checker.lane}. Evidence: "
                    f"{';'.join(checker.evidence_cve + ([checker.evidence_lifecycle_id] if checker.evidence_lifecycle_id else [])) or 'none'}.")
            if trusted:
                body += " " + trusted
            upd["message"] = msg.model_copy(update={"body": body})
            notes.append("do_not_touch: disconnect/isolate wording removed from message")
    return out.model_copy(update=upd), notes


def guard_verifier(out: VerifierOutput, ticket_lane: str, recheck_lane: str | None,
                   record_present: bool | None = None):
    """Close is allowed when the device is gone from the inventory, for any ticket type (patch,
    retire or identify), matching sim/loop.decide_verification; or when the version changed and
    the re-check is fine. `ticket_lane` is informational only. `record_present` (when the caller
    knows it) overrules a model that claims device_removed while the row is still there."""
    notes = []
    upd = {}
    removed = out.observed_change == "device_removed"
    if removed and record_present:
        notes.append("observed_change device_removed contradicts the inventory (row present)")
        removed = False
    if out.decision == "close":
        ok = (removed
              or (out.observed_change == "version_changed" and recheck_lane == "fine"))
        if not ok:
            upd["decision"] = "escalate"
            notes.append(f"close not allowed ({out.observed_change}, recheck {recheck_lane}): escalate")
    if _SECURE_CLAIM.search(out.note):
        upd["note"] = ("The inventory record was compared with the ticket; this only confirms what "
                       f"the record shows ({out.observed_change}), not that the device is secure.")
        notes.append("note rewritten: it claimed the device is secure/fixed")
    return out.model_copy(update=upd), notes


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() == "true"
