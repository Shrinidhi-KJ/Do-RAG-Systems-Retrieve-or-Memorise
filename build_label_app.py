
"""
build_label_app.py
------------------
Generate a self-contained, offline, single-file HTML labelling app from the BLIND
human_label_sheet_d3.csv and taxonomy_rubric.md, for independent raters.

Blindness: this script reads ONLY the blind sheet and the rubric. It never reads
human_label_key_d3.json or any judge field. The emitted HTML embeds only the seven
display columns per row (row_uid, item_id, condition, question, gold, context_shown,
model_answer); the three human columns are filled by the rater in-app. A build-time
self-check parses the generated HTML back and aborts if any per-row judge decision
(field or value) is present.

The app:
  * opens by double-click over file:// and runs fully offline (no CDN, no network),
  * shows the rubric in-app; the label dropdown for each row is derived FROM the
    rubric's applicable-conditions (no separate hardcoded mapping),
  * autosaves to localStorage keyed by rater_id + build title,
  * exports a CSV that is a drop-in for score_judge_validation.py (joins on row_uid),
  * imports a previously exported CSV to resume.

Usage:
    python build_label_app.py                                  # full 120-row app (title "full")
    python build_label_app.py --subset uids.txt --title bioagora   # subset app
    python build_label_app.py --title full --out label_app_d3_full.html
"""

import re
import csv
import sys
import json
import argparse
import datetime
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHEET = ROOT / "human_label_sheet_d3.csv"
RUBRIC = ROOT / "taxonomy_rubric.md"

DISPLAY_COLUMNS = ["row_uid", "item_id", "condition", "question", "gold",
                   "context_shown", "model_answer"]
SHEET_COLUMNS = DISPLAY_COLUMNS + ["human_label", "human_grounded", "notes"]
ALL_CONDITIONS = ["A", "B1", "B2", "C", "D"]

# Fields that must NEVER appear as embedded per-row data (judge decisions). The words
# themselves legitimately appear in the rubric/UI as label options; the check below is
# specifically that no per-row judge value is embedded in the row data.
BANNED_ROW_FIELDS = {"correct", "abstained", "grounded", "failure_type",
                     "judge_label", "model_tag", "model_name"}
# Hard tokens that should not appear ANYWHERE in the output (never legitimate UI text).
BANNED_TOKENS = ["failure_type", "judge_label", "model_tag", "model_name"]

KEY_FILE = ROOT / "human_label_key_d3.json"   # named ONLY to assert we never open it


def parse_rubric(text):
    """Parse the six labels: definition + applicable conditions, straight from the
    rubric. Returns (labels_ordered, cond_labels) with NO separate hardcoded mapping."""
    # isolate the labels section
    seg = text
    if "The six labels:" in seg:
        seg = seg.split("The six labels:", 1)[1]
    if "Decision order" in seg:
        seg = seg.split("Decision order", 1)[0]

    # split into bullet blocks that each start with "- **"
    blocks = re.split(r"\n(?=- \*\*)", seg)
    labels = OrderedDict()
    for blk in blocks:
        blk = " ".join(blk.split())  # collapse wrapped lines / whitespace
        m = re.match(r"-\s*\*\*(.+?)\*\*\s*-\s*(.*)", blk)
        if not m:
            continue
        name = m.group(1).strip()
        rest = m.group(2).strip()
        low = rest.lower()
        aidx = low.find("applies")
        definition = (rest[:aidx] if aidx >= 0 else rest).strip().rstrip(".").strip()
        applies = rest[aidx:] if aidx >= 0 else ""
        if "all condition" in applies.lower():
            conds = list(ALL_CONDITIONS)
        else:
            found = re.findall(r"\b(B1|B2|A|C|D)\b", applies)
            conds = [c for c in ALL_CONDITIONS if c in set(found)]
        labels[name] = {"definition": definition, "conditions": conds}

    if len(labels) != 6:
        raise SystemExit(f"STOP: expected 6 rubric labels, parsed {len(labels)}: {list(labels)}")

    # invert to condition -> allowed labels (rubric order preserved)
    cond_labels = OrderedDict()
    for cond in ALL_CONDITIONS:
        cond_labels[cond] = [name for name, v in labels.items() if cond in v["conditions"]]
    return labels, cond_labels


