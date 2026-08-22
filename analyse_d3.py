"""
analyse_d3.py
-------------
The single producing script for the five D3 quantities that previously existed only as
prose in analysis_d3.md / retrieval_recall_d3.md / interannotator_kj_aneesha.md /
judge_outlier_cells.md, with no committed code behind them.

It regenerates, from the FROZEN artefacts only:

  1. Per-condition correctness, split by model and pooled, with Wilson 95% intervals.
  2. McNemar exact two-sided binomial tests: A vs B1 and B1 vs B2, pooled and per model,
     paired strictly on (item_id, model_tag).
  3. Inter-annotator agreement (KJ vs Aneesha): raw agreement, Cohen's kappa, PABAK for
     the six-way label and for binary correct-vs-not, plus the confusion matrix and the
     grounding-decision agreement.
  4. Judge-outlier cross-tabulation: cells where both humans agree and the judge differs,
     and cells where all three differ.
  5. Retrieval Hit@k of the gold source paper on the clean index, reusing the experiment's
     exact retrieval path.

...and then VERIFIES every figure against the value already published, printing a
PASS/FAIL table. On any mismatch it prints the discrepancy prominently, states which
side is more likely correct, and exits non-zero WITHOUT adjusting anything to match.

SCOPE, deliberately: ALL 12 items and BOTH models, with NO exclusion list of any kind.
The pilot-era exclusion set that core/analyse_results.py carries (a set of pilot item
indices, one of which collides with a valid D3 item) is not used, imported or referenced
here. Every denominator below is the full 24 cells per condition.

READ-ONLY. Inputs are opened for reading only; the ChromaDB index is opened read-only and
never re-embedded or written. Nothing is regenerated: no model calls for generation, no
judge calls, no NLI. Only the two NEW output files are written.

Determinism: items 1-4 are pure arithmetic over frozen files. Item 5 is a similarity
search over a fixed index with a fixed embedding model on CPU, which is deterministic for
a fixed index and query.

Inputs (all read-only):
    results_d3.jsonl                             authoritative 120 cells
    d3_eval_set.json                             12 items (questions + gold DOIs)
    human_label_key_d3.json                      row_uid -> judge label
    KJ_full_labels_d3_20260718.csv               rater 1
    AneeshaGunaratne_full_labels_d3_20260717.csv rater 2
    chroma_db_clean/ (collection owf_clean_v1)   via core/conditions.py, stage 5 only

Outputs (NEW filenames; nothing existing is overwritten):
    analysis_d3_full.md
    analysis_d3_full.json

Usage:
    python analyse_d3.py                  # all five stages (default)
    python analyse_d3.py --skip-retrieval # stages 1-4 only, no index load
    python analyse_d3.py --retrieval      # explicit opt-in (same as default)

NOTE ON THE INTERPRETER: stages 1-4 are stdlib-only and run under any Python 3.8+.
Stage 5 needs the project venv (langchain / chromadb / sentence-transformers), i.e.
    ..\venv\Scripts\python.exe analyse_d3.py
Run under a bare system Python it will report the missing module and tell you to use
--skip-retrieval, rather than half-producing a report.

NOTE ON THE INDEX MTIME: opening the Chroma collection updates chroma_db_clean/
chroma.sqlite3's modification timestamp even though nothing is written -- SQLite touches
the file when a connection is opened. Stage 5 asserts the collection's row counts before
reading, so an actual change to the index is caught rather than assumed away.
"""

import os
import sys
import csv
import json
import math
import argparse
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- frozen inputs (read-only) ------------------------------------------------
RESULTS_JSONL = ROOT / "results_d3.jsonl"
EVAL_SET      = ROOT / "d3_eval_set.json"
JUDGE_KEY     = ROOT / "human_label_key_d3.json"
RATER_KJ      = ROOT / "KJ_full_labels_d3_20260718.csv"
RATER_AN      = ROOT / "AneeshaGunaratne_full_labels_d3_20260717.csv"

# ---- new outputs --------------------------------------------------------------
OUT_MD = ROOT / "analysis_d3_full.md"
OUT_JS = ROOT / "analysis_d3_full.json"

CONDITIONS = ["A", "B1", "B2", "C", "D"]
MODELS     = ["8b", "70b"]
SIX_LABELS = ["correct", "abstention", "retrieval_failure",
              "ungrounded_hallucination", "grounded_but_wrong", "parametric_error"]

# Expected counts, asserted loudly rather than assumed.
N_ITEMS = 12
N_CELLS = 120

# Clean-index shape as built and recorded in owf_clean_v1_MANIFEST.md. Stage 5 asserts
# these before reading, so a rebuilt or extended collection is caught rather than silently
# shifting the retrieval ranks.
EXPECTED_PAPERS = 501
EXPECTED_CHUNKS = 34502

WILSON_Z = 1.959963984540054   # exact two-sided normal quantile for 95%, matching
                               # analysis_d3.json:17 (core/analyse_results.py uses 1.96;
                               # the difference is below the third decimal of any interval)


# ==================================================================================
# small stats helpers (stdlib only, no scipy dependency)
# ==================================================================================

def wilson(k, n, z=WILSON_Z):
    """Wilson score interval for a binomial proportion. Well-behaved at p=0 and p=1,
    which matters here: B2 is 24/24 and D is 0/24."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom  = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half   = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(b, c):
    """
    Exact two-sided binomial McNemar test on the discordant pairs.

    b = discordant pairs where the FIRST condition is correct and the second is not
    c = discordant pairs where the SECOND is correct and the first is not

    Under H0 each discordant pair is a fair coin, so p = 2 * P(X <= min(b,c)) with
    X ~ Binomial(b + c, 0.5), capped at 1. Concordant pairs carry no information and are
    correctly excluded from n.

    The continuity-corrected chi-square (|b-c|-1)^2 / (b+c) is returned alongside for
    comparability with the previously published table, but the EXACT p is the reported
    statistic: with n as small as 1-14 discordant pairs the chi-square approximation is
    not trustworthy.
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p_exact": 1.0, "chi2_cc": None}
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) * (0.5 ** n)
    p = min(1.0, 2.0 * tail)
    chi2 = (abs(b - c) - 1) ** 2 / n
    return {"b": b, "c": c, "n_discordant": n, "p_exact": p, "chi2_cc": chi2}


