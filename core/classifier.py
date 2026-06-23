"""
classifier.py
-------------
The diagnostic failure decomposition -- the core analysis of the dissertation.

Takes one answered item (a result dict from conditions.py) plus the ground-truth
claim, and labels the outcome. The taxonomy:

    abstention            -- model declined ("not in the documents", "I don't know")
    correct               -- answer matches the ground-truth claim
    parametric_error      -- wrong, no context was given (Condition A): pure memory miss
    retrieval_failure     -- wrong in B1/B2 because the supporting info wasn't retrieved
    grounded_but_wrong    -- wrong, but the answer faithfully follows the provided
                             context (e.g. Condition D: followed the counterfactual;
                             or C: followed the irrelevant docs)
    ungrounded_hallucination -- wrong, and the answer is NOT supported by the context
                             (had context, ignored it, fabricated)

Why condition-aware: "retrieval failure" only makes sense where the context was
meant to help (B1/B2). In C the context is irrelevant by design and in D it is
contradictory by design, so a wrong answer there is about grounding behaviour,
not retrieval quality. Treating every "context lacks the answer" as a retrieval
failure would mislabel C and D.

Three sub-judgments (LLM-as-judge; an NLI model is a drop-in alternative):
    abstained      -- did the model decline?
    correct        -- does the answer match the claim?
    grounded       -- is the answer supported by the provided context?
    retrieval_hit  -- does the provided context actually contain the claim's info?
Calls are short-circuited: abstention and correctness are always checked; the
grounding/retrieval judges only run for wrong, non-abstained, context conditions.

Self-test (a handful of synthetic cases, one per label):
    python classifier.py
"""

from llm_generation import complete

JUDGE_MODEL = "llama-3.1-8b-instant"
# 8B for the judges: the full experiment is thousands of classification calls,
# far beyond the 70B free-tier daily token cap (~100k). The 8B free tier (~500k
# tokens/day, ~14,400 req/day) is the sustainable choice, and these are simple
# one-word judgments it handles well. Move to a paid tier + 70B only if the
# judges prove noisy on hard cases during validation.

_ABSTAIN_SYS = (
    "Decide whether the ANSWER declines to give a factual answer -- e.g. it says "
    "the information is not in the documents, it cannot determine it, or it does "
    "not know -- as opposed to asserting a substantive answer. Reply with exactly "
    "one word: ABSTAIN or ANSWER."
)
_CORRECT_SYS = (
    "Judge whether the ANSWER is factually consistent with the reference CLAIM on "
    "its key fact (direction, magnitude, or conclusion). Minor wording differences "
    "are fine. Reply with exactly one word: CORRECT or INCORRECT."
)
_GROUNDED_SYS = (
    "Judge whether the ANSWER is supported by (derivable from) the PASSAGES. If the "
    "answer's key assertion comes from the passages, it is GROUNDED; if it asserts "
    "things absent from the passages, it is UNGROUNDED. Reply with exactly one "
    "word: GROUNDED or UNGROUNDED."
)
_HIT_SYS = (
    "Judge whether the PASSAGES contain information that addresses the CLAIM's "
    "finding (same subject and variable). Reply with exactly one word: HIT or MISS."
)


def _join(context_docs):
    return "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(context_docs))


def judge_abstained(answer):
    v = complete(_ABSTAIN_SYS, f"Answer:\n{answer}", model=JUDGE_MODEL, temperature=0.0, max_tokens=5)
    return v.strip().upper().startswith("ABSTAIN")


def judge_correct(answer, claim_text):
    user = f"Reference claim:\n{claim_text}\n\nAnswer:\n{answer}"
    v = complete(_CORRECT_SYS, user, model=JUDGE_MODEL, temperature=0.0, max_tokens=5)
    return v.strip().upper().startswith("CORRECT")


def judge_grounded(answer, context_docs):
    user = f"Passages:\n{_join(context_docs)}\n\nAnswer:\n{answer}"
    v = complete(_GROUNDED_SYS, user, model=JUDGE_MODEL, temperature=0.0, max_tokens=5)
    return v.strip().upper().startswith("GROUNDED")


def judge_retrieval_hit(context_docs, claim_text):
    user = f"Claim:\n{claim_text}\n\nPassages:\n{_join(context_docs)}"
    v = complete(_HIT_SYS, user, model=JUDGE_MODEL, temperature=0.0, max_tokens=5)
    return v.strip().upper().startswith("HIT")


def classify(result, claim_text):
    """
    Augment a condition result dict with diagnostic labels. Expects:
        result["condition"]     -- "A" | "B1" | "B2" | "C" | "D"
        result["answer"]        -- the model's answer (may be None if unavailable)
        result["context_docs"]  -- list[str] (empty for Condition A)
    Returns the result dict with added keys: abstained, correct, grounded,
    retrieval_hit, failure_type.
    """
    condition = result["condition"]
    answer = result.get("answer")
    context = result.get("context_docs") or []

    out = dict(result)
    out.update({"abstained": None, "correct": None, "grounded": None,
                "retrieval_hit": None, "failure_type": None})

    if answer is None:
        out["failure_type"] = "no_answer"   # e.g. B2 oracle unavailable
        return out

    # Always: abstention then correctness.
    out["abstained"] = judge_abstained(answer)
    if out["abstained"]:
        out["failure_type"] = "abstention"
        return out

    out["correct"] = judge_correct(answer, claim_text)
    if out["correct"]:
        out["failure_type"] = None          # success; not a failure
        return out

    # Wrong and asserted. Decompose.
    if condition == "A":                     # no context to ground against
        out["failure_type"] = "parametric_error"
        return out

    # Context conditions: compute grounding (and retrieval_hit only where it means
    # something -- i.e. the helpful conditions B1/B2).
    out["grounded"] = judge_grounded(answer, context)
    if condition in ("B1", "B2"):
        out["retrieval_hit"] = judge_retrieval_hit(context, claim_text)
        if not out["retrieval_hit"]:
            out["failure_type"] = "retrieval_failure"
            return out

    out["failure_type"] = "grounded_but_wrong" if out["grounded"] else "ungrounded_hallucination"
    return out


def _self_test():
    """Synthetic cases, one per label, to confirm the decision logic + judges."""
    claim = "Pile-driving noise causes temporary hearing loss in harbour porpoises."
    cases = [
        # correct answer, real RAG
        {"condition": "B1", "answer": "Pile driving causes temporary hearing loss in harbour porpoises.",
         "context_docs": ["Construction pile driving produces noise causing temporary threshold shifts in harbour porpoise hearing."]},
        # abstention under irrelevant context
        {"condition": "C", "answer": "The documents do not contain information about this.",
         "context_docs": ["Marine litter accumulates around turbine foundations over time."]},
        # grounded-but-wrong: followed a counterfactual context
        {"condition": "D", "answer": "Pile driving has no measurable effect on porpoise hearing.",
         "context_docs": ["Studies found pile-driving noise has no measurable effect on harbour porpoise hearing."]},
        # parametric error: no context, wrong
        {"condition": "A", "answer": "Pile driving improves porpoise hearing sensitivity.",
         "context_docs": []},
    ]
    for c in cases:
        r = classify(c, claim)
        print(f"{r['condition']:3s} | abstain={r['abstained']} correct={r['correct']} "
              f"grounded={r['grounded']} hit={r['retrieval_hit']} -> {r['failure_type']}")


if __name__ == "__main__":
    _self_test()
