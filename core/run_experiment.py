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
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

from conditions import (
    prepare_A, prepare_B1, prepare_B2, prepare_C, prepare_D,
    PROFILE, COLLECTION, DB_DIR,
)
from classifier import classify, JUDGE_MODEL
from build_contradictions import EDITOR_MODEL
from llm_generation import (
    build_prompt, generate_answer, resolve_provider,
    GROQ_MODEL, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS,
)

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent
# The eval set is config-driven (mirrors the A3 retrieval-profile switch). Default is
# the D3 set; the pilot set stays selectable without a code edit via the env override:
#     RAG_EVAL_SET=pilot_eval_set.json  python run_experiment.py ...
# A bare filename resolves against the repo root; an absolute path is used as-is. The
# contradictions builder reads the SAME variable, so Condition D stays index-aligned.
EVAL_SET = Path(os.environ.get("RAG_EVAL_SET", str(ROOT / "d3_eval_set.json")))
if not EVAL_SET.is_absolute():
    EVAL_SET = ROOT / EVAL_SET
# Condition D contradictions cache. Defaults to the D3 cache, matching EVAL_SET above.
# All four paths in this block name ONE study, so a run with no environment set
# reproduces the D3 re-run rather than a pilot/D3 hybrid. build_contradictions.py reads
# the SAME env var, keeping the D cache index-aligned with the run.
#     RAG_CONTRADICTIONS_CACHE=contradictions_cache.json  python run_experiment.py ...
CONTRADICTIONS = Path(os.environ.get("RAG_CONTRADICTIONS_CACHE", str(ROOT / "contradictions_cache_d3.json")))
if not CONTRADICTIONS.is_absolute():
    CONTRADICTIONS = ROOT / CONTRADICTIONS
# Results log and run-config paths, same pattern and also defaulting to D3. The frozen
# PILOT outputs (results_cache.jsonl / run_config.json) are therefore never written by a
# default run; select them explicitly to reproduce the pilot. A bare filename resolves
# against the repo root.
#     RAG_RESULTS_FILE=results_cache.jsonl  RAG_RUN_CONFIG=run_config.json  python run_experiment.py ...
CACHE = Path(os.environ.get("RAG_RESULTS_FILE", str(ROOT / "results_d3.jsonl")))
if not CACHE.is_absolute():
    CACHE = ROOT / CACHE
RUN_CONFIG = Path(os.environ.get("RAG_RUN_CONFIG", str(ROOT / "run_config_d3.json")))
if not RUN_CONFIG.is_absolute():
    RUN_CONFIG = ROOT / RUN_CONFIG

# SUBJECT models under test (the RQ3 experiment variable: model SIZE). Each cell is
# generated once per subject model, and the subject model name is part of the content
# hash (see cell_signature), so the two never collide in the cache.
#
# Role separation (only the SUBJECT varies here):
#   subject              -> these models (varied)               8b + 70b
#   judge                -> classifier.JUDGE_MODEL (pinned)     8b
#   contradiction builder-> build_contradictions.EDITOR_MODEL  8b
#
# Both live on Groq until 2026-08-16, then retired there; the same open weights are
# served by other OpenAI-compatible hosts. Swap host via LLM_BASE_URL / LLM_API_KEY
# (see llm_generation.resolve_provider) -- no change to the model call sites.
MODELS = {
    "8b":  "llama-3.1-8b-instant",     # subject (small)
    "70b": "llama-3.3-70b-versatile",  # subject (large)
}

ALL_CONDITIONS = ["A", "B1", "B2", "C", "D"]

# Determinism / generation settings. Recorded to run_config.json AND folded into the
# content hash, so a change to any of them yields a new key rather than a silent reuse.
DEFAULT_K = 5                       # retrieval depth (matches the conditions' k default)
TEMPERATURE = DEFAULT_TEMPERATURE   # 0.0 (greedy), from llm_generation
MAX_TOKENS = DEFAULT_MAX_TOKENS     # 512, from llm_generation
SEED = None                         # Groq's chat API accepts a seed; None = unset.
KEY_SCHEMA_VERSION = 2              # bump if the hashed field set below changes


# ------------------------------------------------------------------
# CONTENT-ADDRESSED CACHE KEY
# ------------------------------------------------------------------
# The old key was positional: f"{item_idx}|{condition}|{model_tag}". It ignored the
# prompt, the retrieved/injected documents, k, the distractor set, the contradiction
# text, and the REAL model name -- safe for the single-config frozen run, unsafe for the
# re-run (new corpus, new retrieval recipe, a second model), where it risks collisions
# and stale reuse. The key below hashes everything that actually determines the output.

