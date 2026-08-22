# SUPERSEDED (pilot-era). Use ../analyse_d3.py for the D3 study: this file's EXCLUDE set holds PILOT item indices (index 2 collides with the valid D3 item D3-03, making Condition D read 22/22 instead of 24/24), its "all 67 items" text and n=67 caveats do not apply to the 12-item D3 set, and it pools the 8b and 70b models with no split. Its load() remains the canonical six-way label reconstruction and is still imported elsewhere. No logic changed.
"""
analyse_results.py
------------------
Item 5: turns results.csv (the four-condition run) into the dissertation's
results tables and headline metrics.

Reports, for the offshore-wind-farm domain:
  * Per-condition outcome distribution
   (the master table).
  * RQ1 -- retrieval vs parametric memory:
      - A-correct       : parametric-memory baseline (answers with NO documents)
      - B1-correct      : standard RAG
      - B2-correct      : oracle RAG
      - C behaviour     : memorisation under IRRELEVANT context (abstain vs answer)
      - D conflict split: grounded_but_wrong (followed the false doc) vs
                          correct (overrode it from memory) -- the headline.
  * RQ2 -- failure decomposition: retrieval_failure / ungrounded_hallucination /
      grounded_but_wrong, per condition.
  * B1 vs B2 contrast: isolates retrieval quality from grounding behaviour.

Principled exclusions (reported BOTH ways -- full and filtered):
  * EXCLUDE list: items that are non-assertional or provenance-mismatched, so
    their ground truth can't support D / B2 scoring. Edit EXCLUDE below as your
    human-review pass finalises it.
  * no_answer cells (e.g. B2 oracle paper unretrievable) are dropped from rate
    denominators, since the model was never actually asked.

Proportions carry Wilson 95% confidence intervals -- honest for n=67, and they
stop you over-reading a single run. Absolute LEVELS are provisional (pilot
questions embed the claim); the CROSS-CONDITION PATTERN is the real signal.

Usage:
    python analyse_results.py                       # print all tables
    python analyse_results.py --csv results.csv
    python analyse_results.py --export_dir tables/  # also write CSVs per table
"""

import csv
import math
import argparse
import collections
from pathlib import Path

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent

# Items to exclude from D / B2 scoring: non-assertional claims or wrong-DOI
# provenance mismatches found during contradiction construction. Update after
# your annotators finalise the review queue.
EXCLUDE = {2, 34, 45}

CONDITIONS = ["A", "B1", "B2", "C", "D"]
OUTCOMES = ["correct", "abstention", "retrieval_failure",
            "ungrounded_hallucination", "grounded_but_wrong",
            "parametric_error", "no_answer"]


