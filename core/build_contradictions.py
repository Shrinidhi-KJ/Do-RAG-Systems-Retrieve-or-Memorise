"""
build_contradictions.py
------------------------
One-time builder for Condition D's contradictory documents.

For each question in pilot_eval_set.json it:
  1. Pulls the ground-truth chunk (oracle retrieval from matched_dois). If the
     paper isn't in the index, falls back to the claim_text itself.
  2. Uses a STRONGER editor model (Llama 3.3 70B) to rewrite that passage into a
     fluent, on-topic counterfactual that asserts the WRONG answer.
  3. Verifies the rewrite actually contradicts the original claim (LLM-as-judge).
  4. Caches everything to contradictions_cache.json, keyed by item index.

Why a separate one-time script (not generated inside Condition D at runtime):
  - REPRODUCIBILITY. D's documents are frozen once and reused on every run, so
    your four-condition results are stable and re-runnable.
  - You can MANUALLY REVIEW the cache before trusting it. Counterfactual
    generation is the part most likely to misfire (a "contradiction" that
    doesn't actually contradict, or that's incoherent). The 'verified' flag
    flags failures for you to inspect.

Design choice -- LLM-rewrite vs entity substitution:
  This uses LLM-rewrite (general: handles any claim, matches the knowledge-
  conflict / FaithEval literature). The more controlled alternative is swapping
  the specific answer entity/number; mention both in your Methodology and note
  you spot-checked the rewrites.

Run (idempotent -- safe to re-run; only fills in missing/failed items):
    python build_contradictions.py
    python build_contradictions.py --limit 5      # try a handful first
    python build_contradictions.py --regenerate    # rebuild everything
"""

import os
import json
import argparse
from pathlib import Path

from conditions import get_store
from llm_generation import complete

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent
EVAL_SET = ROOT / "pilot_eval_set.json"
CACHE_FILE = ROOT / "contradictions_cache.json"

# Model for data construction. NOTE: the 70B free tier is capped at ~100k
# tokens/day, which this script (3 calls/item) exhausts around item ~30. The 8B
# free tier allows ~500k tokens/day and ~14,400 requests/day -- enough to build
# all 67 in one pass. We use 8B so the set builds consistently in a day; the
# verify + human-validation steps cover the small quality drop versus 70B.
# (Prefer 70B quality? Set it back and run across two days -- the cache resumes.)
EDITOR_MODEL = "llama-3.1-8b-instant"

VERIFY_SYSTEM = (
    "You judge whether a passage contradicts a claim on its key fact. Reply with "
    "exactly one word: CONTRADICTS or CONSISTENT. No other text."
)


def get_oracle_chunks(store, claim_text, gt_dois, k=3):
    """
    Top-k chunks from the ground-truth paper(s), queried by the CLEAN claim_text
    rather than the awkward auto-generated question, so we surface the passage
    that actually supports the claim. Returns [] if the paper isn't indexed.
    """
    if isinstance(gt_dois, str):
        gt_dois = [gt_dois]
    if not gt_dois:
        return []
    flt = {"doi": gt_dois[0]} if len(gt_dois) == 1 else {"doi": {"$in": gt_dois}}
    docs = store.similarity_search(claim_text, k=k, filter=flt)
    return [d.page_content for d in docs]


PROVENANCE_SYSTEM = (
    "You audit whether a ground-truth paper was correctly matched to a claim. "
    "Given a claim and short passages from the matched paper, decide whether the "
    "paper is plausibly ABOUT THE SAME SUBJECT as the claim -- the same organism "
    "or group AND the same general phenomenon. Passages rarely restate the claim "
    "word-for-word and may be technical tables, fragments, or citation lists; "
    "that is fine. Answer MATCH unless the passages are clearly about a DIFFERENT "
    "organism or an UNRELATED subject. When unsure, answer MATCH.\n\n"
    "Examples:\n"
    "- Claim: sandwich tern flight height and collision risk. Passages: "
    "black-headed gull migration and a reference list. -> MISMATCH (different "
    "species and phenomenon).\n"
    "- Claim: a study showed significant avoidance near turbines. Passages: a "
    "table of avoidance rates across distance bands from the same study. -> MATCH "
    "(same phenomenon, technical wording).\n"
    "- Claim: juveniles spend more time in OWF zones than adults. Passages: time "
    "individuals spent in OWFs in the same kittiwake study, without the age split. "
    "-> MATCH (same species and phenomenon; exact comparison need not appear).\n\n"
    "Reply with exactly one word: MATCH or MISMATCH."
)


def check_provenance(claim_text, chunks):
    """
    Is the matched paper the RIGHT paper for this claim (same subject)? This
    catches wrong-DOI eval-set errors (e.g. a tern claim matched to a gull paper)
    WITHOUT flagging correct papers whose exact sentence just isn't in the top-k
    retrieved chunks. Few-shot calibrated on the pilot's boundary cases.
    """
    if not chunks:
        return False
    joined = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(chunks))
    user = f"Claim: {claim_text}\n\nPassages from the matched paper:\n{joined}\n\nMATCH or MISMATCH?"
    verdict = complete(PROVENANCE_SYSTEM, user, model=EDITOR_MODEL, temperature=0.0, max_tokens=5)
    return verdict.strip().upper().startswith("MATCH")


