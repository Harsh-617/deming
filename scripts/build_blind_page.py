"""Build review/blind.html: a static page for blind labelling, from the worksheet only.

Reads ONLY eval/blind/blind_worksheet.csv, and from it only blind_id (the row key that
eval/blind/agreement.py joins on), device_name_raw and firmware_version_raw. It never opens
ground_truth.csv, blind_key.csv, lifecycle.csv, kev.json or any check output, so the page cannot
leak a label (tests/test_review_tools.py checks the generated file anyway).

The labeller fills vendor, product, version, lane (patch|retire|fine|unknown), the source URL
used, and notes; their name is required before export. The export is the worksheet format that
eval/blind/agreement.py reads (worksheet columns in order, `labeller` = name, `comment` = notes),
plus a trailing `source_url_used` column, which agreement.py ignores.

Run:
  python scripts/build_blind_page.py
"""
from __future__ import annotations

import argparse
import csv
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from review_common import data_hash, page  # noqa: E402

WORKSHEET = ROOT / "eval" / "blind" / "blind_worksheet.csv"
INPUT_COLUMNS = ("blind_id", "device_name_raw", "firmware_version_raw")
EXTRA_COLUMN = "source_url_used"
LANES = ["patch", "retire", "fine", "unknown"]
AS_OF_DEFAULT = "2026-11-12"


def build_data(worksheet: Path = WORKSHEET) -> dict:
    with Path(worksheet).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = [{c: (r.get(c) or "").strip() for c in INPUT_COLUMNS} for r in reader]
    missing = [c for c in INPUT_COLUMNS + ("labeller", "vendor", "product", "version", "lane", "comment")
               if c not in header]
    if missing:
        raise SystemExit(f"{worksheet}: missing column(s) {missing}")
    data = {"rows": rows, "export_header": header + [EXTRA_COLUMN], "lanes": LANES}
    data["key"] = "deming-blind:" + data_hash(rows)
    return data


BODY = """
<div class="wrap">
  <h1>Deming blind labelling</h1>
  <p class="sub">Label each device yourself from its name and firmware. All devices are synthetic.
  Do this <b>before</b> you open the label review page, and don't look at any answers while you work.</p>

  <div class="panel">
    <label class="field" for="reviewer">Your initials (required before export)</label>
    <input type="text" id="reviewer" autocomplete="off" placeholder="e.g. AB" maxlength="40">
    <div class="progress" aria-hidden="true"><div id="bar"></div></div>
    <div class="small muted" id="progress" role="status"></div>
    <div class="small muted" id="saved"></div>
  </div>

  <div id="card"></div>

  <div class="panel">
    <div class="nav">
      <button id="prev">&larr; Previous</button>
      <button id="next">Next &rarr;</button>
      <button id="nextopen">Next unfinished</button>
      <select id="jump" aria-label="Jump to device"></select>
    </div>
  </div>

  <div class="panel">
    <h2>Lanes</h2>
    <ul class="plain small">
      <li><b>patch</b>: the product is supported, it has a known exploited vulnerability (CISA KEV) at this version, and the vendor has a fix.</li>
      <li><b>retire</b>: the vendor no longer supports it (past end of life or end of security support), even if it is also in KEV.</li>
      <li><b>fine</b>: supported, and no known exploited vulnerability at this version.</li>
      <li><b>unknown</b>: you can't tell what it is, or can't decide from the name and firmware. Never guess.</li>
    </ul>
    <p class="small muted">Use public sources only: the vendor's own security advisory or end-of-life page,
    and the <a href="https://www.cisa.gov/known-exploited-vulnerabilities-catalog" target="_blank" rel="noopener noreferrer">CISA KEV catalog</a>.
    Judge support dates as of __AS_OF__.</p>
  </div>

  <div class="panel">
    <h2>Finish</h2>
    <div class="bar">
      <button class="primary" id="export">Export CSV</button>
      <label class="small"><input type="file" id="import" accept=".csv,text/csv" class="hidden">
        <button type="button" id="importbtn">Resume from an exported CSV</button></label>
    </div>
    <p class="err" id="err" role="alert"></p>
  </div>
</div>
"""