def wilson(k, n, z=1.96):
    """Wilson score 95% CI for a proportion -- well-behaved for small n and
    extreme proportions, unlike the normal approximation."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def fmt_pct(k, n):
    p, lo, hi = wilson(k, n)
    return f"{100*p:5.1f}% [{100*lo:4.1f}, {100*hi:4.1f}]  ({k}/{n})"


def load(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        r["item_idx"] = int(r["item_idx"])
        r["failure_type"] = r["failure_type"] or "correct"
        rows.append(r)
    return rows


def by_condition(rows):
    d = collections.defaultdict(list)
    for r in rows:
        d[r["condition"]].append(r)
    return d


def outcome_counts(cells):
    c = collections.Counter(r["failure_type"] for r in cells)
    return c, len(cells)


def print_master_table(bycond):
    print("\n" + "=" * 78)
    print("TABLE 1 - Outcome distribution by condition (all 67 items, unfiltered)")
    print("=" * 78)
    header = "outcome".ljust(26) + "".join(c.rjust(10) for c in CONDITIONS)
    print(header)
    print("-" * len(header))
    for o in OUTCOMES:
        row = o.ljust(26)
        for cond in CONDITIONS:
            counts, n = outcome_counts(bycond[cond])
            v = counts.get(o, 0)
            row += (f"{v}" if v else "·").rjust(10)
        print(row)
    print("-" * len(header))
    print("n".ljust(26) + "".join(str(len(bycond[c])).rjust(10) for c in CONDITIONS))


def rate(cells, predicate, drop_no_answer=True, exclude_items=None):
    """Proportion of cells satisfying predicate, over a clean denominator."""
    pool = cells
    if exclude_items:
        pool = [r for r in pool if r["item_idx"] not in exclude_items]
    if drop_no_answer:
        pool = [r for r in pool if r["failure_type"] != "no_answer"]
    n = len(pool)
    k = sum(1 for r in pool if predicate(r))
    return k, n


def print_rq1(bycond):
    print("\n" + "=" * 78)
    print("RQ1 - Retrieval vs parametric memory  (offshore wind farm domain)")
    print("=" * 78)

    is_correct = lambda r: r["failure_type"] == "correct"
    is_abstain = lambda r: r["failure_type"] == "abstention"

    k, n = rate(bycond["A"], is_correct)
    print(f"  A  correct (parametric-memory baseline) : {fmt_pct(k, n)}")
    k, n = rate(bycond["B1"], is_correct)
    print(f"  B1 correct (standard RAG)               : {fmt_pct(k, n)}")
    k, n = rate(bycond["B2"], is_correct)
    print(f"  B2 correct (oracle RAG)                 : {fmt_pct(k, n)}")

    print("\n  Condition C - behaviour under IRRELEVANT context:")
    k, n = rate(bycond["C"], is_abstain)
    print(f"     abstained (resisted irrelevant docs) : {fmt_pct(k, n)}")
    k, n = rate(bycond["C"], is_correct)
    print(f"     correct (memorised despite noise)    : {fmt_pct(k, n)}")

    print("\n  Condition D - CONFLICT resolution (filtered; excludes "
          f"{sorted(EXCLUDE)}):  <-- headline")
    k, n = rate(bycond["D"], lambda r: r["failure_type"] == "grounded_but_wrong",
                exclude_items=EXCLUDE)
    print(f"     grounded_but_wrong (followed false doc): {fmt_pct(k, n)}")
    k, n = rate(bycond["D"], is_correct, exclude_items=EXCLUDE)
    print(f"     correct (overrode doc from memory)     : {fmt_pct(k, n)}")
    k, n = rate(bycond["D"], lambda r: r["failure_type"] == "ungrounded_hallucination",
                exclude_items=EXCLUDE)
    print(f"     ungrounded_hallucination               : {fmt_pct(k, n)}")

    # Same D, unfiltered, for honest comparison.
    print("\n  Condition D - same metrics UNFILTERED (all 67), for transparency:")
    k, n = rate(bycond["D"], lambda r: r["failure_type"] == "grounded_but_wrong")
    print(f"     grounded_but_wrong                     : {fmt_pct(k, n)}")
    k, n = rate(bycond["D"], is_correct)
    print(f"     correct                                : {fmt_pct(k, n)}")


def print_b1_b2(bycond, rows):
    print("\n" + "=" * 78)
    print("B1 vs B2 - isolating retrieval quality from grounding behaviour")
    print("=" * 78)
    is_correct = lambda r: r["failure_type"] == "correct"
    k1, n1 = rate(bycond["B1"], is_correct)
    k2, n2 = rate(bycond["B2"], is_correct)
    print(f"  B1 (documents as retrieved) correct : {fmt_pct(k1, n1)}")
    print(f"  B2 (oracle ground-truth)    correct : {fmt_pct(k2, n2)}")
    diff = 100 * (k1 / n1 - k2 / n2)
    print(f"  Difference (B1 - B2)                : {diff:+.1f} pts")
    print("  Interpretation: if B2 <= B1, oracle retrieval is NOT a strict upper")
    print("  bound -- narrow oracle context can under-inform vs free retrieval when")
    print("  the ground-truth chunks lack the specific fact (the Hit@5 confound).")

    # Paired view: per-item B1 vs B2 outcomes (the within-item strength).
    b1 = {r["item_idx"]: r["failure_type"] for r in bycond["B1"]}
    b2 = {r["item_idx"]: r["failure_type"] for r in bycond["B2"]}
    both = set(b1) & set(b2)
    flip_b1only = sum(1 for i in both if b1[i] == "correct" and b2[i] != "correct")
    flip_b2only = sum(1 for i in both if b2[i] == "correct" and b1[i] != "correct")
    print(f"\n  Paired (n={len(both)}): correct in B1 only = {flip_b1only}, "
          f"correct in B2 only = {flip_b2only}")


def print_rq2(bycond):
    print("\n" + "=" * 78)
    print("RQ2 - Failure decomposition (wrong answers only), per condition")
    print("=" * 78)
    fails = ["retrieval_failure", "ungrounded_hallucination", "grounded_but_wrong",
             "parametric_error"]
    header = "condition".ljust(12) + "".join(f.split("_")[0][:8].rjust(11) for f in fails) + "totalwrong".rjust(12)
    print(header)
    print("-" * len(header))
    for cond in CONDITIONS:
        counts, _ = outcome_counts(bycond[cond])
        tw = sum(counts.get(f, 0) for f in fails)
        row = cond.ljust(12) + "".join(str(counts.get(f, 0)).rjust(11) for f in fails) + str(tw).rjust(12)
        print(row)


def maybe_export(bycond, rows, export_dir):
    if not export_dir:
        return
    import os
    os.makedirs(export_dir, exist_ok=True)
    # Master table
    with open(os.path.join(export_dir, "table1_outcomes_by_condition.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["outcome"] + CONDITIONS)
        for o in OUTCOMES:
            w.writerow([o] + [outcome_counts(bycond[c])[0].get(o, 0) for c in CONDITIONS])
    print(f"\nWrote table CSVs to {export_dir}/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "results.csv"))
    ap.add_argument("--export_dir", default=None)
    args = ap.parse_args()

    # Resolve a relative --csv against the repo root (CWD-independent).
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    rows = load(str(csv_path))
    bycond = by_condition(rows)

    print(f"\nLoaded {len(rows)} cells | excluded items for D/B2 scoring: {sorted(EXCLUDE)}")
    print("NOTE: absolute levels are provisional (pilot questions embed the claim);")
    print("read the CROSS-CONDITION PATTERN as the finding, not the raw percentages.")

    print_master_table(bycond)
    print_rq1(bycond)
    print_b1_b2(bycond, rows)
    print_rq2(bycond)
    maybe_export(bycond, rows, args.export_dir)
    print()


if __name__ == "__main__":
    main()
