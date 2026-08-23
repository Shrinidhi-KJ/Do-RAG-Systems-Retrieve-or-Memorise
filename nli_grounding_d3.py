"""
nli_grounding_d3.py
-------------------
H2b: independent-family grounding cross-check.

Every "grounded" label in results_d3.jsonl came from the 8b Llama judge, which
shares a family with the 8b subject. This script re-checks the grounding decision
with a natural-language-inference model from a DIFFERENT family (DeBERTa-v3), so the
grounding signal does not rest on one model family.

Read-only over the results. The authoritative cells and judge labels are taken via
core/analyse_results.py load() (verbatim six-way reconstruction), and the same
zero-drift agreement is re-asserted at runtime (abort if it disagrees). NLI is run on
CPU in eval mode with no sampling, so it is deterministic. Writes only
nli_grounding_d3.md and nli_grounding_d3.json.

Evidence per cell:
  premise    = the context ACTUALLY shown (context_docs), not re-retrieved
  hypothesis = the model's answer (full), plus its main claim sentence if multi-sentence
  aggregate  = max entailment across the shown chunks (and across full/main-sentence);
               max contradiction recorded too
Condition A has no shown context -> grounding-not-applicable -> excluded.

NLI entailment and the judge's "grounded" are RELATED BUT NOT IDENTICAL definitions;
this is convergent evidence that answers are context-driven, not a strict equivalence
test.
"""

import os
import re
import csv
import sys
import json
from collections import Counter, defaultdict, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))
from analyse_results import load  # noqa: E402  (verbatim six-way label reconstruction)

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from huggingface_hub import HfApi

RESULTS_JSONL = ROOT / "results_d3.jsonl"
RESULTS_CSV = ROOT / "results_d3.csv"
EVAL_SET = ROOT / "d3_eval_set.json"
SHEET = ROOT / "human_label_sheet_d3.csv"
KEY_JSON = ROOT / "human_label_key_d3.json"

OUT_MD = ROOT / "nli_grounding_d3.md"
OUT_JS = ROOT / "nli_grounding_d3.json"
# Per-cell NLI cache (append-only) so a slow CPU run resumes after an interruption
# without recomputing. A new file only; never a results/frozen file. Configurable so it
# can live in a scratch dir. Deleted automatically once the outputs are written.
CACHE = Path(os.environ.get("NLI_CACHE", str(ROOT / "nli_cell_cache_d3.jsonl")))

MODEL_ID = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
FALLBACK_ID = "roberta-large-mnli"
GROUND_THRESHOLD = 0.5           # primary entailment cut for nli_grounded
THRESHOLDS = [0.5, 0.7, 0.9]     # sensitivity sweep

torch.manual_seed(0)


# ----------------------------- NLI model -----------------------------
def load_nli():
    for mid in (MODEL_ID, FALLBACK_ID):
        try:
            rev = HfApi().model_info(mid).sha
        except Exception:
            rev = None
        try:
            tok = AutoTokenizer.from_pretrained(mid, revision=rev)
            model = AutoModelForSequenceClassification.from_pretrained(mid, revision=rev)
            model.eval()
            id2label = {int(k): v for k, v in model.config.id2label.items()}
            # map by NAME so it works across model families (deberta vs roberta ordering differ)
            idx = {"entail": None, "contra": None, "neutral": None}
            for i, name in id2label.items():
                n = name.lower()
                if "entail" in n:
                    idx["entail"] = i
                elif "contradic" in n:
                    idx["contra"] = i
                elif "neutral" in n:
                    idx["neutral"] = i
            if idx["entail"] is None or idx["contra"] is None:
                raise RuntimeError(f"could not map NLI labels from {id2label}")
            return mid, rev, tok, model, id2label, idx
        except Exception as e:
            print(f"[nli] {mid} failed to load ({type(e).__name__}: {str(e)[:120]}); trying fallback")
    raise SystemExit("STOP: no NLI model could be loaded.")


MID, REV, TOK, MODEL, ID2LABEL, IDX = load_nli()


