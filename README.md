> # !! SUPERSEDED -- DO NOT QUOTE THE NUMBERS BELOW !!
>
> **Everything below this banner describes the WITHDRAWN 67-item pilot study**: one
> subject model (Llama 3.1 8B), the noisy `wind_farm_papers` index, and auto-generated
> questions that restated their own answers. This file was last revised in June 2026 and
> was **not** updated after the clean re-run.
>
> **The pilot's central conclusion was REVERSED by the clean 12-item Descriptor 3 re-run.**
> The pilot reported `A ~= B1 >= B2` (69 / 67 / 60 %) and concluded that the system
> answers largely *from parametric memory*. On the clean index, with hand-verified
> questions and two subject models, the result is the opposite -- **retrieval clearly
> helps**, and A vs B1 is significant in each model separately (exact McNemar p = 0.0078
> for 8b, p = 0.031 for 70b).
>
> | | pilot (withdrawn) | clean D3 re-run (current) |
> |---|---|---|
> | A (no documents) | 69 % | **33 %** (8/24) |
> | B1 (standard RAG) | 67 % | **92 %** (22/24) |
> | B2 (oracle) | 60 % | **100 %** (24/24) |
> | C (irrelevant docs), answered correctly | 21 % | **17 %** (4/24) |
> | D (contradictory doc), followed the false doc | ~31 % | **100 %** (24/24) |
> | retrieval Hit@5 | 43 % | **0.667** |
> | corpus | 45,830 chunks / ~510 papers (`wind_farm_papers`) | **34,502 chunks / 501 papers** (`owf_clean_v1`) |
> | scale | 67 items x 5 x 1 model = 335 cells | **12 items x 5 x 2 models = 120 cells** |
>
> **Current results: [`analysis_d3_full.md`](analysis_d3_full.md)**, regenerated
> from the frozen artefacts and verified against every published figure by
> [`analyse_d3.py`](analyse_d3.py) (34/34 checks pass). See also
> `project_reference.md` (what the system actually does) and
> `discrepancies.md` (every known inconsistency).
>
> The old content is retained below unchanged, for provenance. Nothing has been deleted.

## Current study — Descriptor 3 (clean re-run)

A five-condition diagnostic separating retrieval from parametric memory. The same
question is put to the system with no documents (A), with standard retrieval (B1),
with the gold document supplied directly (B2), with deliberately irrelevant
documents (C), and with a fluent counterfactual asserting the wrong answer (D).
Run over 12 hand-verified Descriptor 3 items across two model sizes (Llama 3.1 8B
and Llama 3.3 70B): 120 labelled cells.

**Result.** Correctness rises from 33% with no documents (8/24) to 92% with standard
retrieval (22/24); the paired comparison is significant, exact McNemar p = 0.0001.
The oracle condition shows no detectable advantage over standard retrieval (24/24
vs 22/24, p = 0.5). Both models follow the counterfactual document on 24 of 24 cells.

**Reproduce.** `python analyse_d3.py --skip-retrieval` regenerates every published
figure from the frozen results and reports 30/30 checks passed. The full run,
including the retrieval stage, additionally needs the project venv.

**Where things are.** [`analysis_d3_full.md`](analysis_d3_full.md) holds the current
results; [`project_log.md`](project_log.md) is the dated work log. The Chroma index
is not in this repository — see [`owf_clean_v1_MANIFEST.md`](owf_clean_v1_MANIFEST.md)
for what it contains and how it was built.

A separate applied project (BioAgora evidence synthesis) reuses this corpus and lives
in its own repository.

# Do RAG systems retrieve, or memorise?

A four-condition diagnostic study of whether a retrieval-augmented generation (RAG)
system actually *uses the documents it retrieves* or instead falls back on the
parametric knowledge already baked into the language model, tested on a corpus of
offshore wind-farm environmental-science papers.

> **Run instructions, file reference, and gotchas live in [docs/PROJECT.md](docs/PROJECT.md).**
> This README is the *what and why*; PROJECT.md is the *how*.

---

## 1. Overview

When a RAG system answers a scientific question correctly, *why* is it correct?
Because it **retrieved and read** the right evidence, or because the underlying model
already **memorised** the answer during pre-training? A standard RAG evaluation cannot
tell these apart, a correct answer looks identical either way.

