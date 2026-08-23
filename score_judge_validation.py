"""
score_judge_validation.py
-------------------------
Score the completed human-labelling sheet against the 8b judge (H2a). Joins the
sheet and the answer key on row_uid and writes judge_validation_d3.md and .json.

Metrics:
  * Overall six-way Cohen's kappa (human_label vs judge_label), with observed
    agreement and PABAK reported alongside.
  * Full human-vs-judge confusion matrix (rows = human, cols = judge).
  * Binary correct-vs-not kappa, observed agreement, PABAK.
  * Grounding-decision kappa, observed agreement, PABAK, over ONLY the cells whose
    judge_grounded is not null (conditions with documents).
  * Per-condition observed agreement (six-way). Condition is parsed from cell_key.

Why all three of kappa, observed agreement, and PABAK: the label marginals here are
heavily skewed (mostly correct and grounded_but_wrong). Skewed marginals can depress
Cohen's kappa even when raw agreement is high (the kappa paradox), so observed
agreement and PABAK are reported together with kappa, never kappa alone.

Read-only over the sheet and key; writes only the two output files.

Usage:
    python score_judge_validation.py
    python score_judge_validation.py --sheet human_label_sheet_d3.csv --key human_label_key_d3.json
"""

import csv
import json
import argparse
from collections import Counter, defaultdict, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SIX_LABELS = ["correct", "abstention", "retrieval_failure",
              "ungrounded_hallucination", "grounded_but_wrong", "parametric_error"]

MD = ROOT / "judge_validation_d3.md"
JS = ROOT / "judge_validation_d3.json"


def norm_label(s):
    if s is None:
        return None
    s = s.strip().lower().replace(" ", "_").replace("-", "_")
    return s or None


def parse_bool(s):
    if s is None:
        return None
    s = s.strip().lower()
    if s in ("true", "t", "yes", "y", "1", "grounded"):
        return True
    if s in ("false", "f", "no", "n", "0", "ungrounded"):
        return False
    return None


def condition_from_cell_key(cell_key):
    # cell_key format: "{item_idx}|{condition}|{model_tag}|{hash8}"
    parts = cell_key.split("|")
    return parts[1] if len(parts) >= 2 else "?"


def observed_agreement(pairs):
    if not pairs:
        return None
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def cohen_kappa(pairs):
    """Cohen's kappa for categorical pairs. Returns (po, pe, kappa, n, k_categories)."""
    n = len(pairs)
    if n == 0:
        return (None, None, None, 0, 0)
    cats = sorted(set(a for a, _ in pairs) | set(b for _, b in pairs))
    k = len(cats)
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 1e-12 else None
    return (po, pe, kappa, n, k)


def pabak(po, k):
    """Prevalence-adjusted bias-adjusted kappa. Multi-category generalisation:
    (k*po - 1) / (k - 1); reduces to 2*po - 1 for k = 2."""
    if po is None or k < 2:
        return None
    return (k * po - 1) / (k - 1)


def rnd(x, p=4):
    return None if x is None else round(x, p)