@torch.no_grad()
def nli_batch(premises, hypotheses):
    """Return entail/contra prob arrays for parallel premise/hypothesis lists."""
    enc = TOK(premises, hypotheses, truncation=True, max_length=512,
              padding=True, return_tensors="pt")
    logits = MODEL(**enc).logits
    probs = torch.softmax(logits, dim=-1)
    return probs[:, IDX["entail"]].tolist(), probs[:, IDX["contra"]].tolist()


def over(premise_list, hypothesis):
    """Max entailment and max contradiction of one hypothesis over a list of premises."""
    if not premise_list or not hypothesis:
        return None, None
    e, c = nli_batch(premise_list, [hypothesis] * len(premise_list))
    return max(e), max(c)


# ----------------------------- text helpers -----------------------------
def split_sentences(t):
    t = (t or "").strip()
    parts = re.split(r"(?<=[.!?])\s+", t)
    return [p.strip() for p in parts if len(p.strip()) > 0]


def main_claim_sentence(answer):
    """Deterministic 'main claim sentence' = the longest sentence (proxy for the
    substantive claim). Returns (sentence, is_multi)."""
    s = split_sentences(answer)
    if len(s) <= 1:
        return (answer or "").strip(), False
    return max(s, key=len), True


# ----------------------------- stats helpers -----------------------------
def observed_agreement(pairs):
    return None if not pairs else sum(1 for a, b in pairs if a == b) / len(pairs)


def cohen_kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None, None
    cats = sorted(set(a for a, _ in pairs) | set(b for _, b in pairs))
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 1e-12 else None
    return po, kappa


def pabak_binary(po):
    return None if po is None else 2 * po - 1


def rnd(x, p=4):
    return None if x is None else round(x, p)