def _context_ids(public):
    """Ordered ids of the documents actually placed in the context (empty for A)."""
    ids = []
    for m in public.get("retrieved_meta", []):
        doi = m.get("doi")
        ci = m.get("chunk_index")
        ids.append(f"{doi}#{ci}" if ci is not None else str(doi))
    return ids


def content_hash(model_name, condition, item_id, prompt_text, context_ids,
                 k, temperature, seed, extra=None):
    """
    sha256 over everything that determines a cell's output: the real model name, the
    condition, the item id, the exact prompt text sent to the subject model, the ordered
    context ids, k, the temperature, the seed, and a condition-specific extra (the D
    contradiction hash, or B2 oracle availability). Any change yields a new key.
    """
    payload = {
        "schema": KEY_SCHEMA_VERSION,
        "model": model_name,
        "condition": condition,
        "item_id": item_id,
        "prompt": prompt_text,
        "context_ids": context_ids,
        "k": k,
        "temperature": temperature,
        "seed": seed,
    }
    if extra:
        payload["extra"] = extra
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def human_key(item_idx, condition, model_tag, chash):
    """Greppable prefix. The resume decision keys on the full hash, not on this."""
    return f"{item_idx}|{condition}|{model_tag}|{chash[:8]}"


def prepare_cell(item, item_idx, condition, contradictions, k=DEFAULT_K):
    """
    Build a cell's inputs WITHOUT generating (retrieval + context assembly only), so the
    content key can be computed before any LLM call. Returns
    (public, gen_context, can_generate, extra).
    """
    question = item["question"]
    gt_dois = item.get("matched_dois", [])

    if condition == "A":
        public, gen_context = prepare_A(question)
        return public, gen_context, True, None
    if condition == "B1":
        public, gen_context = prepare_B1(question, k=k)
        return public, gen_context, True, None
    if condition == "B2":
        public, gen_context = prepare_B2(question, gt_dois, k=k)
        can = bool(public.get("oracle_available", True))
        return public, gen_context, can, {"oracle_available": can}
    if condition == "C":
        # Seed by item index so the distractor pick is reproducible per question.
        public, gen_context = prepare_C(question, k=k, gt_dois=gt_dois, seed=item_idx)
        return public, gen_context, True, None
    if condition == "D":
        entry = contradictions.get(str(item_idx))
        if not entry:
            public = {"condition": "D", "question": question,
                      "context_docs": [], "retrieved_meta": []}
            return public, None, False, {"contradiction_sha": None}
        text = entry["contradiction"]
        public, gen_context = prepare_D(question, text)
        sha = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
        return public, gen_context, True, {"contradiction_sha": sha}
    raise ValueError(f"Unknown condition {condition}")


def cell_signature(item, item_idx, condition, model_tag, model_name, contradictions):
    """Prepare a cell (no generation) and compute its content-addressed identity."""
    public, gen_context, can_generate, extra = prepare_cell(
        item, item_idx, condition, contradictions
    )
    system_prompt, user_message = build_prompt(public["question"], gen_context)
    prompt_text = f"{system_prompt}\n\n{user_message}"
    ctx_ids = _context_ids(public)
    item_id = item.get("id", f"idx{item_idx}")
    chash = content_hash(model_name, condition, item_id, prompt_text, ctx_ids,
                         DEFAULT_K, TEMPERATURE, SEED, extra)
    return {
        "public": public, "gen_context": gen_context, "can_generate": can_generate,
        "prompt_text": prompt_text, "context_ids": ctx_ids, "item_id": item_id,
        "content_hash": chash, "cell_key": human_key(item_idx, condition, model_tag, chash),
    }


def eval_item_ids(eval_set):
    """Item ids in eval-set order, using the same idx fallback as cell_signature."""
    return [it.get("id", f"idx{i}") for i, it in enumerate(eval_set)]


