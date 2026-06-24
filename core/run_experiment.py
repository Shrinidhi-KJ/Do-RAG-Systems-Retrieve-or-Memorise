"""
run_experiment.py
-----------------
The experiment runner. Loops over questions x conditions x models, runs each
through the conditions and the diagnostic classifier, and writes every result
to disk AS IT COMPLETES.

Built for free-tier, multi-day execution:
  * IDEMPOTENT. Each (item, condition, model) cell is cached by a unique key in
    results_cache.jsonl. Re-running skips completed cells, so you just run the
    same command each day until it's done.
  * INTERRUPTIBLE. When the daily token cap is hit, the generation layer raises
    after its retries; the runner catches it, reports progress, and exits cleanly
    so nothing is half-written. Tomorrow, resume with the same command.
  * APPEND-ONLY LOG. results_cache.jsonl is one JSON object per line. Crash-safe:
    a killed process can lose at most the current line, not the whole file.

Usage:
    python run_experiment.py                       # run/resume everything
    python run_experiment.py --models 8b           # only the 8B subject model
    python run_experiment.py --conditions A B1 C    # subset of conditions
    python run_experiment.py --limit 5             # first 5 questions (smoke test)
    python run_experiment.py --status              # show progress, run nothing
    python run_experiment.py --export results.csv  # flatten cache to CSV
"""

import os
import sys
import json
import argparse
from pathlib import Path

from conditions import condition_A, condition_B1, condition_B2, condition_C, condition_D
from classifier import classify

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent
EVAL_SET = ROOT / "pilot_eval_set.json"
CONTRADICTIONS = ROOT / "contradictions_cache.json"
CACHE = ROOT / "results_cache.jsonl"

# Subject models under test (this is the experiment variable -- model SIZE).
# Both on the 8B-family free tier for now; swap the frontier slot when you move
# to a paid tier for the model-size comparison.
MODELS = {
    "8b": "llama-3.1-8b-instant",
    # "frontier": "llama-3.3-70b-versatile",   # enable on paid tier
}

ALL_CONDITIONS = ["A", "B1", "B2", "C", "D"]


def cell_key(item_idx, condition, model_tag):
    return f"{item_idx}|{condition}|{model_tag}"


def load_done_keys():
    """Set of cell keys already in the cache, so we never recompute them."""
    done = set()
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    done.add(rec["cell_key"])
                except (json.JSONDecodeError, KeyError):
                    continue  # tolerate a torn final line from a hard kill
    return done


def append_result(rec):
    with open(CACHE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_one_cell(item, item_idx, condition, model_tag, model_name, contradictions):
    """Run a single condition for one question under one model, then classify."""
    question = item["question"]
    claim_text = item["claim_text"]
    gt_dois = item.get("matched_dois", [])

    if condition == "A":
        result = condition_A(question)
    elif condition == "B1":
        result = condition_B1(question)
    elif condition == "B2":
        result = condition_B2(question, gt_dois)
    elif condition == "C":
        # Seed by item index so the "irrelevant" pick is reproducible per question.
        result = condition_C(question, gt_doi=(gt_dois[0] if gt_dois else None), seed=item_idx)
    elif condition == "D":
        entry = contradictions.get(str(item_idx))
        if not entry:
            result = {"condition": "D", "question": question,
                      "context_docs": [], "retrieved_meta": [], "answer": None}
        else:
            result = condition_D(question, entry["contradiction"])
    else:
        raise ValueError(f"Unknown condition {condition}")

    labelled = classify(result, claim_text)
    labelled["cell_key"] = cell_key(item_idx, condition, model_tag)
    labelled["item_idx"] = item_idx
    labelled["model_tag"] = model_tag
    return labelled


def cmd_status(eval_set, conditions, model_tags):
    done = load_done_keys()
    total = len(eval_set) * len(conditions) * len(model_tags)
    print(f"Progress: {len(done)} / {total} cells complete ({100 * len(done) // max(total,1)}%)")
    for mt in model_tags:
        for cond in conditions:
            n = sum(1 for i in range(len(eval_set)) if cell_key(i, cond, mt) in done)
            print(f"  {mt:8s} {cond:3s}: {n}/{len(eval_set)}")


def cmd_export(path):
    import csv
    # Resolve a relative export path against the repo root so results.csv lands
    # in the same place regardless of the current working directory.
    p = Path(path)
    path = str(p if p.is_absolute() else ROOT / p)
    if not os.path.exists(CACHE):
        print("No cache yet."); return
    rows = []
    with open(CACHE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    fields = ["item_idx", "model_tag", "condition", "abstained", "correct",
              "grounded", "retrieval_hit", "failure_type", "question", "answer"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote {len(rows)} rows to {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
    ap.add_argument("--conditions", nargs="+", choices=ALL_CONDITIONS, default=ALL_CONDITIONS)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--export", type=str, default=None)
    args = ap.parse_args()

    if args.export:
        cmd_export(args.export); return

    with open(EVAL_SET, encoding="utf-8") as f:
        eval_set = json.load(f)
    if args.limit:
        eval_set = eval_set[: args.limit]

    if args.status:
        cmd_status(eval_set, args.conditions, args.models); return

    contradictions = {}
    if os.path.exists(CONTRADICTIONS):
        with open(CONTRADICTIONS, encoding="utf-8") as f:
            contradictions = json.load(f)
    elif "D" in args.conditions:
        print("WARNING: no contradictions_cache.json found; Condition D will be skipped.")

    done = load_done_keys()
    todo = [
        (i, cond, mt)
        for mt in args.models
        for i in range(len(eval_set))
        for cond in args.conditions
        if cell_key(i, cond, mt) not in done
    ]
    print(f"{len(done)} cells already done. {len(todo)} to run this session.\n")

    completed = 0
    for item_idx, cond, mt in todo:
        try:
            rec = run_one_cell(eval_set[item_idx], item_idx, cond, mt, MODELS[mt], contradictions)
            append_result(rec)
            completed += 1
            ft = rec.get("failure_type") or "correct"
            print(f"[{completed}/{len(todo)}] item {item_idx:>2} {cond:3s} {mt:8s} -> {ft}")
        except RuntimeError as e:
            # Almost certainly the daily token cap. Stop cleanly; resume tomorrow.
            print(f"\nStopped on item {item_idx} {cond} {mt}: {e}")
            print(f"Completed {completed} new cells this session. "
                  f"Re-run the same command tomorrow to resume.")
            sys.exit(0)

    print(f"\nDone. {completed} new cells this session.")
    print(f"Run  python run_experiment.py --status   to see totals, or "
          f"--export results.csv  to flatten for analysis.")


if __name__ == "__main__":
    main()
