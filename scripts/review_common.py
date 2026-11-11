"""Shared pieces of the two static review pages (review/review.html, review/blind.html).

Each page is one self-contained HTML file: inline CSS, inline JS, and the data embedded as JSON
in a <script type="application/json"> block. No server, no network, no external scripts.
Progress is saved in localStorage when the browser allows it (behaviour for file:// pages is
not defined by the spec and differs between browsers), and every page can re-import its own
exported CSV to resume, which works everywhere.

This module must never contain label data: the blind page is built from it too.
"""
from __future__ import annotations

import hashlib
import json

CSS = r"""
:root{
  --bg:#f6f7f9; --panel:#ffffff; --ink:#1b1f24; --muted:#5b6470; --line:#d9dde3;
  --accent:#1f5fbf; --accent-ink:#ffffff; --ok:#1d7a46; --ok-bg:#e3f4ea; --warn:#8a5a00;
  --warn-bg:#fff3d6; --bad:#b42318; --bad-bg:#fde8e7; --chip:#eef1f5; --focus:#7aa7ff;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#111418; --panel:#1a1f25; --ink:#e7eaee; --muted:#9aa4b1; --line:#2d343d;
    --accent:#6ea2ff; --accent-ink:#0b1220; --ok:#6fd39b; --ok-bg:#163525; --warn:#f2c46b;
    --warn-bg:#3a2e12; --bad:#ff8a80; --bad-bg:#3d1b1a; --chip:#242b33; --focus:#6ea2ff;
  }
}
:root[data-theme="dark"]{
  --bg:#111418; --panel:#1a1f25; --ink:#e7eaee; --muted:#9aa4b1; --line:#2d343d;
  --accent:#6ea2ff; --accent-ink:#0b1220; --ok:#6fd39b; --ok-bg:#163525; --warn:#f2c46b;
  --warn-bg:#3a2e12; --bad:#ff8a80; --bad-bg:#3d1b1a; --chip:#242b33; --focus:#6ea2ff;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:0 0 8px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.04em}
.sub{color:var(--muted);margin:0 0 12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;margin:0 0 12px}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.bar .grow{flex:1 1 200px}
label.field{display:block;font-weight:600;margin:0 0 4px}
input[type=text],input[type=url],textarea,select{width:100%;padding:8px 10px;border:1px solid var(--line);
  border-radius:8px;background:var(--panel);color:var(--ink);font:inherit}
textarea{min-height:80px;resize:vertical}
input:focus,textarea:focus,select:focus,button:focus{outline:2px solid var(--focus);outline-offset:1px}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);
  background:var(--chip);color:var(--ink);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:600}
button:disabled{opacity:.5;cursor:default}
.progress{height:10px;background:var(--chip);border-radius:6px;overflow:hidden;margin:6px 0 2px}
.progress>div{height:100%;background:var(--accent);width:0}
.muted{color:var(--muted)} .small{font-size:13px}
.err{color:var(--bad);font-weight:600;min-height:1.2em;margin:4px 0 0}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;background:var(--chip);font-size:13px;margin:0 4px 4px 0}
.chip.ok{background:var(--ok-bg);color:var(--ok)} .chip.warn{background:var(--warn-bg);color:var(--warn)}
.chip.bad{background:var(--bad-bg);color:var(--bad)}
.lane{display:inline-block;font-weight:700;padding:2px 12px;border-radius:999px;background:var(--chip)}
dl.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0}
dl.kv dt{color:var(--muted)} dl.kv dd{margin:0;overflow-wrap:anywhere}
.raw{font-family:ui-monospace,Consolas,monospace;background:var(--chip);padding:6px 8px;border-radius:6px;
  overflow-wrap:anywhere;white-space:pre-wrap}
ul.plain{margin:0;padding-left:18px} ul.plain li{margin:0 0 6px;overflow-wrap:anywhere}
a{color:var(--accent)}
.choices{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.choices label{display:flex;align-items:center;gap:6px;padding:8px 12px;border:1px solid var(--line);
  border-radius:8px;cursor:pointer;background:var(--panel)}
.choices input{margin:0}
.choices label.on{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.nav{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.nav select{width:auto;flex:1 1 220px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media (max-width:640px){.grid2{grid-template-columns:1fr} dl.kv{grid-template-columns:1fr} dl.kv dt{margin-top:6px}}
.hidden{display:none}
"""

