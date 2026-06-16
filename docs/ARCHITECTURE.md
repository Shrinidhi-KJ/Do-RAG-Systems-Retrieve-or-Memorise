# ARCHITECTURE — conceptual overview

A study-level map of the pipeline, written to be *spoken from*, not read line by line.
For commands and gotchas see [PROJECT.md](PROJECT.md); for findings see [../README.md](../README.md).

---

## 1. The research question and the design

When a retrieval-augmented generation (RAG) system answers a scientific question correctly,
**is it correct because it retrieved and read the right evidence, or because the language model
already memorised the answer during pre-training?** A standard RAG benchmark cannot tell these
apart — a correct answer looks identical either way. This study separates them by holding the
**question and the model fixed** and varying only the **documents the model is shown**, across
five conditions: **A** (no documents — pure parametric memory), **B1** (the retriever's real
output — standard RAG), **B2** (an *oracle* that returns only chunks of the known ground-truth
paper), **C** (real but topically *irrelevant* documents), and **D** (a fluent *contradictory*
passage asserting the opposite of the truth). Each answer is then labelled by a diagnostic
taxonomy (abstained / correct / and, when wrong, *why*). The domain is ~510 open-access papers on
the environmental effects of offshore wind farms; ground-truth questions are derived from the
**Eklipse** EU synthesis report, so every question has known supporting papers.

---

## 2. The seven core scripts and their roles

| Script | Role in the pipeline | Key functions |
|---|---|---|
| **`rag_pipeline.py`** | Builds the evidence base: loads the PDF corpus, cleans it, chunks it (1000/200), embeds with BGE-small, and stores it in ChromaDB. It is also the canonical *retriever* every condition reuses, so retrieval is identical across the experiment. | `load_pdfs`, `chunk_documents`, `create_vector_store`, `load_existing_vector_store` |
| **`llm_generation.py`** | The single gateway to the language model (Groq Llama-3.1-8B): one lazy, temperature-0, rate-limit-aware client that backs *every* generation and every LLM-judge. Centralising it keeps the subject model and judges consistent and the token budget controllable. | `get_client`, `build_prompt`, `generate_answer`, `complete` |
| **`conditions.py`** | Defines the five experimental conditions as functions — each takes a question and returns an answer plus the exact context it was shown. This is where the independent variable (what documents the model sees) is actually manipulated, using the pipeline's exact retriever. | `retrieve`, `condition_A`, `condition_B1`, `condition_B2`, `condition_C`, `condition_D` |
| **`classifier.py`** | The diagnostic decomposition — the analytical heart of the study. Given an answer and the ground-truth claim, it assigns one outcome label (correct, abstention, or a *condition-aware* failure type) via a short chain of LLM-as-judge sub-judgments. | `classify`, `judge_abstained`, `judge_correct`, `judge_grounded`, `judge_retrieval_hit` |
| **`build_contradictions.py`** | The one-time, offline builder of Condition D's counterfactual documents. For each question it sources an oracle passage, checks provenance, rewrites it into a fluent contradiction, and *verifies* the contradiction — then freezes the result so D is reproducible and human-auditable. | `get_oracle_chunks`, `check_provenance`, `make_counterfactual`, `verify_contradiction` |
| **`run_experiment.py`** | The orchestrator: iterates every item × condition × model, calls the right condition, classifies the answer, and appends one line per cell to an append-only log. It is idempotent and resumable — re-running skips completed cells, which matters under daily token caps. | `run_one_cell`, `cell_key`, `load_done_keys`, `append_result`, `cmd_export` |
| **`analyse_results.py`** | Turns the raw result log into the dissertation's tables: per-condition rates with Wilson 95% confidence intervals, and the RQ1/RQ2 breakdowns. It also applies the `EXCLUDE` list that drops flagged items from the sensitive comparisons. | `by_condition`, `rate`, `wilson`, `print_rq1`, `print_rq2` |

*(A small utility, `inspect_contradictions.py`, dumps the Condition-D cache for human review; it is
a review aid, not part of the seven-stage pipeline.)*

---

## 3. The journey of one question

A single Eklipse-derived item — `{question, claim_text, matched_dois, citations}` — moves through
the system like this:

1. **Eval set.** It begins as one record in `pilot_eval_set.json`, carrying its ground-truth claim
   and the DOI(s) of the paper(s) that support it (built upstream in `setup/`).
