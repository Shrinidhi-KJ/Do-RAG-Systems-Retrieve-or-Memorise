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
> **Current results: [`analysis_d3_full.md`](../analysis_d3_full.md)**, regenerated
> from the frozen artefacts and verified against every published figure by
> [`analyse_d3.py`](../analyse_d3.py) (34/34 checks pass). See also
> `../project_reference.md` (what the system actually does) and
> `../discrepancies.md` (every known inconsistency).
>
> The old content is retained below unchanged, for provenance. Nothing has been deleted.

# Project walkthrough — how it was built and where it stands

A study guide tells the project's story in the order it was
actually built, file by file, with the real numbers from the repo. Companion to
[ARCHITECTURE.md](ARCHITECTURE.md) (conceptual map) and [PROJECT.md](PROJECT.md) (how to run it).

---

## Intro

> I'm testing whether a RAG system answers scientific questions because it actually *reads the
> documents it retrieves*, or because the language model already *memorised* the answer in
> pre-training. A normal RAG benchmark can't tell these apart — a correct answer looks identical
> either way. So I built a controlled experiment: I hold the question and the model fixed and change
> *only the documents the model sees*, across five conditions. It runs on a corpus of ~510
> offshore-wind environmental-science papers, with ground-truth questions taken from the Eklipse EU
> synthesis report. I've run a 67-question pilot on one model; the early pattern says the system
> leans heavily on memory — but the numbers are provisional because the pilot questions are
> auto-generated.

---

## The shape of the project: two layers

- **Layer 1 — Corpus building** (`setup/`): a one-time job to create the evidence base and the
  ground-truth questions. "Getting the data."
- **Layer 2 — The experiment** (`core/`): the science — index the corpus, measure retrieval, run
  the five conditions, classify every answer, aggregate results.

---

## Phase 0 — The research question (the "why")

The core problem is a **confound**: when RAG answers correctly, you can't tell if retrieval did the
work or if the model already knew. The whole design exists to break that confound by varying the
documents while holding the question and model constant. The five conditions:

| Condition | What the model sees | What a correct answer there means |
|---|---|---|
| **A** | Nothing | Knew it from memory (no retrieval at all) |
| **B1** | Whatever the real retriever returns (standard RAG) | Real end-to-end RAG behaviour |
| **B2** | Only chunks from the *known correct* paper (oracle) | RAG with retrieval *quality* removed as a confound |
| **C** | Real chunks about an *unrelated* topic | Still correct → using memory, not the context |
| **D** | A fluent passage asserting the *opposite* of the truth | Follows it → reading context; overrides it → memory wins |

---

## Phase 1 — Building the corpus (`setup/`, run once)

### Step 1 — `doi_discovery_dualmode_clean_fixed_queryloader.py` — find candidate papers
Searches **OpenAlex, Scopus, and Web of Science** with Boolean topic queries about offshore-wind
environmental effects, and collects a deduplicated list of **DOIs**, normalising/canonicalising each
one. **Output:** DOI lists (`dois_*.txt`, `doi_sources*.txt`). Found ~1,700 candidates.

### Step 2 — `download_with_progress.py` + `doi_download_only.py` — download the PDFs
`doi_download_only.py` is the download engine: for each DOI it tries **Unpaywall, OpenAlex, Elsevier,
and an HTML fallback**. `download_with_progress.py` is the progress-bar wrapper you run.
**Output:** `PDFs/`. Filename quirk: PDFs are named by DOI with only the first `/` mapped to `_`
(e.g. `10.1016_j.apenergy.2024.124437.pdf`).

### Step 3 — `02_download_extra_sources.py` — second-pass recovery
For DOIs that failed round one, tries **CORE, Semantic Scholar, and arXiv**; auto-skips papers
already downloaded. This is why the final corpus is larger than a single-pass download.

### Step 4 — `01_clean_fake_pdfs.py` — remove junk
Many "PDFs" are actually **HTML paywall pages saved with a `.pdf` extension**. Reads the first bytes
of each file and deletes non-PDFs (real PDFs start with `%PDF`; HTML with `<!doctype`/`<html>`). Runs
*after* downloading — the `01` prefix is misleading, so be ready to explain the ordering.