def check_contradictions_alignment(eval_set, contradictions):
    """
    ABORT if the Condition D cache was not built from the eval set we just loaded.

    prepare_cell looks a contradiction up by the item's POSITION in the eval set
    (contradictions.get(str(item_idx))), so a cache built from a DIFFERENT set does not
    crash -- it silently pairs each question with another item's counterfactual, and the
    D column comes out quietly wrong. The defaults make that easy to hit: EVAL_SET
    defaults to the D3 set while CONTRADICTIONS defaults to the 67-item pilot cache,
    whose keys 0-11 exist and so would be used without complaint.

    Two things must agree, or this raises SystemExit before anything is generated:
      1. the cache's keys are exactly the eval set's indices, and
      2. the question stored beside each contradiction matches the question at that
         index (catches a cache of the right SIZE built from a different set).
    """
    expected = [str(i) for i in range(len(eval_set))]
    expected_set = set(expected)
    ids = eval_item_ids(eval_set)

    missing = [k for k in expected if k not in contradictions]
    extra = [k for k in contradictions if k not in expected_set]
    mismatched = [
        k for k in expected
        if k in contradictions
        and contradictions[k].get("question") != eval_set[int(k)]["question"]
    ]

    def _preview(keys):
        shown = ", ".join(keys[:10])
        return shown + (f", ... (+{len(keys) - 10} more)" if len(keys) > 10 else "")

    problems = []
    if missing:
        problems.append(
            f"  - {len(missing)} eval item(s) have NO cache entry. indices: "
            f"{_preview(missing)}  ids: {_preview([ids[int(k)] for k in missing])}"
        )
    if extra:
        problems.append(
            f"  - {len(extra)} cache entr(ies) have no matching eval item. keys: "
            f"{_preview(sorted(extra, key=lambda k: (not k.isdigit(), k.zfill(6))))}"
        )
    if mismatched:
        lines = []
        for k in mismatched[:5]:
            lines.append(
                f"      index {k} (id {ids[int(k)]}):\n"
                f"        eval set : {eval_set[int(k)]['question'][:90]!r}\n"
                f"        cache    : {(contradictions[k].get('question') or '')[:90]!r}"
            )
        more = f"\n      ... (+{len(mismatched) - 5} more)" if len(mismatched) > 5 else ""
        problems.append(
            f"  - {len(mismatched)} cache entr(ies) sit at an index whose question differs:\n"
            + "\n".join(lines) + more
        )

    if not problems:
        return

    raise SystemExit(
        "\nFATAL: the Condition D contradictions cache does not match the eval set.\n"
        f"  eval set      : {EVAL_SET}  ({len(eval_set)} items)\n"
        f"  contradictions: {CONTRADICTIONS}  ({len(contradictions)} entries)\n"
        + "\n".join(problems)
        + "\n\nCondition D is keyed by the item's POSITION in the eval set, so continuing "
        "would\npair questions with the WRONG counterfactuals rather than fail. Nothing "
        "was generated.\nPoint both at the same set, e.g. for the D3 run:\n"
        "  RAG_EVAL_SET=d3_eval_set.json RAG_CONTRADICTIONS_CACHE=contradictions_cache_d3.json \\\n"
        "  RAG_RESULTS_FILE=results_d3.jsonl RAG_RUN_CONFIG=run_config_d3.json \\\n"
        "  python run_experiment.py\n"
        "...or build a cache for this eval set: RAG_EVAL_SET=... python build_contradictions.py"
    )


def load_done_hashes():
    """Set of content hashes already in the cache, so we never regenerate them."""
    done = set()
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # tolerate a torn final line from a hard kill
                h = rec.get("content_hash")   # old positional / header records lack this
                if h:
                    done.add(h)
    return done