def read_sheet():
    with open(SHEET, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("STOP: sheet is empty.")
    header = list(rows[0].keys())
    if header != SHEET_COLUMNS:
        raise SystemExit(f"STOP: unexpected sheet columns {header}")
    # keep only the display columns for embedding (blind: drop the human columns)
    return [{c: r[c] for c in DISPLAY_COLUMNS} for r in rows]


def read_subset(path):
    uids = []
    for line in open(path, encoding="utf-8"):
        u = line.strip()
        if u and not u.startswith("#"):
            uids.append(u)
    return uids


def build_html(rows, labels, cond_labels, title):
    data = {
        "title": title,
        "sheetColumns": SHEET_COLUMNS,
        "conditions": ALL_CONDITIONS,
        "labels": labels,            # name -> {definition, conditions}
        "labelOrder": list(labels.keys()),
        "condLabels": cond_labels,   # condition -> [allowed label names]
        "rows": rows,                # only the 7 display columns
    }
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__APP_DATA_JSON__", data_json)


def self_check(html):
    """Parse the embedded row data back out of the generated HTML and abort if any
    per-row judge field/value is present. Also reject hard-banned tokens anywhere."""
    m = re.search(r'<script id="appdata" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise SystemExit("STOP self-check: embedded data block not found.")
    data = json.loads(m.group(1))
    allowed = set(DISPLAY_COLUMNS)
    for row in data["rows"]:
        extra = set(row.keys()) - allowed
        if extra:
            raise SystemExit(f"STOP self-check: row has non-display keys {extra}; aborting without writing.")
        for bad in BANNED_ROW_FIELDS:
            if bad in row:
                raise SystemExit(f"STOP self-check: banned judge field '{bad}' in row data; aborting.")
    for tok in BANNED_TOKENS:
        if tok in html:
            raise SystemExit(f"STOP self-check: banned token '{tok}' present in output; aborting.")
    return len(data["rows"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", default=None, help="File of row_uids (one per line) to include.")
    ap.add_argument("--title", default="full", help="Build tag, e.g. full or bioagora.")
    ap.add_argument("--out", default=None, help="Output HTML path (default label_app_d3_<title>.html).")
    args = ap.parse_args()

    # Blindness guard: we must never open the key file.
    assert KEY_FILE.name == "human_label_key_d3.json"  # referenced by name only, never read

    labels, cond_labels = parse_rubric(RUBRIC.read_text(encoding="utf-8"))
    rows = read_sheet()

    if args.subset:
        want = read_subset(args.subset)
        by_uid = {r["row_uid"]: r for r in rows}
        missing = [u for u in want if u not in by_uid]
        if missing:
            raise SystemExit(f"STOP: {len(missing)} subset row_uids not found in the sheet: {missing[:5]}")
        # preserve sheet order for stability
        wantset = set(want)
        rows = [r for r in rows if r["row_uid"] in wantset]

    html = build_html(rows, labels, cond_labels, args.title)
    n = self_check(html)   # aborts before writing if any judge field leaks

    out = Path(args.out) if args.out else ROOT / f"label_app_d3_{args.title}.html"
    if not out.is_absolute():
        out = ROOT / out
    out.write_text(html, encoding="utf-8")

    print(f"Built {out}  ({n} rows, title='{args.title}')")
    print("  condition -> allowed labels (from rubric):")
    for cond in ALL_CONDITIONS:
        print(f"    {cond:3s}: {cond_labels[cond]}")
    print("  self-check: no per-row judge field embedded; key file never opened.")


# ============================ HTML TEMPLATE ============================
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>D3 labelling</title>
<style>
  :root{
    --bg:#f4f5f7; --panel:#ffffff; --ink:#1b1f24; --muted:#5b6472; --line:#d7dbe2;
    --accent:#2f6f4f; --accent2:#28527a; --warn:#a23; --done:#2f6f4f; --todo:#c9ccd3;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%}
  body{font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
  button{font:inherit;cursor:pointer;border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 12px}
  button:hover{border-color:var(--accent2)}
  .hidden{display:none !important}
  h1,h2,h3{margin:0 0 .4em}
  .pill{display:inline-block;padding:2px 8px;border-radius:999px;background:#eef1f5;color:var(--muted);font-size:12px;margin-right:6px}

  /* Landing */
  #landing{position:fixed;inset:0;background:var(--bg);overflow:auto;padding:32px;z-index:20}
  .card{max-width:820px;margin:0 auto;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:24px}
  .rubric li{margin:.35em 0}
  .rubric code{background:#eef1f5;padding:1px 5px;border-radius:5px}
  .start-row{display:flex;gap:10px;align-items:center;margin-top:16px;flex-wrap:wrap}
  input[type=text]{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;min-width:220px}

  /* App layout */
  #app{display:flex;flex-direction:column;height:100%}
  .topbar{display:flex;align-items:center;gap:12px;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line);flex-wrap:wrap}
  .topbar .grow{flex:1}
  .progress{font-variant-numeric:tabular-nums;color:var(--muted)}
  .cols{flex:1;display:grid;grid-template-columns:minmax(300px,1fr) minmax(340px,1.3fr) minmax(240px,.8fr);gap:12px;padding:12px;overflow:hidden}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;overflow:auto}
  .colwrap{display:flex;flex-direction:column;gap:12px;min-height:0;overflow:auto}
  .label-sm{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}
  .ctx{white-space:pre-wrap;font-size:14px}
  .ctx-panel{display:flex;flex-direction:column;min-height:0}
  .ctx-body{overflow:auto;flex:1;border-top:1px solid var(--line);padding-top:10px;margin-top:8px}
  .gold,.qtext,.mans{white-space:pre-wrap}
  select,textarea{font:inherit;width:100%;padding:8px;border:1px solid var(--line);border-radius:8px;background:#fff}
  textarea{min-height:160px;resize:vertical}
  .seg{display:flex;gap:6px;flex-wrap:wrap}
  .seg button{flex:1;min-width:92px}
  .seg button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
  .defbox{margin-top:8px;font-size:13px;color:var(--muted);min-height:2.4em}
  .bottombar{display:flex;align-items:center;justify-content:center;gap:18px;padding:10px;background:var(--panel);border-top:1px solid var(--line)}
  .bottombar .nav{font-size:20px;padding:6px 16px}
  .qno{font-weight:600;cursor:pointer;text-decoration:underline dotted}

  /* Index grid overlay */
  #grid{position:fixed;inset:0;background:rgba(20,24,30,.5);z-index:30;display:flex;align-items:center;justify-content:center;padding:20px}
  .gridcard{background:var(--panel);border-radius:14px;padding:18px;max-width:900px;width:100%;max-height:86vh;overflow:auto}
  .cells{display:grid;grid-template-columns:repeat(auto-fill,minmax(52px,1fr));gap:8px;margin-top:12px}
  .cell{border:1px solid var(--line);border-radius:8px;padding:8px 4px;text-align:center;font-size:12px;background:#fff}
  .cell .n{font-weight:700}
  .cell.done{background:#e7f2ec;border-color:var(--done)}
  .cell.todo{background:#fff}
  .cell.cur{outline:2px solid var(--accent2)}
  .legend{display:flex;gap:14px;color:var(--muted);font-size:13px;margin-top:8px}
  .swatch{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:5px;border:1px solid var(--line)}
</style>
</head>
<body>
<script id="appdata" type="application/json">__APP_DATA_JSON__</script>

<!-- Landing -->
<div id="landing">
  <div class="card">
    <h1>D3 answer labelling</h1>
    <p>Please enter your name or initials, read the rubric, then start. Your progress is
       saved in this browser and tied to the name you enter. You can export your labels
       to a CSV at any time, and import a CSV to resume on another machine.</p>
    <div class="start-row">
      <label for="rater">Rater name / initials:</label>
      <input type="text" id="rater" placeholder="e.g. AB" autocomplete="off">
      <button id="startBtn">Start labelling &rarr;</button>
    </div>
    <p id="resumeNote" class="progress" style="margin-top:8px"></p>
    <h2 style="margin-top:22px">Rubric: the six labels</h2>
    <p>Assign exactly one label per item. The dropdown only offers the labels valid for
       that item's condition. Also mark <em>grounded</em> (is the answer supported by the
       documents shown?) for conditions B1, B2, C, D.</p>
    <ul id="rubricList" class="rubric"></ul>
  </div>
</div>

<!-- App -->
<div id="app" class="hidden">
  <div class="topbar">
    <strong>D3 labelling</strong>
    <span class="pill" id="titlePill"></span>
    <span class="pill" id="raterPill"></span>
    <span class="grow"></span>
    <span class="progress" id="progress"></span>
    <button id="rubricBtn">Rubric</button>
    <button id="importBtn">Import CSV</button>
    <input type="file" id="importFile" accept=".csv" class="hidden">
    <button id="exportBtn">Export CSV</button>
  </div>

  <div class="cols">
    <!-- LEFT -->
    <div class="colwrap">
      <div class="panel">
        <div id="hdr" class="label-sm"></div>
        <div class="label-sm" style="margin-top:10px">Question</div>
        <div id="q" class="qtext"></div>
        <div class="label-sm" style="margin-top:10px">Claim &amp; gold answer</div>
        <div id="gold" class="gold"></div>
        <div class="label-sm" style="margin-top:10px">Model answer</div>
        <div id="mans" class="mans"></div>
      </div>
      <div class="panel">
        <div class="label-sm">Human label</div>
        <select id="labelSel"><option value="">-- choose a label --</option></select>
        <div id="defbox" class="defbox"></div>
      </div>
    </div>

    <!-- CENTRE -->
    <div class="panel ctx-panel">
      <div class="label-sm">Context shown</div>
      <div id="ctx" class="ctx ctx-body"></div>
    </div>

    <!-- RIGHT -->
    <div class="colwrap">
      <div class="panel" style="flex:1;display:flex;flex-direction:column">
        <div class="label-sm">Notes</div>
        <textarea id="notes" placeholder="Optional notes about this item..."></textarea>
      </div>
      <div class="panel" id="groundedPanel">
        <div class="label-sm">Human grounded (is the answer supported by the documents shown?)</div>
        <div class="seg" id="groundedSeg">
          <button data-g="grounded">Grounded</button>
          <button data-g="not_grounded">Not grounded</button>
          <button data-g="na">N/A</button>
        </div>
      </div>
    </div>
  </div>

  <div class="bottombar">
    <button class="nav" id="prevBtn" title="Previous (left arrow)">&larr;</button>
    <span class="qno" id="qno" title="Open index grid"></span>
    <button class="nav" id="nextBtn" title="Next (right arrow)">&rarr;</button>
  </div>
</div>

<!-- Index grid overlay -->
<div id="grid" class="hidden">
  <div class="gridcard">
    <div style="display:flex;align-items:center">
      <h2 style="flex:1">Jump to item</h2>
      <button id="gridClose">Close</button>
    </div>
    <div class="legend">
      <span><span class="swatch" style="background:#e7f2ec;border-color:#2f6f4f"></span>labelled</span>
      <span><span class="swatch" style="background:#fff"></span>unlabelled</span>
    </div>
    <div class="cells" id="gridCells"></div>
  </div>
</div>

<script>
"use strict";
const DATA = JSON.parse(document.getElementById("appdata").textContent);
const ROWS = DATA.rows;
const TOTAL = ROWS.length;
document.title = "D3 labelling (" + DATA.title + ")";

// ---------- state ----------
let rater = null;
let idx = 0;
let ann = {};   // row_uid -> {human_label, human_grounded, notes}

function storeKey(){ return "labelapp::" + DATA.title + "::" + rater; }
function load(){
  try { ann = JSON.parse(localStorage.getItem(storeKey())) || {}; }
  catch(e){ ann = {}; }
}
function save(){
  try { localStorage.setItem(storeKey(), JSON.stringify(ann)); } catch(e){}
}
function entry(uid){
  if(!ann[uid]) ann[uid] = {human_label:"", human_grounded:"", notes:""};
  return ann[uid];
}
function labelledCount(){
  return ROWS.filter(r => (ann[r.row_uid] && ann[r.row_uid].human_label)).length;
}

// ---------- rubric rendering (landing + button) ----------
function renderRubric(el){
  el.innerHTML = "";
  DATA.labelOrder.forEach(name => {
    const v = DATA.labels[name];
    const li = document.createElement("li");
    li.innerHTML = "<code>" + name + "</code> &mdash; " + escapeHtml(v.definition) +
                   " <span class='pill'>" + v.conditions.join(", ") + "</span>";
    el.appendChild(li);
  });
}
function escapeHtml(s){
  return String(s==null?"":s).replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

// ---------- render one row ----------
function render(){
  const r = ROWS[idx];
  const e = entry(r.row_uid);
  document.getElementById("hdr").textContent =
    "row " + r.row_uid + "   |   item " + r.item_id + "   |   condition " + r.condition;
  document.getElementById("q").textContent = r.question;
  document.getElementById("gold").textContent = r.gold;
  document.getElementById("mans").textContent = r.model_answer;
  document.getElementById("ctx").textContent = r.context_shown;

  // label dropdown from rubric-derived allowed labels
  const sel = document.getElementById("labelSel");
  const allowed = DATA.condLabels[r.condition] || [];
  sel.innerHTML = "<option value=''>-- choose a label --</option>";
  allowed.forEach(name => {
    const o = document.createElement("option");
    o.value = name;
    o.textContent = name + " — " + DATA.labels[name].definition;
    sel.appendChild(o);
  });
  sel.value = e.human_label || "";
  updateDef();

  // grounded control: only B1/B2/C/D
  const showG = r.condition !== "A";
  document.getElementById("groundedPanel").classList.toggle("hidden", !showG);
  document.querySelectorAll("#groundedSeg button").forEach(b =>
    b.classList.toggle("active", showG && e.human_grounded === b.dataset.g));

  document.getElementById("notes").value = e.notes || "";

  document.getElementById("qno").textContent = "Question No " + (idx+1) + " of " + TOTAL;
  document.getElementById("prevBtn").disabled = (idx === 0);
  document.getElementById("nextBtn").disabled = (idx === TOTAL-1);
  updateProgress();
}
function updateDef(){
  const sel = document.getElementById("labelSel");
  const box = document.getElementById("defbox");
  const name = sel.value;
  box.textContent = name ? (name + ": " + DATA.labels[name].definition) : "";
}
function updateProgress(){
  const c = labelledCount();
  document.getElementById("progress").textContent = c + "/" + TOTAL + " labelled";
}

// ---------- navigation ----------
function go(i){ idx = Math.max(0, Math.min(TOTAL-1, i)); render(); }

// ---------- index grid ----------
function openGrid(){
  const wrap = document.getElementById("gridCells");
  wrap.innerHTML = "";
  ROWS.forEach((r,i) => {
    const done = ann[r.row_uid] && ann[r.row_uid].human_label;
    const d = document.createElement("div");
    d.className = "cell " + (done ? "done" : "todo") + (i===idx ? " cur" : "");
    d.title = r.item_id + " / " + r.condition + " / " + r.row_uid + (done ? " ("+ann[r.row_uid].human_label+")" : "");
    d.innerHTML = "<div class='n'>"+(i+1)+"</div><div>"+r.condition+"</div>";
    d.onclick = () => { closeGrid(); go(i); };
    wrap.appendChild(d);
  });
  document.getElementById("grid").classList.remove("hidden");
}
function closeGrid(){ document.getElementById("grid").classList.add("hidden"); }

// ---------- CSV ----------
function csvCell(s){ return '"' + String(s==null?"":s).replace(/"/g,'""') + '"'; }
function groundedExport(g){ return g==="grounded" ? "TRUE" : (g==="not_grounded" ? "FALSE" : ""); }

function exportCSV(){
  const cols = DATA.sheetColumns;
  const lines = [cols.map(csvCell).join(",")];
  ROWS.forEach(r => {
    const e = ann[r.row_uid] || {};
    const rec = Object.assign({}, r, {
      human_label: e.human_label || "",
      human_grounded: groundedExport(e.human_grounded || ""),
      notes: e.notes || ""
    });
    lines.push(cols.map(c => csvCell(rec[c])).join(","));
  });
  const blob = new Blob([lines.join("\r\n")], {type:"text/csv;charset=utf-8"});
  const d = new Date();
  const date = d.getFullYear() + String(d.getMonth()+1).padStart(2,"0") + String(d.getDate()).padStart(2,"0");
  const safe = (rater||"rater").replace(/[^A-Za-z0-9_-]/g,"");
  const name = safe + "_" + DATA.title + "_labels_d3_" + date + ".csv";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
}

function parseCSV(text){
  const rows = []; let row = []; let cur = ""; let q = false;
  for(let i=0;i<text.length;i++){
    const c = text[i];
    if(q){
      if(c === '"'){ if(text[i+1] === '"'){ cur += '"'; i++; } else { q = false; } }
      else cur += c;
    } else {
      if(c === '"') q = true;
      else if(c === ",") { row.push(cur); cur = ""; }
      else if(c === "\n"){ row.push(cur); rows.push(row); row = []; cur = ""; }
      else if(c === "\r"){ /* skip */ }
      else cur += c;
    }
  }
  if(cur.length || row.length){ row.push(cur); rows.push(row); }
  return rows;
}
function groundedImport(v){
  const s = String(v==null?"":v).trim().toLowerCase();
  if(["true","t","yes","y","1","grounded"].includes(s)) return "grounded";
  if(["false","f","no","n","0","ungrounded"].includes(s)) return "not_grounded";
  return "";  // blank or N/A
}
function importCSV(text){
  const cells = parseCSV(text).filter(r => r.length && r.some(x => x!==""));
  if(!cells.length) return;
  const head = cells[0];
  const ix = {};
  head.forEach((h,i)=> ix[h.trim()] = i);
  if(!("row_uid" in ix)){ alert("CSV has no row_uid column."); return; }
  const known = new Set(ROWS.map(r=>r.row_uid));
  let n = 0;
  for(let i=1;i<cells.length;i++){
    const c = cells[i];
    const uid = (c[ix["row_uid"]]||"").trim();
    if(!known.has(uid)) continue;
    const e = entry(uid);
    if("human_label" in ix) e.human_label = (c[ix["human_label"]]||"").trim();
    if("human_grounded" in ix) e.human_grounded = groundedImport(c[ix["human_grounded"]]);
    if("notes" in ix) e.notes = c[ix["notes"]]||"";
    n++;
  }
  save(); render();
  alert("Imported labels for " + n + " rows.");
}

// ---------- wire up ----------
function startApp(){
  document.getElementById("landing").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  document.getElementById("titlePill").textContent = "build: " + DATA.title;
  document.getElementById("raterPill").textContent = "rater: " + rater;
  render();
}

window.addEventListener("DOMContentLoaded", () => {
  renderRubric(document.getElementById("rubricList"));

  const raterInput = document.getElementById("rater");
  raterInput.addEventListener("input", () => {
    const v = raterInput.value.trim();
    if(v){
      // peek resume progress for this name
      try {
        const saved = JSON.parse(localStorage.getItem("labelapp::"+DATA.title+"::"+v) || "{}");
        const c = Object.values(saved).filter(x=>x&&x.human_label).length;
        document.getElementById("resumeNote").textContent = c ? ("Found saved progress for '"+v+"': "+c+"/"+TOTAL+" labelled. Starting will resume it.") : "";
      } catch(e){}
    } else document.getElementById("resumeNote").textContent = "";
  });

  document.getElementById("startBtn").onclick = () => {
    const v = raterInput.value.trim();
    if(!v){ raterInput.focus(); return; }
    rater = v; load(); startApp();
  };

  document.getElementById("labelSel").addEventListener("change", (ev) => {
    entry(ROWS[idx].row_uid).human_label = ev.target.value;
    updateDef(); save(); updateProgress();
  });
  document.querySelectorAll("#groundedSeg button").forEach(b => {
    b.onclick = () => {
      const e = entry(ROWS[idx].row_uid);
      e.human_grounded = (e.human_grounded === b.dataset.g) ? "" : b.dataset.g;
      document.querySelectorAll("#groundedSeg button").forEach(x =>
        x.classList.toggle("active", e.human_grounded === x.dataset.g));
      save();
    };
  });
  document.getElementById("notes").addEventListener("input", (ev) => {
    entry(ROWS[idx].row_uid).notes = ev.target.value; save();
  });

  document.getElementById("prevBtn").onclick = () => go(idx-1);
  document.getElementById("nextBtn").onclick = () => go(idx+1);
  document.getElementById("qno").onclick = openGrid;
  document.getElementById("gridClose").onclick = closeGrid;
  document.getElementById("grid").onclick = (ev) => { if(ev.target.id==="grid") closeGrid(); };
  document.getElementById("rubricBtn").onclick = () => {
    // reuse the grid overlay area is overkill; simple alert-free: toggle landing rubric card
    document.getElementById("landing").classList.remove("hidden");
    document.getElementById("app").classList.add("hidden");
  };
  document.getElementById("exportBtn").onclick = exportCSV;
  document.getElementById("importBtn").onclick = () => document.getElementById("importFile").click();
  document.getElementById("importFile").addEventListener("change", (ev) => {
    const f = ev.target.files[0]; if(!f) return;
    const rd = new FileReader();
    rd.onload = () => importCSV(rd.result);
    rd.readAsText(f); ev.target.value = "";
  });

  // If returning from the rubric view, allow Start to just resume without re-entering.
  document.getElementById("startBtn").addEventListener("click", () => {}, {once:false});

  document.addEventListener("keydown", (ev) => {
    if(!document.getElementById("app").classList.contains("hidden")){
      const t = ev.target.tagName;
      if(t === "TEXTAREA" || t === "SELECT" || t === "INPUT") return;
      if(document.getElementById("grid").classList.contains("hidden")===false) return;
      if(ev.key === "ArrowLeft") go(idx-1);
      else if(ev.key === "ArrowRight") go(idx+1);
    }
  });
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