2. **Condition construction.** `run_experiment.py` (`run_one_cell`) hands the question to each of
   the five condition functions in `conditions.py`. A/B1/C/D run live; **D** instead loads its
   *pre-frozen* contradictory passage from `contradictions_cache.json` (built earlier by
   `build_contradictions.py`). Each condition decides what context the model will see — nothing,
   retrieved chunks, oracle chunks, irrelevant chunks, or the counterfactual.
3. **Generation.** Every condition calls the same `generate_answer` in `llm_generation.py`, so only
   the context differs. The condition returns the answer *and* the exact `context_docs` shown.
4. **Classification.** That result goes straight into `classify` (`classifier.py`), which runs the
   judge chain — abstained? correct? and if wrong, grounded in the context? was the right info even
   present? — and stamps a `failure_type`.
5. **Results.** The labelled cell is appended to `results_cache.jsonl`, exported to `results.csv`,
   and aggregated by `analyse_results.py` into the cross-condition tables. One question thus
   produces five labelled cells whose *pattern across conditions* is the actual finding.

---

## 4. Key design decisions and their reasoning

**B1 and B2 are split to remove retrieval quality as a confound.** B1 is the real retriever's
output (standard RAG, with its real Hit@5 ≈ 43%); B2 is an *oracle* that retrieves only from the
known-correct paper. Comparing them separates two very different failure modes that a single RAG
number conflates: *the retriever fetched the wrong paper* (a B1-vs-B2 gap) versus *the model was
given the right paper and still failed to use it* (a B2 failure). If retrieval quality were the
bottleneck, oracle B2 should clearly beat B1 — a hypothesis the split makes directly testable.

**Condition D's contradictions are constructed offline, gated, and judge-verified.** For each
question, `get_oracle_chunks` pulls the supporting passage from the ground-truth paper (queried by
the *clean* `claim_text`, not the noisy question). Two safeguards then apply. (i) A **provenance
gate** (`check_provenance`) uses an LLM-as-judge to confirm the matched paper is actually *about the
same subject* as the claim — this catches wrong-DOI errors in the eval set (e.g. a tern claim
matched to a gull paper) **without** falsely flagging a correct paper merely because its exact
sentence wasn't in the top-k chunks. It is **few-shot calibrated on the pilot's boundary cases** and
defaults to MATCH when unsure, so it errs toward keeping genuine items. Items that fail the gate are
recorded as `provenance_mismatch` and dropped from the sensitive comparisons. (ii) After a stronger
editor model rewrites the passage into a fluent opposite claim (`make_counterfactual`), a second
judge (`verify_contradiction`) confirms it *genuinely* contradicts the claim; failures are flagged
`verified=false` for human review. The whole set is then **frozen to a cache** — so D is identical
on every run and can be inspected before it is trusted, rather than regenerated unpredictably at
runtime.

**Memorisation is defined operationally, by behaviour across conditions — not by inspecting
weights.** Because the model and question are held fixed and only the documents vary, "the model is
leaning on parametric memory" is read off the *pattern*: A ≈ B1 with oracle B2 no better (retrieval
isn't doing the work); answering correctly in C despite irrelevant context; or overriding the false
document in D. Conversely, "it followed the context" shows up as grounded-but-wrong answers in C and
D. This is the only definition available without white-box access, and the five-condition design is
what makes it measurable.

**Classification is condition-aware, because the same wrong answer means different things in
different conditions.** "Retrieval failure" is only meaningful where the context was *supposed* to
help (B1/B2); in C the context is irrelevant by design and in D it is contradictory by design, so a
wrong answer there is about *grounding behaviour*, not retrieval. `classify` therefore branches on
the condition and short-circuits the judge calls — checking grounding/retrieval only where they
carry meaning — which keeps the taxonomy honest and the token cost down.

**Results are provisional because the pilot questions are auto-generated.** The 67 pilot questions
are derived directly from Eklipse claims and tend to *embed their own answer*, which inflates
accuracy in **every** condition. The defensible claim is therefore the **cross-condition pattern,
not the absolute percentages**. The supervisor's curated questions are pending and will replace the
pilot set without changing the design; the experiment is built to swap them in. (The single model,
Llama 3.1 8B, and the planned model-size comparison are the other reasons the numbers are not yet
final.)
