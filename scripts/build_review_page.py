"""Build review/review.html: a static click-through page for the two label reviewers.

One device at a time: raw name, firmware, the ground-truth label, evidence CVEs (with their KEV
entry), the lifecycle row, the source note with clickable source URLs, and the mechanical check
from scripts/check_labels.py. The reviewer picks verified / disagree / unsure (never pre-filled),
adds notes, and exports a CSV: device_id,reviewer,decision,notes. The reviewer name is required
before export. Progress is saved in the browser and can be restored by importing the export.

Run (after scripts/check_labels.py):
  python scripts/build_review_page.py
Offline: reads only repo files. The generated page needs no server and no network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_labels  # noqa: E402
from review_common import data_hash, page  # noqa: E402

EXPORT_HEADER = ["device_id", "reviewer", "decision", "notes"]
DECISIONS = ["verified", "disagree", "unsure"]


def build_data(root: Path = ROOT, checks_path: Path | None = None) -> dict:
    inputs = check_labels.load_inputs(root)
    checks_path = checks_path or root / "review" / "label_checks.json"
    if not checks_path.exists():
        raise SystemExit(f"{checks_path} not found: run scripts/check_labels.py first")
    checks = json.loads(checks_path.read_text(encoding="utf-8"))
    by_check = {d["device_id"]: d for d in checks["devices"]}
    risk_order = [d["device_id"] for d in checks["devices"]]
    lc_by = {r["lifecycle_id"]: r for r in inputs["lifecycle"]}
    devices = []
    for g in inputs["gt"]:
        did = g["device_id"]
        inv = inputs["inventory"].get(did, {})
        c = by_check.get(did)
        cves = []
        for cid in [x for x in g["evidence_cve"].split(";") if x]:
            e = inputs["kev"].get(cid, {})
            cves.append({"id": cid, "in_kev": bool(e), "vendor": e.get("vendorProject", ""),
                         "product": e.get("product", ""), "name": e.get("vulnerabilityName", ""),
                         "required_action": e.get("requiredAction", ""), "due": e.get("dueDate", ""),
                         "added": e.get("dateAdded", "")})
        lc_id = g["evidence_lifecycle_id"] or (c or {}).get("governing_lifecycle_id") or ""
        lc = lc_by.get(lc_id)
        devices.append({
            "device_id": did, "group": g["group"],
            "inventory": {k: inv.get(k, "") for k in ("device_name_raw", "firmware_version_raw", "location",
                                                     "internet_facing", "criticality", "do_not_touch")},
            "label": {k: g[k] for k in ("vendor", "product", "version", "lane", "evidence_cve",
                                        "evidence_lifecycle_id", "source_row_note")},
            "cves": cves,
            "lifecycle": ({k: lc.get(k, "") for k in ("lifecycle_id", "vendor", "product", "model_pattern",
                                                     "eol_date", "last_security_support_date",
                                                     "patch_available", "fixed_version", "source_url",
                                                     "notes")} | {"cited": bool(g["evidence_lifecycle_id"])}
                          if lc else None),
            "check": ({"mechanical": c["mechanical"], "recomputed_lane": c["recomputed_lane"],
                       "recompute_reason": c["recompute_reason"], "firmware_lane": c["firmware_lane"],
                       "firmware_reason": c["firmware_reason"],
                       "findings": [f for f in c["findings"]],
                       "source": c["source"]["result"], "urls": c["source"]["urls"],
                       "needles": c["source"]["needles"]} if c else None),
        })
    data = {"as_of_date": checks.get("as_of_date"), "checked_at": checks.get("generated_at"),
            "risk_order": risk_order, "devices": devices, "export_header": EXPORT_HEADER,
            "decisions": DECISIONS}
    # Saved progress is keyed on the labels and inventory only: re-running the checks keeps it,
    # but a label change starts a fresh review (an old "verified" must not carry over).
    data["key"] = "deming-review:" + data_hash([[d["device_id"], d["label"], d["inventory"]] for d in devices])
    return data


BODY = """
<div class="wrap">
  <h1>Deming label review</h1>
  <p class="sub">Check each ground-truth label against its sources. All devices are synthetic.
  Labels as of <b id="asof"></b>; mechanical checks run <span id="checked"></span>.</p>

  <div class="panel">
    <div class="bar">
      <div class="grow">
        <label class="field" for="reviewer">Your initials (required before export)</label>
        <input type="text" id="reviewer" autocomplete="off" placeholder="e.g. AB" maxlength="40">
      </div>
      <div>
        <label class="field" for="order">Order</label>
        <select id="order">
          <option value="risk">Flagged first (highest risk first)</option>
          <option value="id">Device ID</option>
        </select>
      </div>
      <div style="align-self:end">
        <label><input type="checkbox" id="onlyflag"> Only flagged / needs human</label>
      </div>
    </div>
    <div class="progress" aria-hidden="true"><div id="bar"></div></div>
    <div class="small muted" id="progress" role="status"></div>
    <div class="small muted" id="saved"></div>
  </div>

  <div id="card"></div>

  <div class="panel">
    <div class="nav">
      <button id="prev">&larr; Previous</button>
      <button id="next">Next &rarr;</button>
      <button id="nextopen">Next undecided</button>
      <select id="jump" aria-label="Jump to device"></select>
    </div>
  </div>

  <div class="panel">
    <h2>Finish</h2>
    <div class="bar">
      <button class="primary" id="export">Export CSV</button>
      <label class="small"><input type="file" id="import" accept=".csv,text/csv" class="hidden">
        <button type="button" id="importbtn">Resume from an exported CSV</button></label>
    </div>
    <p class="err" id="err" role="alert"></p>
    <p class="small muted">The export has one row per device: device_id, reviewer, decision, notes.
    Undecided devices are exported with a blank decision. Send the file to the team; nothing is
    uploaded from this page.</p>
  </div>