This study separates them by holding the **question and the model fixed** and varying
only the **documents the model is shown**, across five conditions:

| Condition | Documents shown | What the answer reveals |
|---|---|---|
| **A**  | None | Pure parametric memory, no retrieval at all |
| **B1** | Retrieved (standard RAG) | Real end-to-end RAG behaviour |
| **B2** | Oracle, only the known ground-truth paper | RAG with retrieval *quality* removed as a confound |
| **C**  | Irrelevant (real chunks about a *different* topic) | Answering anyway ⇒ leaning on memory, not context |
| **D**  | Contradictory (a fluent counterfactual) | Following the false doc vs overriding it from memory |

**Domain.** ~510 open-access papers on the environmental effects of offshore wind
farms, marine mammals, seabirds, fish, benthic habitats, underwater noise, and so on —
indexed as a vector database. Ground-truth questions are derived from the **Eklipse** EU
scientific-synthesis report, so every question has known supporting papers.

---

## 2. Pipeline at a glance

Two layers. **Corpus building** (run once) produces the searchable evidence base;
**the experiment** runs the five conditions over it and classifies every answer.

**Layer 1 - Corpus building** (`setup/`)
1. Discover candidate papers from OpenAlex / Scopus / Web of Science → a deduplicated DOI list.
2. Download the open-access PDFs → the `PDFs/` corpus.
3. Clean fake (HTML-as-PDF) files and enrich each paper with metadata → `paper_metadata.json`.
4. Extract cited claims from the Eklipse report and match them to corpus papers → `pilot_eval_set.json` (the ground-truth question set).

**Layer 2 - The experiment** (`core/`)
5. Embed and index the corpus into a vector database → `chroma_db/`.
6. Measure retrieval quality (does the right paper come back?) → `retrieval_evaluation.json`.
7. Build the frozen contradictory documents for Condition D → `contradictions_cache.json`.
8. Run every question × condition and classify each answer (abstained / correct / failure type) → `results_cache.jsonl`.
9. Aggregate into the results tables → `results.csv`.

---

## 3. Current findings - *provisional*

From the pilot run: **67 questions, one model (Llama 3.1 8B).** Read the
**cross-condition *pattern*, not the absolute percentages** - the pilot questions are
auto-generated from the Eklipse claims and tend to embed the answer, which inflates
accuracy in every condition. Curated questions from the supervisor are pending.

- **A ≈ B1 ≥ B2.** No-documents (A, **69%**) and standard RAG (B1, **67%**) are
  statistically indistinguishable, and *oracle* retrieval (B2, **60%**) is no better -
  slightly lower, in fact. If retrieval were doing the work, B2 should dominate A. It
  doesn't. This is the central signal that the model is largely answering **from memory**.
- **Condition C (irrelevant docs): it mostly resists.** **69% abstain** ("not in the
  documents"); only **21%** answer correctly anyway. Given clearly off-topic context the
  model usually declines rather than reciting memory.
- **Condition D (contradictory docs) - the headline split.** Shown a fluent passage
  asserting the *opposite* of the truth: **~31% follow the false document**
  (grounded-but-wrong), **~22% override it** and answer correctly from memory, and
  **~38% hallucinate** a third answer grounded in neither.

Taken together: this RAG system **leans heavily on parametric memory** (A ≈ B1, oracle
no better) yet remains **manipulable** by confidently-worded wrong context (D).
Retrieval recall is itself modest (Hit@5 ≈ 43%), which is part of why oracle context
(B2) helps less than expected.

---

## 4. Limitations & planned work

- **Single model so far.** Only Llama 3.1 8B. A frontier model (e.g. Llama 3.3 70B)
  will be added for a **model-size comparison** - the central open question is whether
  larger models memorise *more*.
- **Pilot vs curated questions.** Pilot questions embed the claim, so absolute accuracy
  is optimistic. The supervisor's curated questions will replace them; the
  cross-condition design is unchanged.
- **Eval-set revision.** The 67-item pilot set will be revised (likely shrunk) per
  supervisor feedback, dropping non-assertional or wrongly-matched items.

---

## 5. Running it

Setup, the full command sequence, data-artifact rules, gotchas, and the procedure for
swapping in curated questions are all in **[docs/PROJECT.md](docs/PROJECT.md)**.