def load_joined(sheet_path, key_path):
    key = json.load(open(key_path, encoding="utf-8"))
    joined = []
    unlabelled = 0
    for r in csv.DictReader(open(sheet_path, encoding="utf-8")):
        uid = r["row_uid"]
        if uid not in key:
            raise SystemExit(f"STOP: sheet row_uid {uid} not in key; aborting.")
        hlab = norm_label(r.get("human_label"))
        if hlab is None:
            unlabelled += 1
            continue
        k = key[uid]
        joined.append({
            "row_uid": uid,
            "condition": condition_from_cell_key(k["cell_key"]),
            "human_label": hlab,
            "judge_label": k["judge_label"],
            "human_grounded": parse_bool(r.get("human_grounded")),
            "judge_grounded": k["judge_grounded"],
        })
    return joined, unlabelled, len(key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=str(ROOT / "human_label_sheet_d3.csv"))
    ap.add_argument("--key", default=str(ROOT / "human_label_key_d3.json"))
    args = ap.parse_args()

    joined, unlabelled, n_key = load_joined(args.sheet, args.key)
    n = len(joined)
    if n == 0:
        raise SystemExit("STOP: no rows have a human_label filled in; nothing to score.")

    out = OrderedDict()
    out["n_key_rows"] = n_key
    out["n_scored"] = n
    out["n_unlabelled_skipped"] = unlabelled

    # ---- six-way ----
    six_pairs = [(r["human_label"], r["judge_label"]) for r in joined]
    po6, pe6, k6, _, kc6 = cohen_kappa(six_pairs)
    out["sixway"] = {"n": n, "observed_agreement": rnd(po6), "cohen_kappa": rnd(k6),
                     "expected_agreement_pe": rnd(pe6), "pabak": rnd(pabak(po6, kc6)),
                     "n_categories_for_pabak": kc6}

    # confusion matrix (rows human, cols judge)
    labels_seen = [L for L in SIX_LABELS if any(L in (r["human_label"], r["judge_label"]) for r in joined)]
    extras = sorted({r["human_label"] for r in joined} | {r["judge_label"] for r in joined})
    for e in extras:
        if e not in labels_seen:
            labels_seen.append(e)
    cm = {h: {j: 0 for j in labels_seen} for h in labels_seen}
    for r in joined:
        cm[r["human_label"]][r["judge_label"]] += 1
    out["confusion_matrix"] = {"labels": labels_seen, "rows_human_cols_judge": cm}

    # ---- binary correct vs not ----
    def cvn(lbl):
        return "correct" if lbl == "correct" else "not_correct"
    bin_pairs = [(cvn(r["human_label"]), cvn(r["judge_label"])) for r in joined]
    pob, peb, kb, _, kcb = cohen_kappa(bin_pairs)
    out["binary_correct_vs_not"] = {"n": n, "observed_agreement": rnd(pob), "cohen_kappa": rnd(kb),
                                    "pabak": rnd(pabak(pob, 2))}

    # ---- grounding decision (only where judge_grounded is not None) ----
    g_all = [r for r in joined if r["judge_grounded"] is not None]
    g_pairs = [(r["human_grounded"], r["judge_grounded"]) for r in g_all if r["human_grounded"] is not None]
    g_missing_human = sum(1 for r in g_all if r["human_grounded"] is None)
    pog, peg, kg, _, kcg = cohen_kappa(g_pairs)
    out["grounding_decision"] = {
        "n_judge_grounded_present": len(g_all),
        "n_scored": len(g_pairs),
        "n_missing_human_grounded": g_missing_human,
        "observed_agreement": rnd(pog), "cohen_kappa": rnd(kg), "pabak": rnd(pabak(pog, 2)),
    }

    # ---- per-condition observed agreement (six-way) ----
    per_cond = OrderedDict()
    bycond = defaultdict(list)
    for r in joined:
        bycond[r["condition"]].append((r["human_label"], r["judge_label"]))
    for cond in ["A", "B1", "B2", "C", "D"]:
        pairs = bycond.get(cond, [])
        per_cond[cond] = {"n": len(pairs), "observed_agreement": rnd(observed_agreement(pairs))}
    out["per_condition_observed_agreement"] = per_cond

    out["note_on_kappa"] = ("Label marginals are heavily skewed (mostly correct and "
                            "grounded_but_wrong); skewed marginals can depress Cohen's kappa "
                            "despite high observed agreement, so observed agreement and PABAK "
                            "are reported alongside kappa, never kappa alone.")

    JS.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- markdown ----
    md = []
    md.append("# Judge validation (H2a): human vs 8b judge\n")
    md.append(f"Scored {n} of {n_key} sheet rows ({unlabelled} rows had no human_label and were skipped). "
              "Read-only join on row_uid.\n")
    md.append(f"> {out['note_on_kappa']}\n")

    md.append("## Headline agreement\n")
    md.append("| metric | n | observed agreement | Cohen's kappa | PABAK |")
    md.append("|---|---|---|---|---|")
    s6 = out["sixway"]; b = out["binary_correct_vs_not"]; g = out["grounding_decision"]
    md.append(f"| six-way label | {s6['n']} | {s6['observed_agreement']} | {s6['cohen_kappa']} | {s6['pabak']} |")
    md.append(f"| correct vs not (binary) | {b['n']} | {b['observed_agreement']} | {b['cohen_kappa']} | {b['pabak']} |")
    md.append(f"| grounding decision | {g['n_scored']} | {g['observed_agreement']} | {g['cohen_kappa']} | {g['pabak']} |")
    md.append(f"\nPABAK for the six-way row uses the multi-category form (k*po - 1)/(k - 1) with "
              f"k = {s6['n_categories_for_pabak']} categories observed; the two binary rows use 2*po - 1. "
              f"Grounding is scored only over cells whose judge_grounded is not null "
              f"({g['n_judge_grounded_present']} present; {g['n_missing_human_grounded']} lacked a human_grounded value).\n")

    md.append("## Six-way confusion matrix (rows = human, cols = judge)\n")
    labs = out["confusion_matrix"]["labels"]
    md.append("| human \\\\ judge | " + " | ".join(labs) + " |")
    md.append("|" + "---|" * (len(labs) + 1))
    for h in labs:
        md.append(f"| {h} | " + " | ".join(str(cm[h][j]) for j in labs) + " |")
    md.append("")

    md.append("## Per-condition observed agreement (six-way)\n")
    md.append("| condition | n | observed agreement |")
    md.append("|---|---|---|")
    for cond, v in per_cond.items():
        md.append(f"| {cond} | {v['n']} | {v['observed_agreement']} |")
    md.append("")

    MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {MD.name} and {JS.name} | scored {n}/{n_key} rows ({unlabelled} skipped)")


if __name__ == "__main__":
    main()