COUNTERFACTUAL_SYSTEM = (
    "You construct counterfactual passages for a controlled NLP evaluation. You "
    "are given a QUESTION, the TRUE CLAIM (the correct answer), and a SOURCE "
    "passage for style. Write a single self-contained passage that reads like a "
    "scientific finding but asserts the DIRECT OPPOSITE of the true claim -- flip "
    "its key fact (reverse the direction, invert the magnitude, or negate the "
    "conclusion). The passage MUST explicitly state the opposite finding in a "
    "complete sentence; do not merely copy the source, trail off, or change the "
    "subject. Keep it self-contained and roughly 3-6 sentences. Do NOT include "
    "acknowledgements, funding text, figure/table references, or citations to "
    "unrelated work. Do NOT add any disclaimer or note that it is altered. Output "
    "ONLY the passage."
)


def make_counterfactual(question, original, claim_text, model=None):
    # Lead with the claim to be negated; the source passage is for style only and
    # is truncated so a long chunk can't dominate and get parroted back.
    user = (
        f"Question: {question}\n\n"
        f"TRUE CLAIM to contradict:\n{claim_text}\n\n"
        f"Source passage (style reference only, do not copy):\n{original[:900]}\n\n"
        f"Now write the passage that asserts the OPPOSITE of the true claim."
    )
    return complete(
        COUNTERFACTUAL_SYSTEM, user,
        model=model or EDITOR_MODEL, temperature=0.4, max_tokens=600,
    )


def verify_contradiction(claim_text, counterfactual, model=None):
    user = f"Claim: {claim_text}\n\nPassage: {counterfactual}\n\nDoes the passage contradict the claim?"
    verdict = complete(VERIFY_SYSTEM, user, model=model or EDITOR_MODEL, temperature=0.0, max_tokens=5)
    return verdict.strip().upper().startswith("CONTRADICTS")


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Only process the first N items.")
    ap.add_argument("--regenerate", action="store_true", help="Rebuild every item from scratch.")
    ap.add_argument("--only_failed", action="store_true",
                    help="Rebuild ONLY items currently flagged verified=false. Keeps the rest.")
    ap.add_argument("--model", type=str, default=None,
                    help="Override editor/verifier model, e.g. llama-3.3-70b-versatile.")
    args = ap.parse_args()

    model = args.model  # None -> use EDITOR_MODEL default

    with open(EVAL_SET, encoding="utf-8") as f:
        eval_set = json.load(f)
    if args.limit:
        eval_set = eval_set[: args.limit]

    cache = {} if args.regenerate else load_cache()
    store = get_store()

    n_oracle = n_mismatch = n_not_indexed = n_verified = n_failed_verify = 0

    for idx, item in enumerate(eval_set):
        key = str(idx)
        if key in cache and not args.regenerate:
            # In only_failed mode, redo the unverified ones; otherwise skip cached.
            if not (args.only_failed and not cache[key].get("verified", False)):
                continue

        question = item["question"]
        claim_text = item["claim_text"]
        gt_dois = item.get("matched_dois", [])

        chunks = get_oracle_chunks(store, claim_text, gt_dois)
        if not chunks:
            # Ground-truth paper not in the index at all.
            source, original, supported = "not_indexed", claim_text, False
            n_not_indexed += 1
        else:
            supported = check_provenance(claim_text, chunks)
            if supported:
                source, original = "oracle", chunks[0]
                n_oracle += 1
            else:
                # Paper indexed but about a different species/phenomenon: almost
                # certainly a wrong-DOI match in the eval set. Flag for review --
                # this item's ground truth is suspect for B2 and scoring too.
                source, original = "provenance_mismatch", claim_text
                n_mismatch += 1

        counterfactual = make_counterfactual(question, original, claim_text, model=model)
        verified = verify_contradiction(claim_text, counterfactual, model=model)
        if verified:
            n_verified += 1
        else:
            n_failed_verify += 1

        cache[key] = {
            "question": question,
            "claim_text": claim_text,
            "gt_dois": gt_dois,
            "source": source,
            "provenance_supported": supported,
            # Always log what was retrieved, even when provenance fails, so the
            # mismatch flags can be audited rather than taken on trust.
            "oracle_preview": [c[:220].replace("\n", " ") for c in chunks],
            "original": original,
            "contradiction": counterfactual,
            "verified": verified,
        }
        save_cache(cache)   # incremental: a rate-limit crash never loses progress
        review = "REVIEW" if (not verified or source == "provenance_mismatch") else "ok"
        print(f"[{idx + 1}/{len(eval_set)}] {source:20s} {review}")

    print("\n" + "=" * 64)
    print(f"  Cached:                 {len(cache)} items -> {CACHE_FILE}")
    print(f"  Oracle-sourced:         {n_oracle}  (paper contains the claim)")
    print(f"  Provenance mismatch:    {n_mismatch}  (paper lacks the claim -> check eval set)")
    print(f"  Not indexed:            {n_not_indexed}  (ground-truth paper missing from corpus)")
    print(f"  Verified contradiction: {n_verified}")
    print(f"  Contradiction REVIEW:   {n_failed_verify}")
    print("=" * 64)
    print("  Investigate provenance-mismatch items: they signal claims matched to")
    print("  the wrong DOI, which would also corrupt Condition B2 and your scoring.")


if __name__ == "__main__":
    main()