# Pure helpers, kept in their own <script id="core"> block so tests can run them under Node.
JS_CORE = r"""
function csvCell(v){ v = (v === null || v === undefined) ? '' : String(v);
  return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
function toCsv(header, rows){
  var lines = [header.map(csvCell).join(',')];
  rows.forEach(function(r){ lines.push(header.map(function(h){ return csvCell(r[h]); }).join(',')); });
  return lines.join('\r\n') + '\r\n'; }
function parseCsv(text){
  var rows = [], row = [], cell = '', q = false, i = 0, c;
  text = String(text).replace(/^\uFEFF/, '');
  for (; i < text.length; i++){
    c = text[i];
    if (q){ if (c === '"'){ if (text[i+1] === '"'){ cell += '"'; i++; } else q = false; } else cell += c; }
    else if (c === '"') q = true;
    else if (c === ','){ row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r'){ if (c === '\r' && text[i+1] === '\n') i++;
      row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += c; }
  if (cell !== '' || row.length){ row.push(cell); rows.push(row); }
  return rows; }
function csvObjects(text){
  var rows = parseCsv(text); if (!rows.length) return [];
  var h = rows[0];
  return rows.slice(1).filter(function(r){ return r.length > 1 || r[0] !== ''; }).map(function(r){
    var o = {}; h.forEach(function(k, i){ o[k] = r[i] === undefined ? '' : r[i]; }); return o; }); }
function validReviewer(s){ return /^[A-Za-z][A-Za-z .'\-]{0,39}$/.test(String(s || '').trim()); }
function safeUrl(u){ try { var x = new URL(u); return x.protocol === 'https:' ? x.href : null; } catch(e){ return null; } }
function fileStamp(){ var d = new Date(); function p(n){ return (n < 10 ? '0' : '') + n; }
  return d.getFullYear() + p(d.getMonth()+1) + p(d.getDate()) + '-' + p(d.getHours()) + p(d.getMinutes()); }
function slug(s){ return String(s || '').trim().replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'reviewer'; }
if (typeof module !== 'undefined') module.exports = {csvCell:csvCell, toCsv:toCsv, parseCsv:parseCsv,
  csvObjects:csvObjects, validReviewer:validReviewer, safeUrl:safeUrl, slug:slug};
"""

# DOM helpers (browser only).
JS_DOM = r"""
function storageGet(key){ try { return JSON.parse(window.localStorage.getItem(key) || 'null'); } catch(e){ return null; } }
function storageSet(key, val){ try { window.localStorage.setItem(key, JSON.stringify(val)); return true; } catch(e){ return false; } }
function download(name, text){
  var blob = new Blob([text], {type: 'text/csv;charset=utf-8'});
  var url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(function(){ URL.revokeObjectURL(url); }, 2000); }
function el(tag, attrs){
  var n = document.createElement(tag), k;
  for (k in (attrs || {})){
    if (k === 'text') n.textContent = attrs[k];
    else if (k === 'cls') n.className = attrs[k];
    else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), attrs[k]);
    else n.setAttribute(k, attrs[k]); }
  for (var i = 2; i < arguments.length; i++){
    var c = arguments[i]; if (c === null || c === undefined || c === false) continue;
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); }
  return n; }
function link(url, text){
  var u = safeUrl(url);
  return u ? el('a', {href: u, target: '_blank', rel: 'noopener noreferrer', text: text || url})
           : el('span', {text: (text || url) + ' (not an https link)'}); }
function kv(pairs){
  var dl = el('dl', {cls: 'kv'});
  pairs.forEach(function(p){ if (p) { dl.appendChild(el('dt', {text: p[0]}));
    var v = p[1]; dl.appendChild(el('dd', null, (v === '' || v === null || v === undefined) ? el('span', {cls: 'muted', text: '(blank)'}) : v)); } });
  return dl; }
function typing(e){ var t = e.target && e.target.tagName; return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT'; }
"""


def embed_json(data) -> str:
    """JSON safe to place inside <script type="application/json">: no '<', '>', '&' or
    U+2028/2029 survive, so data text can never close the script block."""
    s = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return (s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def data_hash(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def page(title: str, body: str, data, app_js: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style>
</head>
<body>
{body}
<script type="application/json" id="data">{embed_json(data)}</script>
<script id="core">{JS_CORE}</script>
<script>{JS_DOM}</script>
<script>{app_js}</script>
</body>
</html>
"""