def observed_agreement(pairs):
    return None if not pairs else sum(1 for a, b in pairs if a == b) / len(pairs)


def cohen_kappa(pairs):
    """
    Unweighted Cohen's kappa. Returns (po, pe, kappa, n, n_categories, degenerate).

    `degenerate` is True when expected agreement is 1 (both raters used a single class),
    in which case kappa is mathematically undefined rather than zero. We return None and
    flag it, because emitting 0.0 there would read as 'no agreement' when agreement is in
    fact perfect.
    """
    n = len(pairs)
    if n == 0:
        return (None, None, None, 0, 0, False)
    cats = sorted(set(a for a, _ in pairs) | set(b for _, b in pairs))
    k = len(cats)
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    if (1 - pe) <= 1e-12:
        return (po, pe, None, n, k, True)
    return (po, pe, (po - pe) / (1 - pe), n, k, False)


def pabak(po, k):
    """Prevalence-adjusted bias-adjusted kappa, Byrt's multi-category form
    (k*po - 1)/(k - 1); reduces to 2*po - 1 at k = 2. Defined even when kappa is not."""
    if po is None or k < 2:
        return None
    return (k * po - 1) / (k - 1)


def rnd(x, p=4):
    return None if x is None else round(x, p)


def norm_label(s):
    """Same normalisation the human-label scorer applies, so rater free-text spacing or
    hyphenation cannot masquerade as disagreement."""
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


def binarise(label):
    return "correct" if label == "correct" else "not_correct"


def condition_from_cell_key(cell_key):
    parts = cell_key.split("|")
    return parts[1] if len(parts) >= 2 else "?"


class AnalysisError(RuntimeError):
    """Raised when a structural assumption about the frozen data does not hold."""


def require(condition, message):
    if not condition:
        raise AnalysisError(message)


# ==================================================================================
# loading
# ==================================================================================