def append_result(rec):
    with open(CACHE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def build_run_config(model_tags, conditions):
    """The reproducibility header: determinism settings, models, and an honesty note."""
    base_url, _ = resolve_provider()   # base URL only; never record the key value
    return {
        "record_type": "run_config",
        "created": datetime.now().isoformat(timespec="seconds"),
        "eval_set": str(EVAL_SET),
        "retrieval_profile": PROFILE,
        "collection": COLLECTION,
        "db_dir": DB_DIR,
        # Role separation: only the SUBJECT model varies; judge and D builder are pinned.
        "subject_models": {mt: MODELS[mt] for mt in model_tags},
        "roles": {
            "subject": [MODELS[mt] for mt in model_tags],
            "judge": JUDGE_MODEL,
            "contradiction_builder": EDITOR_MODEL,
        },
        "provider": {
            "base_url": base_url,
            "env_vars_read": ["LLM_BASE_URL", "LLM_API_KEY", "GROQ_API_KEY"],
            "note": "OpenAI-compatible; set LLM_BASE_URL + LLM_API_KEY to swap host.",
        },
        "subject_default_model": GROQ_MODEL,
        "conditions": list(conditions),
        "k": DEFAULT_K,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "seed": SEED,
        "key_schema_version": KEY_SCHEMA_VERSION,
        "key_fields": ["model", "condition", "item_id", "prompt", "context_ids",
                       "k", "temperature", "seed", "extra"],
        "determinism_note": (
            "Decoding is greedy (temperature 0). Greedy decoding at temperature 0 is "
            "NOT bit-deterministic without a fixed seed, and Groq does not guarantee "
            "bitwise reproducibility across calls or infrastructure. seed is currently "
            "unset (None); set SEED to request best-effort determinism where the API "
            "supports it. Report results as reproducible in distribution, not "
            "bit-identical."
        ),
    }


def write_run_config(model_tags, conditions, path=RUN_CONFIG):
    cfg = build_run_config(model_tags, conditions)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg


def run_prepared(sig, item, item_idx, condition, model_tag, model_name):
    """Generate (if the cell has an answer to produce), classify, and label the record."""
    claim_text = item["claim_text"]
    result = dict(sig["public"])
    if sig["can_generate"]:
        result["answer"] = generate_answer(
            result["question"], context=sig["gen_context"],
            model=model_name, temperature=TEMPERATURE,
        )
    else:
        result["answer"] = None   # e.g. B2 oracle unavailable, or D missing

    labelled = classify(result, claim_text)
    labelled["content_hash"] = sig["content_hash"]
    labelled["cell_key"] = sig["cell_key"]
    labelled["item_idx"] = item_idx
    labelled["item_id"] = sig["item_id"]
    labelled["model_tag"] = model_tag
    labelled["model_name"] = model_name
    labelled["k"] = DEFAULT_K
    labelled["temperature"] = TEMPERATURE
    labelled["max_tokens"] = MAX_TOKENS
    labelled["seed"] = SEED
    return labelled


def cmd_status(eval_set, conditions, model_tags):
    # Tally from the stored record fields (item_idx/model_tag/condition), counting how
    # many distinct items have at least one cached result per (model, condition). This
    # reflects what is actually in the cache without recomputing content hashes.
    seen = {}   # (model_tag, condition) -> set(item_idx)
    total_records = 0
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("record_type") == "run_config" or "content_hash" not in rec:
                    continue
                mt, cond, ii = rec.get("model_tag"), rec.get("condition"), rec.get("item_idx")
                if mt is None or cond is None:
                    continue
                seen.setdefault((mt, cond), set()).add(ii)
                total_records += 1

    n_items = len(eval_set)
    total_cells = n_items * len(conditions) * len(model_tags)
    covered = sum(len(seen.get((mt, cond), ())) for mt in model_tags for cond in conditions)
    print(f"Cached result records: {total_records}. "
          f"Items covered: {covered} / {total_cells} cells.")
    for mt in model_tags:
        for cond in conditions:
            n = len(seen.get((mt, cond), ()))
            print(f"  {mt:8s} {cond:3s}: {n}/{n_items}")


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
    print(f"Eval set       : {EVAL_SET}  ({len(eval_set)} items)")
    # Keep the UNTRUNCATED set for the alignment check below: Condition D is keyed by
    # position in the full set, so --limit must not make a matched cache look short.
    full_eval_set = eval_set
    if args.limit:
        eval_set = eval_set[: args.limit]

    if args.status:
        cmd_status(eval_set, args.conditions, args.models); return

    contradictions = {}
    if os.path.exists(CONTRADICTIONS):
        with open(CONTRADICTIONS, encoding="utf-8") as f:
            contradictions = json.load(f)
        print(f"Contradictions : {CONTRADICTIONS}  ({len(contradictions)} entries)")
        # Hard fail BEFORE any generation if this cache belongs to a different eval set.
        check_contradictions_alignment(full_eval_set, contradictions)
    elif "D" in args.conditions:
        print(f"WARNING: no contradictions cache at {CONTRADICTIONS}; "
              f"Condition D will be skipped.")

    # Record the run's determinism settings before doing anything, so the write-up can
    # state reproducibility honestly even if the session is interrupted.
    write_run_config(args.models, args.conditions)

    done = load_done_hashes()

    # First pass: prepare every cell (retrieval + prompt, NO generation) and compute its
    # content hash. This is cheap and local; only generation is rate-limited. A cell is
    # "done" only if its full content hash is already cached -- a changed input (corpus,
    # prompt, model, k, temperature, contradiction) produces a new hash and regenerates.
    sigs = []
    for mt in args.models:
        model_name = MODELS[mt]
        for i, item in enumerate(eval_set):
            for cond in args.conditions:
                sig = cell_signature(item, i, cond, mt, model_name, contradictions)
                sigs.append((sig, item, i, cond, mt, model_name))

    todo = [s for s in sigs if s[0]["content_hash"] not in done]
    print(f"{len(sigs) - len(todo)} cells already done. {len(todo)} to run this session.\n")

    completed = 0
    for sig, item, item_idx, cond, mt, model_name in todo:
        try:
            rec = run_prepared(sig, item, item_idx, cond, mt, model_name)
            append_result(rec)
            done.add(sig["content_hash"])
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
