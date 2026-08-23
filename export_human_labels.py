"""
export_human_labels.py
----------------------
Build a BLIND human-labelling workbook for judge validation (H2a), plus its
answer key, from results_d3.jsonl. Read-only over the results; writes only the
three new output files.

Outputs (repo root):
  human_label_sheet_d3.csv   -- one row per cell, shuffled fixed-seed order, NO
                                judge-derived fields. Columns the annotator fills:
                                human_label, human_grounded, notes.
  human_label_key_d3.json    -- row_uid -> {cell_key, model_tag, judge_label,
                                judge_grounded}. The answer key; never opened while
                                labelling.
  taxonomy_rubric.md         -- the six labels, one-line definitions, applicable
                                conditions, so the annotator labels under the judge's
                                rules.

The judge's six-way label is NOT stored directly; it is the `failure_type` field
mapped so an empty/None value becomes "correct". That mapping is reused VERBATIM
from core/analyse_results.py load():  r["failure_type"] = r["failure_type"] or "correct"
(imported here as `load`), so the reconstructed label matches analysis_d3.md with
zero drift (verified: load() on results_d3.csv == this rule on results_d3.jsonl ==
analysis_d3.json condition x label table).

Usage:
    python export_human_labels.py                 # all 120 cells
    python export_human_labels.py --n 30          # stratified subset (see below)
    python export_human_labels.py --seed 20260711 # override the fixed seed
"""

import os
import csv
import json
import random
import hashlib
import argparse
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT / "core"))
from analyse_results import load  # noqa: E402  (verbatim six-way label reconstruction)

RESULTS_JSONL = ROOT / "results_d3.jsonl"
RESULTS_CSV = ROOT / "results_d3.csv"
EVAL_SET = ROOT / "d3_eval_set.json"

SHEET = ROOT / "human_label_sheet_d3.csv"
KEY = ROOT / "human_label_key_d3.json"
RUBRIC = ROOT / "taxonomy_rubric.md"

DEFAULT_SEED = 20260711

# The two singleton cells that MUST be force-included in any --n subset.
SINGLETONS = [
    {"condition": "A", "model_tag": "8b", "item_id": "D3-02", "judge_label": "parametric_error"},
    {"condition": "B1", "model_tag": "8b", "item_id": "D3-12", "judge_label": "retrieval_failure"},
]

SIX_LABELS = ["correct", "abstention", "retrieval_failure",
              "ungrounded_hallucination", "grounded_but_wrong", "parametric_error"]


def row_uid(cell_key):
    """Short opaque, stable hash of the cell_key (not reversible to condition/model)."""
    return hashlib.sha1(cell_key.encode("utf-8")).hexdigest()[:10]


def judge_label_of(rec):
    """Reconstruct the judge's six-way label, verbatim rule from analyse_results.load()."""
    return rec.get("failure_type") or "correct"


def context_shown(rec):
    """Readable rendering of the documents the model actually saw for this cell."""
    cond = rec["condition"]
    docs = rec.get("context_docs") or []
    if cond == "A":
        return "no documents"
    if cond == "D":
        # The single pre-generated counterfactual passage that was actually shown.
        return docs[0] if docs else ""
    if not docs:
        return ""
    return "\n\n".join(f"[{i + 1}] {d}" for i, d in enumerate(docs))


def build_rows(recs, eval_by_id, key_label):
    rows = []
    for rec in recs:
        iid = rec["item_id"]
        ev = eval_by_id[iid]
        gold = f"CLAIM: {ev['claim_text']}\n\nGOLD ANSWER: {ev.get('gold_answer', '')}"
        uid = row_uid(rec["cell_key"])
        rows.append({
            # sheet-visible fields (blind: no judge-derived columns)
            "row_uid": uid,
            "item_id": iid,
            "condition": rec["condition"],
            "question": rec["question"],
            "gold": gold,
            "context_shown": context_shown(rec),
            "model_answer": rec.get("answer") if rec.get("answer") is not None else "",
            "human_label": "",
            "human_grounded": "",
            "notes": "",
            # internal-only (used for key + stratification; NOT written to the sheet)
            "_cell_key": rec["cell_key"],
            "_model_tag": rec["model_tag"],
            "_judge_label": key_label[(rec["item_idx"], rec["model_tag"], rec["condition"])],
            "_judge_grounded": rec.get("grounded"),
        })
    return rows