APP = r"""
(function(){
var D = JSON.parse(document.getElementById('data').textContent);
var FIELDS = ['vendor', 'product', 'version', 'lane', 'source_url_used', 'comment'];
var byId = {}; D.rows.forEach(function(r){ byId[r.blind_id] = r; });
var ids = D.rows.map(function(r){ return r.blind_id; });
var S = storageGet(D.key) || {reviewer: '', answers: {}, current: null};
var $ = function(id){ return document.getElementById(id); };
$('reviewer').value = S.reviewer || '';

function ans(id){ return S.answers[id] || (S.answers[id] = {vendor: '', product: '', version: '', lane: '', source_url_used: '', comment: ''}); }
function done(id){ var a = S.answers[id]; return !!(a && a.lane); }
function save(){ var ok = storageSet(D.key, S);
  $('saved').textContent = ok ? 'Progress saved in this browser.' :
    'This browser does not allow saving here. Export regularly and use "Resume from an exported CSV".'; }

function field(id, labelText, value, onInput, type, hint){
  var input = el('input', {type: type || 'text', id: id, autocomplete: 'off'});
  input.value = value || ''; input.addEventListener('input', function(){ onInput(input.value); });
  return el('div', null, el('label', {cls: 'field', 'for': id, text: labelText}), input,
            hint ? el('div', {cls: 'small muted', text: hint}) : null); }

function render(){
  if (ids.indexOf(S.current) < 0) S.current = ids[0];
  var r = byId[S.current], a = ans(S.current), pos = ids.indexOf(S.current);
  var set = function(k){ return function(v){ a[k] = v; save(); updateProgress(); refreshJump(); }; };
  var lane = el('select', {id: 'lane'});
  lane.appendChild(el('option', {value: '', text: '— choose a lane —'}));
  D.lanes.forEach(function(l){ var o = el('option', {value: l, text: l}); if (a.lane === l) o.selected = true; lane.appendChild(o); });
  lane.addEventListener('change', function(){ set('lane')(lane.value); });
  var notes = el('textarea', {id: 'comment', placeholder: 'How you decided, what you were unsure about.'});
  notes.value = a.comment || ''; notes.addEventListener('input', function(){ set('comment')(notes.value); });
  $('card').replaceChildren(
    el('div', {cls: 'panel'},
      el('h1', {text: r.blind_id}), el('div', {cls: 'small muted', text: 'Device ' + (pos + 1) + ' of ' + ids.length}),
      kv([['Device name', el('div', {cls: 'raw', text: r.device_name_raw})],
          ['Firmware', r.firmware_version_raw ? el('span', {cls: 'raw', text: r.firmware_version_raw}) : '']])),
    el('div', {cls: 'panel'}, el('h2', {text: 'Your answer'}),
      el('div', {cls: 'grid2'},
        field('vendor', 'Vendor', a.vendor, set('vendor')),
        field('product', 'Product', a.product, set('product'), 'text', 'As the vendor or the KEV catalog names it.'),
        field('version', 'Version', a.version, set('version'), 'text', 'As the vendor writes it, no "v" prefix. Blank if none given.'),
        el('div', null, el('label', {cls: 'field', 'for': 'lane', text: 'Lane'}), lane)),
      field('source_url_used', 'Source URL you used', a.source_url_used, set('source_url_used'), 'url'),
      el('label', {cls: 'field', 'for': 'comment', text: 'Notes'}), notes));
  $('prev').disabled = pos <= 0; $('next').disabled = pos >= ids.length - 1;
  var jump = $('jump'); jump.replaceChildren();
  ids.forEach(function(i){ var o = el('option', {value: i, text: (done(i) ? '✓ ' : '· ') + i});
    if (i === S.current) o.selected = true; jump.appendChild(o); });
  updateProgress(); }
function refreshJump(){ Array.prototype.forEach.call($('jump').options, function(o){ o.textContent = (done(o.value) ? '✓ ' : '· ') + o.value; }); }
function updateProgress(){ var n = ids.filter(done).length;
  $('bar').style.width = (100 * n / ids.length) + '%';
  $('progress').textContent = n + ' of ' + ids.length + ' devices have a lane'; }
function go(delta){ var i = ids.indexOf(S.current) + delta;
  if (i >= 0 && i < ids.length){ S.current = ids[i]; save(); render(); window.scrollTo(0, 0); } }

$('prev').onclick = function(){ go(-1); };
$('next').onclick = function(){ go(1); };
$('nextopen').onclick = function(){ var i = ids.indexOf(S.current);
  for (var k = 1; k <= ids.length; k++){ var id = ids[(i + k) % ids.length]; if (!done(id)){ S.current = id; save(); render(); return; } }
  $('err').textContent = 'Every device has a lane.'; };
$('jump').onchange = function(){ S.current = this.value; save(); render(); };
$('reviewer').oninput = function(){ S.reviewer = this.value; $('err').textContent = ''; save(); };
document.addEventListener('keydown', function(e){ if (typing(e)) return;
  if (e.key === 'ArrowRight') go(1); if (e.key === 'ArrowLeft') go(-1); });

function exportRows(who){
  return ids.map(function(id){ var r = byId[id], a = S.answers[id] || {}, o = {};
    D.export_header.forEach(function(h){ o[h] = ''; });
    o.blind_id = id; o.device_name_raw = r.device_name_raw; o.firmware_version_raw = r.firmware_version_raw;
    o.labeller = who; FIELDS.forEach(function(k){ o[k] = (a[k] || '').trim(); });
    return o; }); }
$('export').onclick = function(){
  var who = $('reviewer').value.trim();
  if (!validReviewer(who)){ $('err').textContent = 'Enter your initials first (letters, spaces, dots or hyphens; no commas).';
    $('reviewer').focus(); return; }
  var open = ids.filter(function(i){ return !done(i); }).length;
  if (open && !window.confirm(open + ' device(s) have no lane yet. Export anyway?')) return;
  download('deming-blind-' + slug(who) + '-' + fileStamp() + '.csv', toCsv(D.export_header, exportRows(who)));
  $('err').textContent = ''; };
$('importbtn').onclick = function(){ $('import').click(); };
$('import').onchange = function(){
  var f = this.files && this.files[0]; if (!f) return;
  var rd = new FileReader();
  rd.onload = function(){
    var rows = csvObjects(rd.result), n = 0;
    if (!rows.length || !('blind_id' in rows[0]) || !('lane' in rows[0])){ $('err').textContent = 'That file is not a blind-labelling export.'; return; }
    rows.forEach(function(x){ if (!byId[x.blind_id]) return; var a = ans(x.blind_id);
      FIELDS.forEach(function(k){ a[k] = x[k] || ''; }); if (D.lanes.indexOf(a.lane) < 0) a.lane = ''; n++;
      if (!S.reviewer && x.labeller) S.reviewer = x.labeller; });
    $('reviewer').value = S.reviewer || ''; save(); render();
    $('err').textContent = 'Restored ' + n + ' device(s) from ' + f.name + '.'; };
  rd.readAsText(f); this.value = ''; };
save(); render();
})();
"""


def build(out: Path, worksheet: Path = WORKSHEET, as_of: str = AS_OF_DEFAULT) -> Path:
    """`as_of` is the evaluation date shown to labellers (data/ground_truth_meta.json holds the
    same date; it is passed in, not read, so this builder opens nothing but the worksheet)."""
    data = build_data(worksheet)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = BODY.replace("__AS_OF__", html.escape(as_of))
    out.write_text(page("Deming blind labelling", body, data, APP), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "review" / "blind.html")
    ap.add_argument("--worksheet", type=Path, default=WORKSHEET)
    ap.add_argument("--as-of", default=AS_OF_DEFAULT, help="evaluation date shown to labellers")
    a = ap.parse_args(argv)
    p = build(a.out, a.worksheet, a.as_of)
    print(f"Wrote {p} ({p.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