def load_cells():
    """
    Load the authoritative 120 result cells from results_d3.jsonl.

    The six-way label is reconstructed with the project's standing rule: a correct answer
    is stored as an EMPTY failure_type, so `failure_type or "correct"`. This is the same
    rule core/analyse_results.py:79 applies and the same one export_human_labels.py used
    to build the judge key, which is why the labels here join cleanly to the rater sheets.
    """
    require(RESULTS_JSONL.exists(), f"missing frozen input: {RESULTS_JSONL}")
    cells = []
    with open(RESULTS_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("record_type") == "run_config":
                continue
            cells.append({
                "item_idx":   rec["item_idx"],
                "item_id":    rec["item_id"],
                "condition":  rec["condition"],
                "model_tag":  rec["model_tag"],
                "cell_key":   rec["cell_key"],
                "label":      rec.get("failure_type") or "correct",
                "grounded":   rec.get("grounded"),
                "abstained":  rec.get("abstained"),
            })

    require(len(cells) == N_CELLS,
            f"expected {N_CELLS} result cells, found {len(cells)}")
    item_ids = sorted({c["item_id"] for c in cells})
    require(len(item_ids) == N_ITEMS,
            f"expected {N_ITEMS} distinct item_ids, found {len(item_ids)}: {item_ids}")
    for m in MODELS:
        for cond in CONDITIONS:
            n = sum(1 for c in cells if c["model_tag"] == m and c["condition"] == cond)
            require(n == N_ITEMS,
                    f"expected {N_ITEMS} cells for model={m} condition={cond}, found {n}")
    return cells, item_ids


def load_raters():
    """Load both rater sheets and the judge key, joined on row_uid."""
    for p in (JUDGE_KEY, RATER_KJ, RATER_AN):
        require(p.exists(), f"missing frozen input: {p}")

    key = json.load(open(JUDGE_KEY, encoding="utf-8"))

    def sheet(path):
        rows = {}
        for r in csv.DictReader(open(path, encoding="utf-8")):
            uid = r["row_uid"]
            require(uid not in rows, f"duplicate row_uid {uid} in {path.name}")
            rows[uid] = {
                "item_id":   r.get("item_id"),
                "condition": r.get("condition"),
                "label":     norm_label(r.get("human_label")),
                "grounded":  parse_bool(r.get("human_grounded")),
            }
        return rows

    kj = sheet(RATER_KJ)
    an = sheet(RATER_AN)

    common = sorted(set(kj) & set(an) & set(key))
    require(len(common) == N_CELLS,
            f"expected {N_CELLS} row_uids common to both raters and the judge key, "
            f"found {len(common)} (KJ {len(kj)}, Aneesha {len(an)}, key {len(key)})")
    for uid in common:
        require(kj[uid]["label"] is not None, f"KJ left row_uid {uid} unlabelled")
        require(an[uid]["label"] is not None, f"Aneesha left row_uid {uid} unlabelled")
    return key, kj, an, common


# ==================================================================================
# 1. per-condition correctness
# ==================================================================================

def stage1_correctness(cells):
    out = OrderedDict()
    per_condition = OrderedDict()

    for cond in CONDITIONS:
        entry = OrderedDict()
        for scope in MODELS + ["pooled"]:
            sub = [c for c in cells if c["condition"] == cond
                   and (scope == "pooled" or c["model_tag"] == scope)]
            k = sum(1 for c in sub if c["label"] == "correct")
            n = len(sub)
            p, lo, hi = wilson(k, n)
            entry[scope] = {"correct": k, "n": n, "prop": rnd(p),
                            "wilson_lo": rnd(lo), "wilson_hi": rnd(hi)}
        # full six-way breakdown, pooled
        entry["label_counts_pooled"] = dict(
            Counter(c["label"] for c in cells if c["condition"] == cond))
        per_condition[cond] = entry
    out["per_condition"] = per_condition

    per_model = OrderedDict()
    for scope in MODELS + ["pooled"]:
        sub = [c for c in cells if scope == "pooled" or c["model_tag"] == scope]
        k = sum(1 for c in sub if c["label"] == "correct")
        n = len(sub)
        p, lo, hi = wilson(k, n)
        per_model[scope] = {"correct": k, "n": n, "prop": rnd(p),
                            "wilson_lo": rnd(lo), "wilson_hi": rnd(hi)}
    out["overall_by_model"] = per_model

    out["note"] = ("All 12 items and both models, no exclusion list. 'correct' means the "
                   "judge labelled the cell correct; abstention and no_answer count as "
                   "not correct. Wilson z = %.15g." % WILSON_Z)
    return out


# ==================================================================================
# 2. McNemar
# ==================================================================================

def _paired(cells, cond_a, cond_b, scope):
    """
    Build the paired correctness vectors for two conditions.

    Pairing key is (item_id, model_tag) -- NOT item_idx alone. Keying on the item index
    only would silently collapse the two models onto one another and discard half the
    data, which is exactly the defect this script exists to supersede.
    """
    idx = {}
    for c in cells:
        if c["condition"] in (cond_a, cond_b):
            if scope != "pooled" and c["model_tag"] != scope:
                continue
            idx[(c["item_id"], c["model_tag"], c["condition"])] = (c["label"] == "correct")

    units = sorted({(iid, m) for (iid, m, _) in idx})
    pairs = []
    for iid, m in units:
        ka = (iid, m, cond_a)
        kb = (iid, m, cond_b)
        require(ka in idx and kb in idx,
                f"incomplete pair for item_id={iid} model={m} "
                f"({cond_a} present={ka in idx}, {cond_b} present={kb in idx})")
        pairs.append(((iid, m), idx[ka], idx[kb]))
    return pairs


def stage2_mcnemar(cells):
    expected_pairs = {"8b": N_ITEMS, "70b": N_ITEMS, "pooled": N_ITEMS * len(MODELS)}
    out = OrderedDict()

    for cond_a, cond_b in (("A", "B1"), ("B1", "B2")):
        comparison = OrderedDict()
        for scope in ["pooled"] + MODELS:
            pairs = _paired(cells, cond_a, cond_b, scope)

            # Fail loudly rather than quietly reporting a test on the wrong n.
            require(len(pairs) == expected_pairs[scope],
                    f"McNemar {cond_a} vs {cond_b} [{scope}]: expected "
                    f"{expected_pairs[scope]} pairs, built {len(pairs)}. "
                    f"Pairing is on (item_id, model_tag); a mismatch here means the "
                    f"frozen results are not the expected 12 items x 2 models.")

            b = sum(1 for _, a_ok, b_ok in pairs if a_ok and not b_ok)   # first only
            c = sum(1 for _, a_ok, b_ok in pairs if b_ok and not a_ok)   # second only
            res = mcnemar_exact(b, c)
            res["n_pairs"] = len(pairs)
            res["b_means"] = f"{cond_a}-only correct"
            res["c_means"] = f"{cond_b}-only correct"
            res["discordant_units"] = sorted(
                [f"{iid}/{m}" for (iid, m), a_ok, b_ok in pairs if a_ok != b_ok])
            comparison[scope] = res
        out[f"{cond_a}_vs_{cond_b}"] = comparison

    out["note"] = (
        "Exact two-sided binomial on the discordant pairs: p = 2 * P(X <= min(b,c)), "
        "X ~ Binomial(b+c, 0.5), capped at 1. Continuity-corrected chi-square is reported "
        "for comparability only. Pairing is strictly on (item_id, model_tag), asserted to "
        "be 12 pairs per model and 24 pooled. CAVEAT: the pooled test treats the 8b and "
        "70b observations on the same item as independent, which they are not; the "
        "per-model tests carry no such assumption and should be read first.")
    return out


# ==================================================================================
# 3. inter-annotator agreement
# ==================================================================================

def stage3_interannotator(kj, an, common):
    out = OrderedDict()
    out["n"] = len(common)
    out["raters"] = {"rater_1": RATER_KJ.name, "rater_2": RATER_AN.name}

    # --- six-way ---
    six = [(kj[u]["label"], an[u]["label"]) for u in common]
    po6, pe6, k6, n6, kc6, deg6 = cohen_kappa(six)
    out["sixway"] = {
        "n": n6, "raw_agreement": rnd(po6), "expected_agreement_pe": rnd(pe6),
        "cohen_kappa": rnd(k6), "kappa_undefined": deg6,
        "pabak": rnd(pabak(po6, kc6)), "n_categories_for_pabak": kc6,
        "marginal_rater_1": dict(Counter(a for a, _ in six)),
        "marginal_rater_2": dict(Counter(b for _, b in six)),
    }

    # --- binary ---
    binp = [(binarise(a), binarise(b)) for a, b in six]
    pob, peb, kb, nb, kcb, degb = cohen_kappa(binp)
    out["binary_correct_vs_not"] = {
        "n": nb, "raw_agreement": rnd(pob), "expected_agreement_pe": rnd(peb),
        "cohen_kappa": rnd(kb), "kappa_undefined": degb,
        "pabak": rnd(pabak(pob, 2)),
        "marginal_rater_1": dict(Counter(a for a, _ in binp)),
        "marginal_rater_2": dict(Counter(b for _, b in binp)),
    }

    # --- confusion matrix (rows = rater 1 / KJ, cols = rater 2 / Aneesha) ---
    labels_seen = [L for L in SIX_LABELS if any(L in pr for pr in six)]
    for extra in sorted({a for a, _ in six} | {b for _, b in six}):
        if extra not in labels_seen:
            labels_seen.append(extra)
    cm = {h: {j: 0 for j in labels_seen} for h in labels_seen}
    for a, b in six:
        cm[a][b] += 1
    out["confusion_matrix"] = {"labels": labels_seen,
                               "rows_rater_1_cols_rater_2": cm}

    # --- grounding decision, over cells where BOTH raters recorded a call ---
    g_uids = [u for u in common
              if kj[u]["grounded"] is not None and an[u]["grounded"] is not None]
    gp = [(kj[u]["grounded"], an[u]["grounded"]) for u in g_uids]
    pog, peg, kg, ng, kcg, degg = cohen_kappa(gp)
    marg1 = Counter(a for a, _ in gp)
    marg2 = Counter(b for _, b in gp)
    single_class = (len(marg1) <= 1 and len(marg2) <= 1)
    out["grounding_decision"] = {
        "n_both_recorded": len(gp),
        "n_rater_1_recorded": sum(1 for u in common if kj[u]["grounded"] is not None),
        "n_rater_2_recorded": sum(1 for u in common if an[u]["grounded"] is not None),
        "raw_agreement": rnd(pog),
        "cohen_kappa": rnd(kg),
        "kappa_undefined": bool(degg or single_class),
        "pabak": rnd(pabak(pog, 2)),
        "marginal_rater_1": {str(k): v for k, v in marg1.items()},
        "marginal_rater_2": {str(k): v for k, v in marg2.items()},
        "degenerate_marginals": single_class,
        "reading": ("DEGENERATE MARGINALS: both raters used a single class on every "
                    "jointly-recorded cell, so expected agreement is 1 and Cohen's kappa "
                    "is mathematically UNDEFINED (not zero). Read raw agreement and "
                    "PABAK. Agreement here is perfect, not absent."
                    if (degg or single_class) else
                    "Marginals are non-degenerate; kappa reads directly."),
    }

    # --- per-condition raw agreement ---
    bycond = defaultdict(list)
    for u in common:
        bycond[kj[u]["condition"]].append((kj[u]["label"], an[u]["label"]))
    out["per_condition_raw_agreement"] = OrderedDict(
        (cond, {"n": len(bycond.get(cond, [])),
                "raw_agreement": rnd(observed_agreement(bycond.get(cond, [])))})
        for cond in CONDITIONS)

    out["note"] = ("Human-vs-human only; the judge is not involved in this section. "
                   "Skewed marginals depress Cohen's kappa even at high raw agreement "
                   "(the kappa paradox), so raw agreement and PABAK are reported "
                   "alongside kappa, never kappa alone.")
    return out


# ==================================================================================
# 4. judge-outlier cross-tabulation
# ==================================================================================

def stage4_judge_outliers(key, kj, an, common):
    both_agree_judge_differs = []
    all_three_differ = []

    for uid in common:
        h1 = kj[uid]["label"]
        h2 = an[uid]["label"]
        j  = norm_label(key[uid]["judge_label"])
        item = kj[uid]["item_id"]
        cond = kj[uid]["condition"]
        model = key[uid].get("model_tag")

        if h1 == h2 and j != h1:
            crosses = binarise(h1) != binarise(j)
            if crosses:
                direction = ("judge lenient (judge=correct, both humans=not-correct)"
                             if binarise(j) == "correct" else
                             "judge strict (judge=not-correct, both humans=correct)")
            else:
                direction = "within not-correct (label flavour only)"
            both_agree_judge_differs.append({
                "row_uid": uid, "item_id": item, "condition": cond, "model_tag": model,
                "humans_shared": h1, "judge": j,
                "crosses_binary_boundary": crosses, "direction": direction,
            })
        elif len({h1, h2, j}) == 3:
            all_three_differ.append({
                "row_uid": uid, "item_id": item, "condition": cond, "model_tag": model,
                "rater_1_kj": h1, "rater_2_aneesha": h2, "judge": j,
                "crosses_binary_boundary": len({binarise(h1), binarise(h2), binarise(j)}) > 1,
                "direction": ("judge lenient (judge=correct, neither human agrees)"
                              if binarise(j) == "correct"
                              and binarise(h1) != "correct" and binarise(h2) != "correct"
                              else "no consistent direction"),
            })

    both_agree_judge_differs.sort(key=lambda r: (r["item_id"], r["condition"]))
    all_three_differ.sort(key=lambda r: (r["item_id"], r["condition"]))

    n_cross = sum(1 for r in both_agree_judge_differs if r["crosses_binary_boundary"])
    n_lenient = sum(1 for r in both_agree_judge_differs
                    if r["crosses_binary_boundary"] and r["direction"].startswith("judge lenient"))

    return OrderedDict([
        ("both_humans_agree_judge_differs", both_agree_judge_differs),
        ("n_both_agree_judge_differs", len(both_agree_judge_differs)),
        ("n_crossing_binary_boundary", n_cross),
        ("n_crossing_and_judge_lenient", n_lenient),
        ("all_three_differ", all_three_differ),
        ("n_all_three_differ", len(all_three_differ)),
        ("note", "These are the cleanest judge-outlier cells: two independent raters "
                 "landed on the same label and only the automatic judge dissents."),
    ])


# ==================================================================================
# 5. retrieval Hit@k
# ==================================================================================

def stage5_retrieval(max_k=10):
    """
    Hit@k of the gold source paper, reusing the experiment's exact retrieval path.

    Imported lazily so stages 1-4 need neither torch nor chromadb, and so
    --skip-retrieval is genuinely cheap. The import pulls core/conditions.py, which loads
    the store through the SAME code path Condition B1 uses (conditions.retrieve ->
    conditions.get_store -> rag_pipeline.load_existing_vector_store) under the default
    'clean' retrieval profile: collection owf_clean_v1 in chroma_db_clean/, BGE
    query-instruction embeddings (prefix on queries, passages plain, normalised).

    The index is opened read-only: nothing here embeds a passage, adds a document, or
    creates a collection. The query is the RAW item question, exactly as B1 sends it.
    DOIs are canonicalised on both sides with the codebase's own canonicalise_doi.
    """
    def _index_integrity(db_dir):
        """
        Read the collection's row counts straight from sqlite in READ-ONLY mode, before
        any Chroma client touches it, and assert they are what the frozen study used.

        This exists because the index file's MODIFICATION TIME is not a usable integrity
        signal: SQLite bumps it whenever a connection is opened, so simply querying the
        collection re-dates the file without changing a byte. Row counts do not move
        unless the index actually changed, so a rebuild or an append is caught here
        rather than silently shifting every Hit@k rank.
        """
        import sqlite3
        path = Path(db_dir) / "chroma.sqlite3"
        require(path.exists(), f"clean index not found at {path}")
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            n_emb = con.execute("select count(*) from embeddings").fetchone()[0]
            n_doi = con.execute(
                "select count(distinct string_value) from embedding_metadata "
                "where key='doi'").fetchone()[0]
            colls = [r[1] for r in con.execute("select id,name from collections")]
        finally:
            con.close()
        require(n_emb == EXPECTED_CHUNKS,
                f"index integrity: expected {EXPECTED_CHUNKS} chunks in the clean index, "
                f"found {n_emb}. The collection has been rebuilt or appended to since the "
                f"frozen study; Hit@k below would NOT be comparable to the published "
                f"figures. Investigate before trusting anything in stage 5.")
        require(n_doi == EXPECTED_PAPERS,
                f"index integrity: expected {EXPECTED_PAPERS} distinct DOIs, found {n_doi}. "
                f"See the note above.")
        return {"collections": colls, "n_chunks": n_emb, "n_papers": n_doi,
                "verified_against": f"{EXPECTED_PAPERS} papers / {EXPECTED_CHUNKS} chunks "
                                    f"(owf_clean_v1_MANIFEST.md)"}

    sys.path.insert(0, str(ROOT / "core"))
    try:
        from conditions import retrieve, canonicalise_doi, COLLECTION, DB_DIR, PROFILE, EMB_MODEL
    except Exception as e:                                    # pragma: no cover
        raise AnalysisError(
            f"could not load the retrieval path ({type(e).__name__}: {e}). "
            f"Re-run with --skip-retrieval to produce stages 1-4 without it.")

    integrity = _index_integrity(DB_DIR)

    eval_set = json.load(open(EVAL_SET, encoding="utf-8"))
    require(len(eval_set) == N_ITEMS,
            f"expected {N_ITEMS} eval items, found {len(eval_set)}")

    rows = []
    for item in eval_set:
        gold = {canonicalise_doi(d) for d in item.get("matched_dois", []) if d}
        require(bool(gold), f"item {item['id']} has no matched_dois")
        got = retrieve(item["question"], k=max_k)          # no exclusions: this is B1's path
        ranked = [g["doi"] for g in got]
        first = None
        for rank, doi in enumerate(ranked, 1):
            if doi in gold:
                first = rank
                break
        rows.append({
            "item_id": item["id"],
            "gold_doi_canonical": sorted(gold),
            "n_retrieved": len(ranked),
            "first_hit_rank": first,
            "retrieved_dois": ranked,
            "retrieved_scores": [round(g["score"], 4) for g in got],
        })

    hits = OrderedDict()
    for k in (1, 3, 5, 10):
        h = sum(1 for r in rows if r["first_hit_rank"] is not None and r["first_hit_rank"] <= k)
        hits[f"hit@{k}"] = {"hits": h, "n": len(rows), "rate": rnd(h / len(rows))}

    return OrderedDict([
        ("profile", PROFILE),
        ("collection", COLLECTION),
        ("db_dir", DB_DIR),
        ("embedding_model", EMB_MODEL),
        ("index_integrity", integrity),
        ("max_k", max_k),
        ("query_construction", "raw item question, identical to Condition B1"),
        ("doi_matching", "conditions.canonicalise_doi applied to both the gold DOI and "
                         "the stored chunk DOI"),
        ("hit_at_k", hits),
        ("per_item", rows),
        ("note", "A hit at rank r means at least one of the top-r retrieved chunks has a "
                 "canonicalised DOI in the item's gold set. Every gold paper is present "
                 "in the index, so the denominator is a single 12 with no indexed-only "
                 "subset. NOTE this is recall within a corpus that was completed to "
                 "contain the gold papers (see owf_clean_v1_MANIFEST.md, 'D3 source "
                 "rescue'), not end-to-end corpus recall."),
    ])


# ==================================================================================
# VERIFICATION against the already-published values
# ==================================================================================

# (label, computed_getter, expected_value, tolerance)
#   tolerance None -> exact equality (integers / counts)
# Sources for every expected value are named in the `source` field so a reader can check
# the published figure without trusting this script.
def build_checks(s1, s2, s3, s5):
    checks = []

    def add(label, computed, expected, tol=None, source=""):
        checks.append({"check": label, "computed": computed, "expected": expected,
                       "tolerance": tol, "source": source})

    # --- 1. per-condition correctness (pooled counts) ---
    for cond, exp in (("A", 8), ("B1", 22), ("B2", 24), ("C", 4), ("D", 0)):
        add(f"{cond} correct (pooled, /24)",
            s1["per_condition"][cond]["pooled"]["correct"], exp,
            source="analysis_d3.md:9-13")
        add(f"{cond} n (pooled)",
            s1["per_condition"][cond]["pooled"]["n"], 24,
            source="12 items x 2 models, no exclusions")

    # --- 1b. per-model overall ---
    add("8b overall correct (/60)",  s1["overall_by_model"]["8b"]["correct"], 30,
        source="analysis_d3.md:19")
    add("70b overall correct (/60)", s1["overall_by_model"]["70b"]["correct"], 28,
        source="analysis_d3.md:20")

    # --- 2. McNemar ---
    ab = s2["A_vs_B1"]
    add("McNemar A-vs-B1 pooled b", ab["pooled"]["b"], 0, source="analysis_d3.md:28")
    add("McNemar A-vs-B1 pooled c", ab["pooled"]["c"], 14, source="analysis_d3.md:28")
    add("McNemar A-vs-B1 pooled p", ab["pooled"]["p_exact"], 0.0001, 5e-4,
        source="analysis_d3.md:28 (published rounded to 4 dp)")
    add("McNemar A-vs-B1 8b p",  ab["8b"]["p_exact"],  0.008, 5e-4, source="analysis_d3.md:29")
    add("McNemar A-vs-B1 70b p", ab["70b"]["p_exact"], 0.031, 5e-4, source="analysis_d3.md:30")
    add("McNemar A-vs-B1 pooled n_pairs", ab["pooled"]["n_pairs"], 24, source="design")
    add("McNemar A-vs-B1 8b n_pairs",  ab["8b"]["n_pairs"],  12, source="design")
    add("McNemar A-vs-B1 70b n_pairs", ab["70b"]["n_pairs"], 12, source="design")

    bb = s2["B1_vs_B2"]
    add("McNemar B1-vs-B2 pooled b", bb["pooled"]["b"], 0, source="analysis_d3.md:31")
    add("McNemar B1-vs-B2 pooled c", bb["pooled"]["c"], 2, source="analysis_d3.md:31")
    add("McNemar B1-vs-B2 pooled p", bb["pooled"]["p_exact"], 0.5, 5e-4,
        source="analysis_d3.md:31")
    add("McNemar B1-vs-B2 pooled n_pairs", bb["pooled"]["n_pairs"], 24, source="design")

    # --- 3. inter-annotator ---
    add("Inter-annotator six-way raw",   s3["sixway"]["raw_agreement"], 0.9583, 1e-4,
        source="interannotator_kj_aneesha.md:24")
    add("Inter-annotator six-way kappa", s3["sixway"]["cohen_kappa"],   0.9369, 1e-4,
        source="interannotator_kj_aneesha.md:24")
    add("Inter-annotator binary raw",    s3["binary_correct_vs_not"]["raw_agreement"], 0.975, 1e-4,
        source="interannotator_kj_aneesha.md:25")
    add("Inter-annotator binary kappa",  s3["binary_correct_vs_not"]["cohen_kappa"], 0.9492, 1e-4,
        source="interannotator_kj_aneesha.md:25")
    add("Inter-annotator grounding n (both recorded)",
        s3["grounding_decision"]["n_both_recorded"], 72,
        source="interannotator_kj_aneesha.md:26,36")
    add("Inter-annotator grounding raw",
        s3["grounding_decision"]["raw_agreement"], 1.0, 1e-9,
        source="interannotator_kj_aneesha.md:26")

    # --- 5. retrieval ---
    if s5 is not None:
        add("Hit@1 hits (/12)",  s5["hit_at_k"]["hit@1"]["hits"],  8,  source="retrieval_recall_d3.md:50")
        add("Hit@3 hits (/12)",  s5["hit_at_k"]["hit@3"]["hits"],  8,  source="retrieval_recall_d3.md:51")
        add("Hit@5 hits (/12)",  s5["hit_at_k"]["hit@5"]["hits"],  8,  source="retrieval_recall_d3.md:52")
        add("Hit@10 hits (/12)", s5["hit_at_k"]["hit@10"]["hits"], 11, source="retrieval_recall_d3.md:53")

    for ch in checks:
        comp, exp, tol = ch["computed"], ch["expected"], ch["tolerance"]
        if comp is None:
            ch["pass"] = False
            ch["delta"] = None
        elif tol is None:
            ch["pass"] = (comp == exp)
            ch["delta"] = None
        else:
            ch["delta"] = round(abs(comp - exp), 8)
            ch["pass"] = ch["delta"] <= tol
    return checks


def print_verification(checks, retrieval_ran):
    width = max(len(c["check"]) for c in checks) + 2
    print()
    print("=" * (width + 46))
    print("VERIFICATION against previously published values".center(width + 46))
    print("=" * (width + 46))
    print("check".ljust(width) + "computed".rjust(12) + "expected".rjust(12) + "result".rjust(10))
    print("-" * (width + 46))
    for c in checks:
        comp = c["computed"]
        exp = c["expected"]
        fmt = (lambda v: "None" if v is None else
               (str(v) if isinstance(v, int) else f"{v:.6g}"))
        print(c["check"].ljust(width) + fmt(comp).rjust(12) + fmt(exp).rjust(12)
              + ("PASS" if c["pass"] else "**FAIL**").rjust(10))
    print("-" * (width + 46))
    n_pass = sum(1 for c in checks if c["pass"])
    print(f"{n_pass}/{len(checks)} checks passed."
          + ("" if retrieval_ran else "  (retrieval stage skipped)"))
    print("=" * (width + 46))
    return n_pass == len(checks)


def print_failure_report(checks):
    fails = [c for c in checks if not c["pass"]]
    bar = "!" * 78
    print()
    print(bar)
    print("!!  DISCREPANCY: a recomputed figure does NOT match the published value.")
    print("!!  The script has NOT been adjusted to match. Resolve before submission.")
    print(bar)
    for c in fails:
        print(f"\n  CHECK    : {c['check']}")
        print(f"  computed : {c['computed']}   (this script, from the frozen artefacts)")
        print(f"  published: {c['expected']}   (source: {c['source']})")
        if c["delta"] is not None:
            print(f"  delta    : {c['delta']}  (tolerance {c['tolerance']})")
    print(f"""
  WHICH IS MORE LIKELY CORRECT, AND WHY
  -------------------------------------
  This script recomputes from the frozen primary artefacts (results_d3.jsonl, the two
  rater CSVs, human_label_key_d3.json, and the live owf_clean_v1 index) with the pairing
  key and denominators asserted at runtime. The published figures in analysis_d3.md,
  interannotator_kj_aneesha.md and retrieval_recall_d3.md were produced by an ad-hoc
  analysis session whose code was never committed, so they cannot be re-derived or
  inspected.

  On that basis THIS SCRIPT'S VALUE is the more likely correct one for any arithmetic
  disagreement -- it is reproducible and its assumptions are checked. The published value
  is more likely correct only if this script has mis-specified something upstream of the
  arithmetic: the wrong label rule, the wrong pairing key, or a changed input file.

  Check in this order before trusting either:
    1. Have any frozen inputs changed? results_d3.jsonl should hold exactly 120 cells over
       12 item_ids and 2 model_tags; both rater CSVs should hold 120 rows each.
    2. For a Hit@k mismatch: has chroma_db_clean/ been rebuilt or appended to since
       2026-07-19? The index mtime is the thing to check first -- a re-embedded or
       extended collection changes ranks without changing any code.
    3. For an agreement mismatch: confirm both rater CSVs are the originals and that no
       cell was edited after 2026-07-18.

  Stopping here. Outputs were still written so the mismatch is on record.""")
    print(bar)


# ==================================================================================
# report writers
# ==================================================================================

def _pct(d):
    return f"{d['correct']}/{d['n']} = {d['prop']:.2f}"


def write_markdown(out, checks, all_pass, retrieval_ran):
    s1, s2, s3, s4 = out["per_condition_correctness"], out["mcnemar"], \
                     out["inter_annotator"], out["judge_outliers"]
    s5 = out.get("retrieval")
    md = []
    A = md.append

    A("# D3 full analysis — regenerated from the frozen artefacts\n")
    A(f"Generated by `analyse_d3.py` on {out['meta']['generated']}. "
      "Read-only over the frozen inputs; no generation, judge or NLI call was made.\n")
    A(f"**Verification: {sum(1 for c in checks if c['pass'])}/{len(checks)} checks "
      f"{'PASSED' if all_pass else '— SEE FAILURES BELOW'}.**\n")
    A("Scope: all 12 items, both subject models, 120 cells. **No exclusion list of any "
      "kind is applied.** The pilot-era exclusion set carried by `core/analyse_results.py` "
      "is not used here; one of its indices collides with a valid D3 item, which is why "
      "that script reports Condition D over 22 cells rather than 24.\n")

    # ---- verification table first: it is the point of the script ----
    A("## 0. Verification against published values\n")
    A("| check | computed | expected | source | result |")
    A("|---|---|---|---|---|")
    for c in checks:
        comp = "None" if c["computed"] is None else (
            str(c["computed"]) if isinstance(c["computed"], int) else f"{c['computed']:.6g}")
        exp = str(c["expected"]) if isinstance(c["expected"], int) else f"{c['expected']:.6g}"
        A(f"| {c['check']} | {comp} | {exp} | `{c['source']}` | "
          f"{'PASS' if c['pass'] else '**FAIL**'} |")
    A("")

    # ---- 1 ----
    A("## 1. Per-condition correctness (Wilson 95% intervals on the pooled rate)\n")
    A("| condition | 8b | 70b | pooled | pooled 95% CI |")
    A("|---|---|---|---|---|")
    for cond in CONDITIONS:
        e = s1["per_condition"][cond]
        A(f"| {cond} | {_pct(e['8b'])} | {_pct(e['70b'])} | {_pct(e['pooled'])} | "
          f"[{e['pooled']['wilson_lo']:.2f}, {e['pooled']['wilson_hi']:.2f}] |")
    A("")
    A("Overall by model:\n")
    A("| scope | correct/n | proportion | 95% CI |")
    A("|---|---|---|---|")
    for scope in MODELS + ["pooled"]:
        e = s1["overall_by_model"][scope]
        A(f"| {scope} | {e['correct']}/{e['n']} | {e['prop']:.2f} | "
          f"[{e['wilson_lo']:.2f}, {e['wilson_hi']:.2f}] |")
    A("")
    A("Full six-way label breakdown (pooled over both models):\n")
    all_labels = [L for L in SIX_LABELS
                  if any(L in s1["per_condition"][c]["label_counts_pooled"] for c in CONDITIONS)]
    A("| condition | " + " | ".join(all_labels) + " |")
    A("|" + "---|" * (len(all_labels) + 1))
    for cond in CONDITIONS:
        counts = s1["per_condition"][cond]["label_counts_pooled"]
        A(f"| {cond} | " + " | ".join(str(counts.get(L, 0)) for L in all_labels) + " |")
    A("")

    # ---- 2 ----
    A("## 2. McNemar tests (exact two-sided binomial, paired on item_id x model)\n")
    A("| comparison | scope | pairs | b | c | discordant | chi2 (cc) | p (exact) |")
    A("|---|---|---|---|---|---|---|---|")
    for comp_name, comp in s2.items():
        if comp_name == "note":
            continue
        for scope in ["pooled"] + MODELS:
            r = comp[scope]
            chi = "—" if r["chi2_cc"] is None else f"{r['chi2_cc']:.4f}"
            A(f"| {comp_name.replace('_', ' ')} | {scope} | {r['n_pairs']} | {r['b']} | "
              f"{r['c']} | {r['n_discordant']} | {chi} | {r['p_exact']:.6g} |")
    A("")
    A(f"> {s2['note']}\n")
    A("Discordant units (the pairs carrying all the information):\n")
    for comp_name, comp in s2.items():
        if comp_name == "note":
            continue
        A(f"- **{comp_name.replace('_', ' ')}**, pooled: "
          f"{', '.join(comp['pooled']['discordant_units']) or 'none'}")
    A("")

    # ---- 3 ----
    A("## 3. Inter-annotator agreement (KJ vs Aneesha; the judge is NOT involved)\n")
    A(f"Raters: `{s3['raters']['rater_1']}` (rater 1) and `{s3['raters']['rater_2']}` "
      f"(rater 2). Joined on `row_uid`; {s3['n']} rows common to both and to the judge key.\n")
    A("| metric | n | raw agreement | Cohen's kappa | PABAK |")
    A("|---|---|---|---|---|")
    for name, blk, nkey in (("six-way label", s3["sixway"], "n"),
                            ("correct vs not (binary)", s3["binary_correct_vs_not"], "n"),
                            ("grounding decision", s3["grounding_decision"], "n_both_recorded")):
        kap = "**undefined**" if blk.get("kappa_undefined") else f"{blk['cohen_kappa']}"
        A(f"| {name} | {blk[nkey]} | {blk['raw_agreement']} | {kap} | {blk['pabak']} |")
    A("")
    g = s3["grounding_decision"]
    A(f"> **Grounding decision.** {g['reading']} Marginals — rater 1 "
      f"{g['marginal_rater_1']}, rater 2 {g['marginal_rater_2']}. "
      f"({g['n_rater_1_recorded']} and {g['n_rater_2_recorded']} calls recorded "
      f"individually; {g['n_both_recorded']} jointly.)\n")
    A("Six-way confusion matrix (rows = KJ, cols = Aneesha):\n")
    labs = s3["confusion_matrix"]["labels"]
    cm = s3["confusion_matrix"]["rows_rater_1_cols_rater_2"]
    A("| KJ \\ Aneesha | " + " | ".join(labs) + " |")
    A("|" + "---|" * (len(labs) + 1))
    for h in labs:
        A(f"| {h} | " + " | ".join(str(cm[h][j]) for j in labs) + " |")
    A("")
    A("Per-condition raw agreement (six-way):\n")
    A("| condition | n | raw agreement |")
    A("|---|---|---|")
    for cond, v in s3["per_condition_raw_agreement"].items():
        A(f"| {cond} | {v['n']} | {v['raw_agreement']} |")
    A("")

    # ---- 4 ----
    A("## 4. Judge-outlier cross-tabulation\n")
    A(f"**(a) Both humans agree, judge differs — n = {s4['n_both_agree_judge_differs']}.** "
      f"{s4['n_crossing_binary_boundary']} cross the correct/not-correct boundary, of which "
      f"{s4['n_crossing_and_judge_lenient']} run judge=correct / humans=not-correct.\n")
    A("| row_uid | item | condition | model | humans (shared) | judge | crosses binary | direction |")
    A("|---|---|---|---|---|---|---|---|")
    for r in s4["both_humans_agree_judge_differs"]:
        A(f"| `{r['row_uid']}` | {r['item_id']} | {r['condition']} | {r['model_tag']} | "
          f"{r['humans_shared']} | {r['judge']} | {'YES' if r['crosses_binary_boundary'] else 'no'} | "
          f"{r['direction']} |")
    A("")
    A(f"**(b) All three differ — n = {s4['n_all_three_differ']}.**\n")
    if s4["all_three_differ"]:
        A("| row_uid | item | condition | model | KJ | Aneesha | judge | crosses binary |")
        A("|---|---|---|---|---|---|---|---|")
        for r in s4["all_three_differ"]:
            A(f"| `{r['row_uid']}` | {r['item_id']} | {r['condition']} | {r['model_tag']} | "
              f"{r['rater_1_kj']} | {r['rater_2_aneesha']} | {r['judge']} | "
              f"{'YES' if r['crosses_binary_boundary'] else 'no'} |")
    else:
        A("None.")
    A("")

    # ---- 5 ----
    A("## 5. Retrieval Hit@k of the gold source paper\n")
    if not retrieval_ran:
        A("Skipped (`--skip-retrieval`). Re-run without the flag to regenerate this section.\n")
    else:
        ii = s5["index_integrity"]
        A(f"Collection `{s5['collection']}` in `{s5['db_dir']}`, profile `{s5['profile']}`, "
          f"embeddings `{s5['embedding_model']}`. Query construction: {s5['query_construction']}. "
          f"DOI matching: {s5['doi_matching']}.\n")
        A(f"Index integrity checked before reading: **{ii['n_papers']} papers / "
          f"{ii['n_chunks']} chunks**, matching `owf_clean_v1_MANIFEST.md`. "
          "(The sqlite file's modification time is *not* an integrity signal — SQLite "
          "re-dates it whenever a connection is opened, so a read-only query bumps the "
          "mtime without changing a byte. Row counts are the signal.)\n")
        A("| k | hits | Hit@k |")
        A("|---|---|---|")
        for kk, v in s5["hit_at_k"].items():
            A(f"| {kk} | {v['hits']}/{v['n']} | {v['rate']:.3f} |")
        A("")
        A("| item_id | gold DOI (canonicalised) | first-hit rank | Hit@5 |")
        A("|---|---|---|---|")
        max_k = s5["max_k"]
        for r in s5["per_item"]:
            fr = r["first_hit_rank"]
            rank_txt = str(fr) if fr is not None else f"not in top {max_k}"
            hit5 = "Y" if (fr is not None and fr <= 5) else "N"
            gold_txt = ", ".join(r["gold_doi_canonical"])
            A(f"| {r['item_id']} | `{gold_txt}` | {rank_txt} | {hit5} |")
        A("")
        A(f"> {s5['note']}\n")

    A("---\n")
    A("Machine-readable form of everything above: `analysis_d3_full.json`.\n")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")


# ==================================================================================
# main
# ==================================================================================

def main():
    ap = argparse.ArgumentParser(
        description="Regenerate and verify the five D3 quantities from the frozen artefacts.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--retrieval", action="store_true",
                   help="Explicitly include the Hit@k stage (this is the default).")
    g.add_argument("--skip-retrieval", action="store_true",
                   help="Produce stages 1-4 only; do not load the index.")
    args = ap.parse_args()
    run_retrieval = not args.skip_retrieval

    try:
        cells, item_ids = load_cells()
        key, kj, an, common = load_raters()

        s1 = stage1_correctness(cells)
        s2 = stage2_mcnemar(cells)
        s3 = stage3_interannotator(kj, an, common)
        s4 = stage4_judge_outliers(key, kj, an, common)
        s5 = None
        if run_retrieval:
            print("Loading the clean index (read-only) for stage 5 — first call warms the "
                  "embedding model, this takes a moment...", flush=True)
            s5 = stage5_retrieval()
    except AnalysisError as e:
        print("\n" + "!" * 78)
        print("!!  STRUCTURAL ASSERTION FAILED — the frozen inputs are not what this")
        print("!!  script expects. Nothing was written. Investigate before proceeding.")
        print("!" * 78)
        print(f"\n  {e}\n")
        sys.exit(2)

    checks = build_checks(s1, s2, s3, s5)

    out = OrderedDict()
    out["meta"] = {
        "script": "analyse_d3.py",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "scope": "all 12 items, both subject models, 120 cells, NO exclusion list",
        "inputs": {
            "results": RESULTS_JSONL.name,
            "eval_set": EVAL_SET.name,
            "judge_key": JUDGE_KEY.name,
            "rater_1": RATER_KJ.name,
            "rater_2": RATER_AN.name,
        },
        "n_items": len(item_ids),
        "item_ids": item_ids,
        "n_cells": len(cells),
        "correct_rule": "record['failure_type'] or 'correct'; abstention and no_answer "
                        "count as not correct",
        "wilson_z": WILSON_Z,
        "mcnemar": "exact two-sided binomial on discordant pairs; chi-square (continuity "
                   "corrected) reported for comparability only",
        "pairing_key": "(item_id, model_tag)",
        "retrieval_stage_run": run_retrieval,
        "read_only": "no generation, judge or NLI call; index opened read-only",
    }
    out["per_condition_correctness"] = s1
    out["mcnemar"] = s2
    out["inter_annotator"] = s3
    out["judge_outliers"] = s4
    if s5 is not None:
        out["retrieval"] = s5
    out["verification"] = checks

    all_pass = print_verification(checks, run_retrieval)
    out["meta"]["verification_passed"] = all_pass
    out["meta"]["n_checks"] = len(checks)
    out["meta"]["n_checks_passed"] = sum(1 for c in checks if c["pass"])

    OUT_JS.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(out, checks, all_pass, run_retrieval)
    print(f"\nWrote {OUT_MD.name} and {OUT_JS.name}")

    if not all_pass:
        print_failure_report(checks)
        sys.exit(1)


if __name__ == "__main__":
    main()