### Step 5 — `03_enrich_metadata.py` — attach metadata
For every DOI, queries **OpenAlex** for title, authors, **publication year**, venue, citation count,
abstract, topics. **Output:** `paper_metadata.json` (metadata for **1,715** DOIs). Year is the
important field — it's what would let you later test "does the model memorise *older* papers more?"

### Step 6 — `04_build_pilot_eval_set.py` — manufacture ground-truth questions
The **Eklipse report** is a 157-page EU synthesis full of cited claims like *"X has Y effect on Z
(Smith et al., 2020)."* This script: (1) extracts the text, (2) regex-finds **sentences with inline
citations** (i.e. factual claims), (3) resolves citations to **DOIs in the corpus**, (4) builds
`{question, claim_text, citations, matched_dois}` records. **Output:** `pilot_eval_set.json` —
**67 items**. This is the source of the biggest caveat: the auto-generated question often re-states
the claim, so it half-contains its own answer. Real example:

- **claim_text:** *"Pollock et al. (2024) illustrated significant avoidance close to the turbines from 0 to 140m."*
- **question:** *"According to the scientific literature: research illustrated significant avoidance close to the turbines from 0 to 140m?"*
- **matched_dois:** `10.1007/s00227-024-04542-y`

The question almost *is* the answer — the pilot limitation in one screenshot.

---

## Phase 2 — Building & measuring the RAG system (`core/`)

### Step 7 — `rag_pipeline.py` — build the searchable index
Loads every PDF, cleans the text, splits each paper into overlapping **chunks (1000 chars,
200 overlap)**, embeds each with the **BGE-small** model, stores them in **ChromaDB**.
**Output:** `chroma_db/` — **45,830 chunks from ~510 papers** (~45 min CPU). Also provides the
*retriever* reused everywhere, so retrieval is identical across conditions.
Functions: `load_pdfs`, `chunk_documents`, `create_vector_store`, `load_existing_vector_store`.

### Step 8 — `05_evaluate_retrieval.py` — is retrieval even any good?
For each of the 67 questions, retrieve top-k chunks and check whether the *known correct paper* shows
up. **Output:** `retrieval_evaluation.json`. Actual numbers:

| Metric | k=1 | k=3 | k=5 | k=10 |
|---|---|---|---|---|
| **Hit@k** | 27% | 40% | **43%** | 52% |

**Retrieval recall is modest (Hit@5 ≈ 43%)** — the right paper is in the top 5 less than half the
time. A finding in itself, and it explains why oracle context (B2) later matters.

---

## Phase 3 — The experiment engine (`core/`)

### Step 9 — `llm_generation.py` — the single door to the model
One centralised wrapper around **Groq Llama-3.1-8B** (temperature 0, rate-limit back-off). Every
answer and every judge goes through it, keeping the subject model and judges consistent and the token
budget in one place. Functions: `build_prompt`, `generate_answer`, `complete`.

### Step 10 — `conditions.py` — the five conditions, as code
Each condition is a function returning the answer **plus the exact context shown**. Details worth
knowing: **B2** filters retrieval to only the ground-truth DOI(s) and records
`oracle_available: false` if the paper isn't indexed (an absence that is itself data); **C** retrieves
on a deliberately off-topic query and *excludes* the ground-truth paper so the answer can't leak in;
**D** is handed a frozen counterfactual. Functions: `condition_A/B1/B2/C/D`, `retrieve`.

### Step 11 — `build_contradictions.py` — manufacture Condition D, carefully
Per item: (1) pull the oracle passage from the true paper (`get_oracle_chunks`); (2) **provenance
gate** (`check_provenance`) — an LLM-judge confirms the matched paper is *actually about the same
subject* as the claim, catching wrong-DOI eval-set errors without falsely flagging correct papers;
(3) **rewrite** into a fluent opposite claim (`make_counterfactual`); (4) **verify** it genuinely
contradicts (`verify_contradiction`). **Frozen to `contradictions_cache.json`** so D is reproducible
and reviewable. Actual cache: **67 items, 65 oracle-sourced, 2 flagged `provenance_mismatch`, all 67
verified.** Example (item 0): true "significant *avoidance* 0–140m" → "significant *attraction*…
strong affinity for the area immediately surrounding the turbines."