</div>
"""

APP = r"""
(function(){
var D = JSON.parse(document.getElementById('data').textContent);
var byId = {}; D.devices.forEach(function(d){ byId[d.device_id] = d; });
var idOrder = D.devices.map(function(d){ return d.device_id; }).sort();
var S = storageGet(D.key) || {reviewer: '', decisions: {}, current: null, order: 'risk', onlyFlagged: false};
var $ = function(id){ return document.getElementById(id); };
$('asof').textContent = D.as_of_date || '?';
$('checked').textContent = D.checked_at || '(not run)';
$('reviewer').value = S.reviewer || '';
$('order').value = S.order || 'risk';
$('onlyflag').checked = !!S.onlyFlagged;

function flagged(d){ return d.check && (d.check.mechanical === 'flag' || d.check.source === 'needs_human'); }
function list(){
  var ids = S.order === 'id' ? idOrder.slice() : D.risk_order.filter(function(i){ return byId[i]; });
  D.devices.forEach(function(d){ if (ids.indexOf(d.device_id) < 0) ids.push(d.device_id); });
  return S.onlyFlagged ? ids.filter(function(i){ return flagged(byId[i]); }) : ids; }
function decided(id){ var x = S.decisions[id]; return x && x.decision; }
function save(){
  var ok = storageSet(D.key, S);
  $('saved').textContent = ok ? 'Progress saved in this browser.' :
    'This browser does not allow saving here. Export regularly and use "Resume from an exported CSV".'; }

function chipFor(kind, text){ return el('span', {cls: 'chip ' + kind, text: text}); }

function render(){
  var ids = list();
  if (!ids.length){ $('card').replaceChildren(el('div', {cls: 'panel', text: 'No devices match the filter.'})); updateProgress(); return; }
  if (ids.indexOf(S.current) < 0) S.current = ids[0];
  var d = byId[S.current], c = d.check, inv = d.inventory, L = d.label, pos = ids.indexOf(S.current);

  var head = el('div', {cls: 'panel'},
    el('div', {cls: 'bar'},
      el('div', {cls: 'grow'}, el('h1', {text: d.device_id}),
        el('div', {cls: 'small muted', text: 'Device ' + (pos + 1) + ' of ' + ids.length + ' · group ' + d.group})),
      el('div', null,
        c ? chipFor(c.mechanical === 'flag' ? 'bad' : 'ok', 'Mechanical: ' + c.mechanical) : chipFor('warn', 'Mechanical: not run'),
        c ? chipFor(c.source === 'ok' ? 'ok' : 'warn', 'Sources: ' + (c.source === 'ok' ? 'ok' : 'needs human')) : null,
        inv.do_not_touch === 'true' ? chipFor('bad', 'do not touch') : null)));

  var invPanel = el('div', {cls: 'panel'}, el('h2', {text: 'Inventory row (what the owner typed)'}),
    kv([['Raw name', el('div', {cls: 'raw', text: inv.device_name_raw})],
        ['Firmware', inv.firmware_version_raw ? el('span', {cls: 'raw', text: inv.firmware_version_raw}) : ''],
        ['Location', inv.location], ['Internet-facing', inv.internet_facing],
        ['Criticality', inv.criticality], ['Do not touch', inv.do_not_touch]]));

  var labPanel = el('div', {cls: 'panel'}, el('h2', {text: 'Ground-truth label (to check)'}),
    kv([['Lane', el('span', {cls: 'lane', text: L.lane})], ['Vendor', L.vendor], ['Product', L.product],
        ['Version', L.version], ['Why (source note)', L.source_row_note]]));

  var ev = el('div', {cls: 'panel'}, el('h2', {text: 'Evidence'}));
  if (d.cves.length){
    var ul = el('ul', {cls: 'plain'});
    d.cves.forEach(function(x){
      ul.appendChild(el('li', null, el('b', {text: x.id}), ' ',
        x.in_kev ? el('span', {text: '· KEV: ' + x.vendor + ' / ' + x.product + ' · ' + x.name + ' · added ' + x.added + ' · due ' + x.due})
                 : chipFor('bad', 'not in the KEV copy'), ' ',
        link('https://nvd.nist.gov/vuln/detail/' + x.id, 'NVD page'),
        x.required_action ? el('div', {cls: 'small muted', text: 'KEV required action: ' + x.required_action}) : null)); });
    ev.appendChild(ul);
  } else ev.appendChild(el('p', {cls: 'muted', text: 'No KEV CVE cited.'}));
  if (d.lifecycle){
    var l = d.lifecycle;
    ev.appendChild(el('p', {cls: 'small', text: (l.cited ? 'Cited lifecycle row ' : 'Lifecycle row found by the checker (not cited by the label) ') + l.lifecycle_id}));
    ev.appendChild(kv([['Vendor / product', l.vendor + ' / ' + l.product], ['Model pattern', l.model_pattern],
      ['End of life', l.eol_date], ['Last security support', l.last_security_support_date],
      ['Patch available', l.patch_available], ['Fixed version', l.fixed_version],
      ['Row source', link(l.source_url)], ['Row notes', l.notes]]));
  } else ev.appendChild(el('p', {cls: 'muted', text: 'No lifecycle row cited or found.'}));

  var src = el('div', {cls: 'panel'}, el('h2', {text: 'Sources: open them and check'}));
  if (c && c.urls.length){
    var su = el('ul', {cls: 'plain'});
    c.urls.forEach(function(u){
      var kind = u.result === 'text' ? 'ok' : 'warn';
      su.appendChild(el('li', null, link(u.url), ' ', chipFor(kind, u.result === 'text' ? 'script read it (HTTP ' + u.status + ')' : 'needs you in a browser'),
        u.result !== 'text' ? el('div', {cls: 'small muted', text: u.note}) : null)); });
    src.appendChild(su);
  } else src.appendChild(el('p', {cls: 'muted', text: 'No source URL recorded.'}));
  if (c && c.needles.length){
    src.appendChild(el('p', {cls: 'small', text: 'Strings the script looked for on these pages:'}));
    var nu = el('ul', {cls: 'plain small'});
    c.needles.forEach(function(n){
      var kind = n.status === 'found' ? 'ok' : (n.status === 'not_found' ? 'bad' : 'warn');
      var label = n.status === 'found' ? 'found' + (n.where.length ? ' (' + n.where.map(function(w){ return w.split('/')[2] || w; }).join(', ') + ')' : '')
                : n.status === 'not_found' ? 'not found by script: check by eye' : 'not checked: page unreadable by script';
      nu.appendChild(el('li', null, el('b', {text: n.kind.replace(/_/g, ' ') + ': '}), '"' + n.text + '" ', chipFor(kind, label))); });
    src.appendChild(nu);
  }

  var mech = el('div', {cls: 'panel'}, el('h2', {text: 'Mechanical check'}));
  if (c){
    mech.appendChild(kv([['Recomputed lane', el('span', null, el('span', {cls: 'lane', text: c.recomputed_lane}), ' ', c.recompute_reason)],
      ['With raw firmware', c.firmware_lane ? el('span', null, el('span', {cls: 'lane', text: c.firmware_lane}), ' ', c.firmware_reason) : '(no firmware)']]));
    var fl = c.findings.filter(function(f){ return f.kind !== 'info'; });
    if (fl.length){ var fu = el('ul', {cls: 'plain'});
      fl.forEach(function(f){ fu.appendChild(el('li', null, chipFor(f.severity >= 2 ? 'bad' : 'warn', f.kind.replace(/_/g, ' ')), f.text)); });
      mech.appendChild(fu);
    } else mech.appendChild(el('p', {cls: 'muted', text: 'No mechanical rule disagreed. That does not mean the label is right: you still check the sources.'}));
  } else mech.appendChild(el('p', {cls: 'muted', text: 'Not run for this device.'}));

  var cur = S.decisions[d.device_id] || {decision: '', notes: ''};
  var choices = el('div', {cls: 'choices', role: 'radiogroup', 'aria-label': 'Your decision'});
  D.decisions.forEach(function(v){
    var input = el('input', {type: 'radio', name: 'decision', value: v});
    if (cur.decision === v) input.checked = true;
    input.addEventListener('change', function(){ setDecision(d.device_id, v); });
    var help = {verified: 'Verified: the label matches the sources', disagree: 'Disagree: something is wrong',
                unsure: 'Unsure: I could not confirm it'}[v];
    choices.appendChild(el('label', {cls: cur.decision === v ? 'on' : ''}, input, help)); });
  var notes = el('textarea', {id: 'notes', placeholder: 'What did you check? If you disagree or are unsure, say why.'});
  notes.value = cur.notes || '';
  notes.addEventListener('input', function(){ setNotes(d.device_id, notes.value); });
  var dec = el('div', {cls: 'panel'}, el('h2', {text: 'Your decision'}), choices,
    el('label', {cls: 'field', 'for': 'notes', text: 'Notes'}), notes,
    cur.decision ? el('button', {type: 'button', cls: 'small', text: 'Clear my decision', onclick: function(){ setDecision(d.device_id, ''); render(); }}) : null);

  $('card').replaceChildren(head, el('div', {cls: 'grid2'}, invPanel, labPanel), ev, src, mech, dec);
  $('prev').disabled = pos <= 0; $('next').disabled = pos >= ids.length - 1;
  var jump = $('jump'); jump.replaceChildren();
  ids.forEach(function(i){ var x = byId[i];
    var o = el('option', {value: i, text: (decided(i) ? '✓ ' : '· ') + i + ' — ' + x.label.lane + (flagged(x) ? ' (flagged)' : '')});
    if (i === S.current) o.selected = true; jump.appendChild(o); });
  updateProgress(); }

function setDecision(id, v){ var x = S.decisions[id] || {decision: '', notes: ''}; x.decision = v; S.decisions[id] = x; save();
  Array.prototype.forEach.call(document.querySelectorAll('.choices label'), function(lb){
    lb.className = lb.querySelector('input').checked ? 'on' : ''; });
  updateProgress(); refreshJump(); }
function setNotes(id, v){ var x = S.decisions[id] || {decision: '', notes: ''}; x.notes = v; S.decisions[id] = x; save(); }
function refreshJump(){ Array.prototype.forEach.call($('jump').options, function(o){
  var x = byId[o.value]; o.textContent = (decided(o.value) ? '✓ ' : '· ') + o.value + ' — ' + x.label.lane + (flagged(x) ? ' (flagged)' : ''); }); }
function updateProgress(){
  var n = D.devices.filter(function(d){ return decided(d.device_id); }).length, t = D.devices.length;
  $('bar').style.width = (100 * n / t) + '%';
  var nf = D.devices.filter(flagged).length;
  $('progress').textContent = n + ' of ' + t + ' devices decided · ' + nf + ' flagged or needing a browser check'; }
function go(delta){ var ids = list(), i = ids.indexOf(S.current) + delta;
  if (i >= 0 && i < ids.length){ S.current = ids[i]; save(); render(); window.scrollTo(0, 0); } }

$('prev').onclick = function(){ go(-1); };
$('next').onclick = function(){ go(1); };
$('nextopen').onclick = function(){ var ids = list(), i = ids.indexOf(S.current);
  for (var k = 1; k <= ids.length; k++){ var id = ids[(i + k) % ids.length]; if (!decided(id)){ S.current = id; save(); render(); window.scrollTo(0, 0); return; } }
  $('err').textContent = 'Every device in this list has a decision.'; };
$('jump').onchange = function(){ S.current = this.value; save(); render(); };
$('order').onchange = function(){ S.order = this.value; save(); render(); };
$('onlyflag').onchange = function(){ S.onlyFlagged = this.checked; save(); render(); };
$('reviewer').oninput = function(){ S.reviewer = this.value; $('err').textContent = ''; save(); };
document.addEventListener('keydown', function(e){ if (typing(e)) return;
  if (e.key === 'ArrowRight') go(1); if (e.key === 'ArrowLeft') go(-1); });

$('export').onclick = function(){
  var who = $('reviewer').value.trim();
  if (!validReviewer(who)){ $('err').textContent = 'Enter your initials first (letters, spaces, dots or hyphens; no commas).';
    $('reviewer').focus(); return; }
  var open = D.devices.filter(function(d){ return !decided(d.device_id); }).length;
  if (open && !window.confirm(open + ' device(s) have no decision yet. Export anyway? (You can export again later.)')) return;
  var rows = idOrder.map(function(id){ var x = S.decisions[id] || {};
    return {device_id: id, reviewer: who, decision: x.decision || '', notes: x.notes || ''}; });
  download('deming-review-' + slug(who) + '-' + fileStamp() + '.csv', toCsv(D.export_header, rows));
  $('err').textContent = ''; };

$('importbtn').onclick = function(){ $('import').click(); };
$('import').onchange = function(){
  var f = this.files && this.files[0]; if (!f) return;
  var r = new FileReader();
  r.onload = function(){
    var rows = csvObjects(r.result), n = 0;
    if (!rows.length || !('device_id' in rows[0]) || !('decision' in rows[0])){ $('err').textContent = 'That file is not a review export.'; return; }
    rows.forEach(function(x){ if (!byId[x.device_id]) return;
      var dcs = D.decisions.indexOf(x.decision) >= 0 ? x.decision : '';
      S.decisions[x.device_id] = {decision: dcs, notes: x.notes || ''}; n++;
      if (!S.reviewer && x.reviewer) S.reviewer = x.reviewer; });
    $('reviewer').value = S.reviewer || ''; save(); render();
    $('err').textContent = 'Restored ' + n + ' device(s) from ' + f.name + '.'; };
  r.readAsText(f); this.value = ''; };

save(); render();
})();
"""


def build(out: Path, root: Path = ROOT, checks_path: Path | None = None) -> Path:
    data = build_data(root, checks_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page("Deming label review", BODY, data, APP), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "review" / "review.html")
    ap.add_argument("--checks", type=Path, default=ROOT / "review" / "label_checks.json")
    a = ap.parse_args(argv)
    p = build(a.out, ROOT, a.checks)
    print(f"Wrote {p} ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