# ----------------------------- main -----------------------------
def main():
    recs = [json.loads(l) for l in open(RESULTS_JSONL, encoding="utf-8") if l.strip()]
    recs = [r for r in recs if r.get("record_type") != "run_config"]
    eval_by_id = {it["id"]: it for it in json.load(open(EVAL_SET, encoding="utf-8"))}

    # authoritative labels via imported load(); re-assert zero drift with the jsonl field
    csv_rows = load(str(RESULTS_CSV))
    csv_label = {(r["item_idx"], r["model_tag"], r["condition"]): r["failure_type"] for r in csv_rows}
    for r in recs:
        if (r.get("failure_type") or "correct") != csv_label[(r["item_idx"], r["model_tag"], r["condition"])]:
            raise SystemExit("STOP: reconstructed label disagrees with analyse_results.load(); aborting.")

    # resume cache: cell_key -> computed cell record
    cache = {}
    if CACHE.exists():
        for line in open(CACHE, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    cache[rec["cell_key"]] = rec
                except json.JSONDecodeError:
                    pass  # tolerate a torn final line from a kill

    cells = []
    context_recs = [r for r in recs if r["condition"] != "A"]  # A excluded (no context)
    print(f"Running NLI on {len(context_recs)} context cells (A excluded); "
          f"{len(cache)} already cached...")
    for n, r in enumerate(context_recs, 1):
        if r["cell_key"] in cache:
            cells.append(cache[r["cell_key"]])
            if n % 24 == 0:
                print(f"  ...{n}/{len(context_recs)} (cached)")
            continue
        ctx = r.get("context_docs") or []
        ans = r.get("answer") or ""
        ms, is_multi = main_claim_sentence(ans)

        # context entailment/contradiction: best of full answer and main sentence
        e_full, c_full = over(ctx, ans)
        e_ms, c_ms = (over(ctx, ms) if is_multi else (e_full, c_full))
        entail_ctx = max(x for x in (e_full, e_ms) if x is not None) if (e_full is not None) else None
        contra_ctx = max(x for x in (c_full, c_ms) if x is not None) if (c_full is not None) else None

        # gold entailment/contradiction (premise = gold claim_text)
        claim = eval_by_id.get(r["item_id"], {}).get("claim_text")
        if claim:
            ge_full, gc_full = over([claim], ans)
            ge_ms, gc_ms = (over([claim], ms) if is_multi else (ge_full, gc_full))
            entail_gold = max(ge_full, ge_ms)
            contra_gold = max(gc_full, gc_ms)
        else:
            entail_gold = contra_gold = None

        judge_label = csv_label[(r["item_idx"], r["model_tag"], r["condition"])]
        cell = {
            "cell_key": r["cell_key"],
            "item_id": r["item_id"],
            "condition": r["condition"],
            "model_tag": r["model_tag"],
            "judge_label": judge_label,
            "judge_grounded": r.get("grounded"),
            "abstained": r.get("abstained"),
            "n_context_chunks": len(ctx),
            "answer_is_multisentence": is_multi,
            "nli_entail_context": rnd(entail_ctx),
            "nli_contra_context": rnd(contra_ctx),
            "nli_entail_context_full": rnd(e_full),
            "nli_entail_context_mainsent": rnd(e_ms) if is_multi else None,
            "nli_grounded": (entail_ctx is not None and entail_ctx >= GROUND_THRESHOLD),
            "nli_entail_gold": rnd(entail_gold),
            "nli_contra_gold": rnd(contra_gold),
        }
        cells.append(cell)
        with open(CACHE, "a", encoding="utf-8") as cf:   # incremental: survives a kill
            cf.write(json.dumps(cell, ensure_ascii=False) + "\n")
        if n % 24 == 0:
            print(f"  ...{n}/{len(context_recs)}")

    by_key = {c["cell_key"]: c for c in cells}

    out = OrderedDict()
    out["meta"] = {
        "nli_model_id": MID,
        "nli_revision": REV,
        "nli_id2label": ID2LABEL,
        "device": "cpu",
        "torch_version": torch.__version__,
        "deterministic": "eval mode, softmax over logits, no sampling",
        "ground_threshold": GROUND_THRESHOLD,
        "premise": "context_docs actually shown (not re-retrieved); Condition A excluded",
        "hypothesis": "model answer (full) plus main claim sentence (longest) if multi-sentence",
        "aggregation": "max entailment across shown chunks and across full/main-sentence; max contradiction recorded",
        "n_context_cells": len(cells),
        "definitions_note": ("NLI entailment and the judge's 'grounded' are related but NOT "
                             "identical definitions. This is convergent evidence that answers "
                             "are context-driven, not a strict equivalence test."),
    }

    # ---- (1) NLI vs judge over the cells where the judge recorded a grounding decision ----
    jg = [c for c in cells if c["judge_grounded"] is not None]
    pairs = [(c["nli_grounded"], bool(c["judge_grounded"])) for c in jg]
    po, kappa = cohen_kappa(pairs)
    jg_marg = Counter(bool(c["judge_grounded"]) for c in jg)
    out["nli_vs_judge_grounding"] = {
        "n": len(jg),
        "observed_agreement": rnd(po),
        "cohen_kappa": rnd(kappa),
        "pabak": rnd(pabak_binary(po)),
        "judge_grounded_marginal": {str(k): v for k, v in jg_marg.items()},
        "nli_grounded_marginal": {str(k): v for k, v in Counter(c["nli_grounded"] for c in jg).items()},
        "note": ("Marginals are near-degenerate ({} of {} cells share one judge class), so kappa is "
                 "expected to be uninformative; the convergent signal is the OBSERVED AGREEMENT rate, "
                 "not kappa.".format(max(jg_marg.values()), len(jg))),
    }

    # ---- (2) Condition D double-check ----
    d_cells = [c for c in cells if c["condition"] == "D"]
    d_rows = []
    for c in sorted(d_cells, key=lambda x: (x["item_id"], x["model_tag"])):
        d_rows.append({
            "item_id": c["item_id"], "model_tag": c["model_tag"],
            "entail_by_counterfactual": c["nli_entail_context"],
            "entailed_by_false_doc": c["nli_entail_context"] is not None and c["nli_entail_context"] >= GROUND_THRESHOLD,
            "contra_gold": c["nli_contra_gold"],
            "contradicts_gold": c["nli_contra_gold"] is not None and c["nli_contra_gold"] >= GROUND_THRESHOLD,
        })
    n_d = len(d_rows)
    out["condition_D_double_check"] = {
        "n": n_d,
        "rate_entailed_by_false_doc": rnd(sum(x["entailed_by_false_doc"] for x in d_rows) / n_d) if n_d else None,
        "rate_contradicts_gold": rnd(sum(x["contradicts_gold"] for x in d_rows) / n_d) if n_d else None,
        "rows": d_rows,
    }

    # ---- (3) broader non-abstained per-condition grounding rate ----
    def subset_for(cond):
        if cond == "C":
            return [c for c in cells if c["condition"] == "C" and c["judge_label"] == "correct"]
        return [c for c in cells if c["condition"] == cond and c["judge_label"] != "abstention"]
    per_cond = OrderedDict()
    for cond in ["B1", "B2", "C", "D"]:
        sub = subset_for(cond)
        rate = (sum(c["nli_grounded"] for c in sub) / len(sub)) if sub else None
        label = "C-correct" if cond == "C" else f"{cond} (non-abstained)"
        per_cond[cond] = {"subset": label, "n": len(sub), "nli_grounded_rate": rnd(rate)}
    out["per_condition_grounding_rate"] = per_cond

    # ---- (4) threshold sensitivity over the broader non-abstained set ----
    broad = []
    for cond in ["B1", "B2", "C", "D"]:
        broad += subset_for(cond)
    sweep = OrderedDict()
    for t in THRESHOLDS:
        overall = sum((c["nli_entail_context"] or 0) >= t for c in broad) / len(broad) if broad else None
        percond = {}
        for cond in ["B1", "B2", "C", "D"]:
            sub = subset_for(cond)
            percond[cond] = rnd(sum((c["nli_entail_context"] or 0) >= t for c in sub) / len(sub)) if sub else None
        sweep[str(t)] = {"overall": rnd(overall), "per_condition": percond}
    out["threshold_sensitivity"] = {"n_broad": len(broad), "rates": sweep}

    # ---- (5) optional three-way NLI vs judge vs human ----
    threeway = None
    if SHEET.exists() and KEY_JSON.exists():
        key = json.load(open(KEY_JSON, encoding="utf-8"))
        sheet = list(csv.DictReader(open(SHEET, encoding="utf-8")))
        filled = [r for r in sheet if (r.get("human_grounded") or "").strip() != ""]
        if filled:
            def pb(s):
                s = s.strip().lower()
                return True if s in ("true", "t", "yes", "y", "1", "grounded") else (
                    False if s in ("false", "f", "no", "n", "0", "ungrounded") else None)
            tri = []
            for r in filled:
                k = key.get(r["row_uid"])
                if not k:
                    continue
                c = by_key.get(k["cell_key"])
                hg = pb(r.get("human_grounded", ""))
                if c is None or k["judge_grounded"] is None or hg is None:
                    continue
                tri.append((c["nli_grounded"], bool(k["judge_grounded"]), hg))
            if tri:
                nj = observed_agreement([(a, b) for a, b, _ in tri])
                nh = observed_agreement([(a, c) for a, _, c in tri])
                jh = observed_agreement([(b, c) for _, b, c in tri])
                all3 = sum(1 for a, b, c in tri if a == b == c) / len(tri)
                threeway = {"n": len(tri), "nli_vs_judge": rnd(nj), "nli_vs_human": rnd(nh),
                            "judge_vs_human": rnd(jh), "all_three_agree": rnd(all3)}
    out["three_way_agreement"] = threeway if threeway else {
        "status": "skipped", "reason": "human_grounded column not filled in human_label_sheet_d3.csv"}

    out["cells"] = cells

    OUT_JS.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    # ----------------------------- markdown -----------------------------
    md = []
    md.append("# H2b: independent-family NLI grounding cross-check\n")
    m = out["meta"]
    md.append(f"NLI model: `{m['nli_model_id']}` revision `{m['nli_revision']}` "
              f"(labels {m['nli_id2label']}), CPU, {m['deterministic']}.\n")
    md.append(f"> {m['definitions_note']}\n")
    md.append(f"Premise = {m['premise']}. Hypothesis = {m['hypothesis']}. "
              f"Aggregation: {m['aggregation']}. Primary grounding cut = entail >= {GROUND_THRESHOLD}.\n")

    md.append("## 1. NLI vs judge grounding (over the judge's grounding-decision cells)\n")
    g = out["nli_vs_judge_grounding"]
    md.append(f"Over the **{g['n']}** cells where the judge recorded a grounding decision:")
    md.append(f"- **observed agreement: {g['observed_agreement']}** (reported first)")
    md.append(f"- Cohen's kappa: {g['cohen_kappa']}  |  PABAK: {g['pabak']}")
    md.append(f"- judge_grounded marginal: {g['judge_grounded_marginal']}; nli_grounded marginal: {g['nli_grounded_marginal']}")
    md.append(f"- {g['note']}\n")

    md.append("## 2. Condition D double-check (independent of the same-family judge)\n")
    d = out["condition_D_double_check"]
    md.append(f"Rate entailed by the false (counterfactual) document: **{d['rate_entailed_by_false_doc']}** "
              f"({d['n']} cells). Rate contradicting the gold claim: **{d['rate_contradicts_gold']}**.\n")
    md.append("| item | model | entail(counterfactual->answer) | entailed>=0.5 | contra(answer,gold) | contradicts_gold>=0.5 |")
    md.append("|---|---|---|---|---|---|")
    for x in d["rows"]:
        md.append(f"| {x['item_id']} | {x['model_tag']} | {x['entail_by_counterfactual']} | "
                  f"{x['entailed_by_false_doc']} | {x['contra_gold']} | {x['contradicts_gold']} |")
    md.append("")

    md.append("## 3. Independent grounding rate per condition (non-abstained context cells)\n")
    md.append("| condition | subset | n | nli_grounded rate (entail>=0.5) |")
    md.append("|---|---|---|---|")
    for cond, v in out["per_condition_grounding_rate"].items():
        md.append(f"| {cond} | {v['subset']} | {v['n']} | {v['nli_grounded_rate']} |")
    md.append("")

    md.append("## 4. Threshold sensitivity (grounding rate over the broader non-abstained set)\n")
    sw = out["threshold_sensitivity"]
    md.append(f"n = {sw['n_broad']} cells (B1 non-abstained + B2 non-abstained + C-correct + D).\n")
    md.append("| threshold | overall | B1 | B2 | C | D |")
    md.append("|---|---|---|---|---|---|")
    for t in THRESHOLDS:
        r = sw["rates"][str(t)]
        pc = r["per_condition"]
        md.append(f"| {t} | {r['overall']} | {pc['B1']} | {pc['B2']} | {pc['C']} | {pc['D']} |")
    md.append("")

    md.append("## 5. Three-way NLI vs judge vs human grounding\n")
    tw = out["three_way_agreement"]
    if tw.get("status") == "skipped":
        md.append(f"Skipped: {tw['reason']}.\n")
    else:
        md.append(f"Over {tw['n']} cells with a human grounding label: NLI-vs-judge {tw['nli_vs_judge']}, "
                  f"NLI-vs-human {tw['nli_vs_human']}, judge-vs-human {tw['judge_vs_human']}, "
                  f"all three agree {tw['all_three_agree']}.\n")

    md.append("## Note on definitions\n")
    md.append(m["definitions_note"] + "\n")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    # outputs are complete: drop the resume cache so no helper artefact is left behind
    try:
        CACHE.unlink()
    except FileNotFoundError:
        pass
    print(f"\nWrote {OUT_MD.name} and {OUT_JS.name}")
    print("NLI vs judge over", g["n"], "cells: observed agreement", g["observed_agreement"],
          "| kappa", g["cohen_kappa"], "| PABAK", g["pabak"])
    print("D: entailed-by-false-doc rate", d["rate_entailed_by_false_doc"],
          "| contradicts-gold rate", d["rate_contradicts_gold"])


if __name__ == "__main__":
    main()