def stratified_subset(rows_shuffled, n):
    """Floor of one per populated (condition x judge_label) stratum, force-include the
    two singleton cells, then fill to n in the fixed shuffled order. Returns rows in
    shuffled order. If n is below the floor count, the floor wins (n is raised)."""
    order = {r["row_uid"]: i for i, r in enumerate(rows_shuffled)}
    strata = OrderedDict()
    for r in rows_shuffled:
        strata.setdefault((r["condition"], r["_judge_label"]), []).append(r)

    singleton_uids = set()
    for s in SINGLETONS:
        for r in rows_shuffled:
            if (r["condition"] == s["condition"] and r["_model_tag"] == s["model_tag"]
                    and r["item_id"] == s["item_id"] and r["_judge_label"] == s["judge_label"]):
                singleton_uids.add(r["row_uid"])
    if len(singleton_uids) != len(SINGLETONS):
        raise SystemExit("STOP: could not locate both singleton cells; aborting rather than guessing.")

    selected = OrderedDict()  # uid -> row, insertion tracked; order fixed at the end

    def add(r):
        selected.setdefault(r["row_uid"], r)

    # 1. force-include the singletons
    for r in rows_shuffled:
        if r["row_uid"] in singleton_uids:
            add(r)
    # 2. floor: one per populated stratum (first in shuffled order)
    for _, lst in strata.items():
        if not any(x["row_uid"] in selected for x in lst):
            add(lst[0])
    floor_count = len(selected)
    # 3. fill to n in shuffled order
    for r in rows_shuffled:
        if len(selected) >= n:
            break
        add(r)

    out = sorted(selected.values(), key=lambda r: order[r["row_uid"]])
    return out, floor_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None,
                    help="Stratified subset size (condition x judge-label, floor 1/stratum, "
                         "singletons forced). Default: all 120.")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Fixed shuffle seed.")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(RESULTS_JSONL, encoding="utf-8") if l.strip()]
    recs = [r for r in recs if r.get("record_type") != "run_config"]
    eval_set = json.load(open(EVAL_SET, encoding="utf-8"))
    eval_by_id = {it["id"]: it for it in eval_set}

    # Authoritative six-way labels via the imported analyse_results.load() code path.
    csv_rows = load(str(RESULTS_CSV))
    key_label = {(r["item_idx"], r["model_tag"], r["condition"]): r["failure_type"] for r in csv_rows}
    # Zero-drift guard: the imported rule must agree with the jsonl field on every cell.
    for rec in recs:
        if judge_label_of(rec) != key_label[(rec["item_idx"], rec["model_tag"], rec["condition"])]:
            raise SystemExit("STOP: reconstructed label disagrees with analyse_results.load(); aborting.")

    rows = build_rows(recs, eval_by_id, key_label)

    rng = random.Random(args.seed)
    rng.shuffle(rows)

    note = ""
    if args.n is not None:
        rows, floor_count = stratified_subset(rows, args.n)
        if args.n < floor_count:
            note = f" (requested n={args.n} raised to {floor_count} to keep one per populated stratum)"

    # ---- write the blind sheet (visible columns only) ----
    sheet_cols = ["row_uid", "item_id", "condition", "question", "gold",
                  "context_shown", "model_answer", "human_label", "human_grounded", "notes"]
    with open(SHEET, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sheet_cols, extrasaction="ignore", quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # ---- write the answer key ----
    key = OrderedDict()
    for r in rows:
        key[r["row_uid"]] = {
            "cell_key": r["_cell_key"],
            "model_tag": r["_model_tag"],
            "judge_label": r["_judge_label"],
            "judge_grounded": r["_judge_grounded"],
        }
    with open(KEY, "w", encoding="utf-8") as f:
        json.dump(key, f, indent=2, ensure_ascii=False)

    # ---- write the rubric ----
    RUBRIC.write_text(RUBRIC_TEXT, encoding="utf-8")

    print(f"Wrote {SHEET.name}: {len(rows)} rows{note}")
    print(f"Wrote {KEY.name}: {len(key)} entries")
    print(f"Wrote {RUBRIC.name}")
    # quick label spread for sanity (from the key, not the sheet)
    from collections import Counter
    spread = Counter(v["judge_label"] for v in key.values())
    print("judge-label spread in sheet:", dict(spread))


RUBRIC_TEXT = """# Judge taxonomy rubric (H2a human labelling)

Label each cell under the SAME rules the 8b judge used, so human and judge labels
are comparable. Assign exactly one `human_label` from the six below. Also record
`human_grounded` (TRUE or FALSE: is the model answer supported by the documents
shown?) for every cell that HAS documents (conditions B1, B2, C, D); leave it blank
for Condition A (no documents).

The six labels:

- **correct** - the answer matches the gold claim on its key fact (direction,
  magnitude, or conclusion). Applies to ALL conditions (A, B1, B2, C, D).
- **abstention** - the answer declines to give a substantive answer (says it cannot
  tell, does not know, or the information is not in the documents). Applies to ALL
  conditions.
- **retrieval_failure** - wrong (not correct, not abstained) because the documents
  shown did NOT contain the information needed to answer. Applies ONLY to the helpful
  retrieval conditions B1 and B2.
- **ungrounded_hallucination** - wrong, and the answer asserts things NOT supported by
  the documents shown (had context, ignored it, fabricated). Applies to the context
  conditions B1, B2, C, D.
- **grounded_but_wrong** - wrong, but the answer FAITHFULLY follows the documents shown
  (e.g. it followed a counterfactual in D, or followed irrelevant docs in C). Applies to
  the context conditions B1, B2, C, D.
- **parametric_error** - wrong, with NO documents given: a pure parametric-memory miss.
  Applies ONLY to Condition A.

Decision order (mirrors the judge): abstention first, then correctness; if wrong and
Condition A -> parametric_error; if wrong with context in B1/B2 and the documents lack
the answer -> retrieval_failure; otherwise grounded_but_wrong if the answer follows the
documents, else ungrounded_hallucination.
"""


if __name__ == "__main__":
    main()