### Step 12 — `classifier.py` — the diagnostic taxonomy (analytical heart)
For each answer + claim, assigns one outcome via a chain of LLM-judges (`classify`): **abstained?** →
**correct?** → if wrong, **grounded in context?** and **was the right info present?** Crucially
**condition-aware**: "retrieval failure" only makes sense in B1/B2; in C/D a wrong answer is about
*grounding behaviour*, not retrieval. Labels: `correct`, `abstention`, `parametric_error` (A),
`retrieval_failure` (B1/B2), `grounded_but_wrong` (followed bad context), `ungrounded_hallucination`
(ignored context, fabricated).

### Step 13 — `run_experiment.py` — the orchestrator
Loops **every item × condition × model**, calls the right condition, classifies, appends one line per
cell to `results_cache.jsonl`. **Idempotent and resumable** — re-running skips finished cells, which
matters under Groq's daily token caps (hit the cap → clean exit → re-run next day).
**Output:** **335 cells (67 × 5 × 1 model)** → `results.csv`. Functions: `run_one_cell`, `cell_key`,
`cmd_export`.

### Step 14 — `analyse_results.py` — the results tables
Aggregates the 335 cells into per-condition rates with **Wilson 95% confidence intervals** plus
RQ1/RQ2 breakdowns. Applies the **`EXCLUDE` list `[2, 34, 45]`** (2 and 45 = provenance mismatches;
34 = non-assertional), reporting results both with and without them.
Functions: `by_condition`, `rate`, `wilson`, `print_rq1`.

*(`inspect_contradictions.py` dumps the D cache for human review — a helper, not a pipeline stage.)*

---

## Phase 4 — Where it stands now: the results

A complete pilot: **67 questions × 5 conditions × 1 model (Llama 3.1 8B) = 335 classified answers.**
Headline pattern:

- **A ≈ B1 ≥ B2** (≈69% / 67% / 60%). No-documents and standard RAG are statistically
  indistinguishable, and *oracle* retrieval is **no better** — slightly worse. If retrieval were
  doing the work, B2 should dominate A. It doesn't. → The model answers largely **from memory**.
- **Condition C: mostly resists** — ~69% abstain, only ~21% answer anyway. Given off-topic context,
  it usually declines rather than reciting memory.
- **Condition D: the headline split** — shown a fluent lie, ~31% **follow the false document**,
  ~22% **override it** with the truth, ~38% **hallucinate** a third wrong answer. Memory-leaning but
  still manipulable by confident wrong context.

Across all 335 cells, `failure_type` tallies: **161 correct, 107 abstentions, 35 ungrounded
hallucinations, 22 grounded-but-wrong, 6 retrieval failures, 4 parametric errors.**

---

## The honest caveats 

1. **Results are provisional** — pilot questions are auto-generated from Eklipse claims and tend to
   *embed their own answer*, inflating accuracy in every condition. The claim is the cross-condition
   *pattern*, not the absolute percentages. Curated questions are pending and swap in without design
   changes.
2. **Single model so far** (Llama 3.1 8B). Planned model-size comparison (e.g. 70B) tests the key
   open question: do larger models memorise *more*?
3. **Modest retrieval (Hit@5 ≈ 43%)** is a real limitation that partly explains why oracle B2 helps
   less than expected.
4. **The eval set will likely shrink** — dropping non-assertional or wrongly-matched items per
   supervisor feedback.

---

## Likely questions — and your answers

- **"Why split B1 and B2?"** → To separate *the retriever fetched the wrong paper* (a B1-vs-B2 gap)
  from *the model had the right paper and still failed*. If retrieval were the bottleneck, oracle B2
  would beat B1. It doesn't.
- **"How do you know the contradictions are real contradictions?"** → Two gates: a provenance check
  that the matched paper is on-subject, then an LLM-judge that verifies the rewrite genuinely
  contradicts the claim. All 67 passed; 2 were flagged as eval-set DOI mismatches and excluded.
- **"Isn't using an LLM to judge LLM outputs circular?"** → The judges make narrow one-word
  factual-consistency calls (not open-ended grading), are few-shot calibrated on boundary cases, and
  an NLI model is a drop-in alternative. (A validation step you can add.)
- **"What's your operational definition of memorisation?"** → Behavioural, not weight-inspection:
  A ≈ B1 with oracle no better, correct answers under irrelevant context (C), and overriding false
  context (D). The only definition available without white-box model access.
