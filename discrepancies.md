# Discrepancies and numbers provenance

Read-only audit, 29 July 2026. Adversarial by design: the job here is to find what an
examiner could correct you on.

**Preliminary, and it matters for how you read section 6.** There is **no dissertation
manuscript anywhere in this repo** — not in `data_pipeline/`, not in `Proposal & Ethics/`
(which holds `research_proposal.docx`, the *proposal*, plus ethics paperwork), not in
`supervisor/`. So "where the code and your dissertation disagree" is **not determinable
from the repo**. What follows compares the code against the in-repo prose that a reader
would take as the project's description: `methodology_capture.md`, `README.md`,
`docs/*.md`, the audit/validation reports, and the code's own docstrings and comments.
**You must separately check every item below against your actual dissertation text.**

Severity key: **HIGH** = an examiner could correct you on a headline claim ·
**MEDIUM** = a real inconsistency that undermines confidence · **LOW** = cosmetic drift.

---

# 6. Discrepancy hunt

## 6.A The documentation set describes a different study — HIGH

The repo's four "front door" documents all describe the **superseded 67-item pilot** with
**different headline numbers**. Anyone handed this repo — a supervisor, a second marker,
an examiner who asks to see the code — reads these first.

### A1. `README.md` states results that contradict every current number — **HIGH**

| README claim | line | What the frozen D3 data says |
|---|---|---|
| "67 questions, one model (Llama 3.1 8B)" | `README.md:60` | 12 items, **two** models, 120 cells |
| "A, **69%**" | `README.md:66` | A = 8/24 = **33.3%** |
| "B1, **67%**" | `README.md:66` | B1 = 22/24 = **91.7%** |
| "*oracle* retrieval (B2, **60%**) is no better - slightly lower, in fact" | `README.md:66-68` | B2 = 24/24 = **100%**, i.e. **higher** than B1 |
| "**A ≈ B1 ≥ B2** … the central signal that the model is largely answering **from memory**" | `README.md:66-68` | **The reverse.** A (33%) ≪ B1 (92%) ≤ B2 (100%). McNemar A vs B1 p = 0.0001. Retrieval clearly helps. |
| "C … **69% abstain**; only **21%** answer correctly" | `README.md:69-71` | C = 83.3% abstain, 16.7% correct |
| "D … ~31% follow the false document, ~22% override it, ~38% hallucinate" | `README.md:72-75` | D = **100% follow it** (24/24 grounded_but_wrong), 0% override, **0% hallucinate** |
| "Retrieval recall … (Hit@5 ≈ 43%)" | `README.md:80` | Hit@5 = **0.667** on the clean index |
| "~510 open-access papers" | `README.md:31` | 501 papers indexed |

**This is the single most dangerous artefact in the repo.** The README's central
conclusion ("A ≈ B1 ≥ B2 ⇒ answering from memory") is the *opposite* of what the current
run shows. It is unmarked as superseded and dated 2026-06-17.

### A2. `docs/CUE_CARD.md` is a briefing card with the wrong numbers — **HIGH**

`CUE_CARD.md:22-27` gives you a script to say out loud: "**A ≈ B1 ≥ B2** (69 / 67 / 60%)…
**C: ~69% abstain** … **D split: ~31% follow the lie, ~22% override it, ~38% hallucinate**",
plus "Corpus: ~510 papers, **45,830 chunks**", "Eval set: **67 ground-truth items**",
"Retrieval: **Hit@5 ≈ 43%**", "**335 cells**". Every one of these is now wrong. Do not open
this file before the meeting.

### A3. `docs/PROJECT.md` and `docs/WALKTHROUGH.md` — **HIGH**

- `PROJECT.md:94` — "`chroma_db/` Vector index — 45,830 chunks from 510 papers". The live
  index is `chroma_db_clean/` with 34,502 chunks from 501 papers.
- `PROJECT.md:98` — "335 cells (67 × 5 conditions × 1 model)". Now 120 (12 × 5 × 2).
- `PROJECT.md:102` — "Hit@k … (Hit@5 ≈ 43%)".
- `PROJECT.md:141` — "`run_experiment.py` uses 8B for both the [subject and judge]". False
  since the 70B subject was added (`run_experiment.py:87-90`).
- `PROJECT.md:34` — instructs `python core\rag_pipeline.py --rebuild`. **`--rebuild` is a
  dead flag**: parsed at `core/rag_pipeline.py:375`, never referenced anywhere in `main()`.
  Running that command rebuilds the *frozen* `chroma_db/` regardless of the flag.
- `WALKTHROUGH.md:96,106,149,164-170` — the same stale corpus size, the same Hit@k table
  (27/40/43/52%), the same pilot headline. `WALKTHROUGH.md:149` also names functions
  `run_one_cell` and `cell_key` which **no longer exist** in `run_experiment.py` (replaced
  by `prepare_cell`, `cell_signature`, `run_prepared`, `human_key`).
- `ARCHITECTURE.md:29` describes `rag_pipeline.py` as the thing that "chunks it (1000/200),
  embeds with BGE-small, and stores it in ChromaDB" and as "the canonical *retriever* every
  condition reuses". Only the *retriever* half is still true — the indexing half was
  replaced by `core/clean_index/` and `rag_pipeline.py`'s own indexer writes the frozen
  collection.

**Recommended defence:** say plainly at the meeting that `README.md` and `docs/` document
the superseded pilot and were not updated after the D3 re-run, and that
`methodology_capture.md`, `analysis_d3.md` and the `*_d3` artefacts are authoritative.
Saying it first is much better than being shown it.

---

## 6.B `methodology_capture.md` is stale on status, not on substance — MEDIUM

The file is dated "Last updated: 10 July 2026" (`:5`) and its own rule is "Only DONE items
are safe to lift verbatim" (`:3`). Two sections are still marked as not-done although the
work was completed 8–19 days later:

| Claim | line | Reality |
|---|---|---|
| "**Judging and validation. STATUS: PLANNED / IN PROGRESS. Do not write in the past tense yet.** … These validations are not yet run." | `methodology_capture.md:67-69` | **Both were run.** Human validation: `judge_validation_d3.json` (2026-07-18), two independent raters, all 120 cells. NLI cross-check: `nli_grounding_d3.json` (2026-07-11). |
| "**Statistics. STATUS: PLANNED.** … will be reported with Wilson … McNemar …" | `methodology_capture.md:73-75` | Reported in `analysis_d3.md` on 2026-07-10, i.e. **before** this file's own last-updated date. |

Also inside that file:

- `:21` — "1,732 deduplicated DOIs … 514 open-access PDFs were obtained". **The 1,732 figure
  is not derivable from any script or artefact in the repo** (no file records it) — not
  determinable from the repo. The 514 figure conflicts with `owf_clean_v1_MANIFEST.md`'s
  "PDFs on disk considered: 523" and today's 523 `.pdf` files. Neither is wrong exactly —
  514 presumably predates the D3 source rescue that added 9 papers — but the two numbers are
  never reconciled anywhere.
- `:43` — "Distances are L2 on normalised vectors, which is order-equivalent to cosine
  similarity (the write-up should describe it as such rather than as cosine)." Correct in
  substance, but note the metric is **never explicitly configured**: neither sqlite file has
  a `collection_metadata` row, so this relies on ChromaDB's *default*. If a future ChromaDB
  changes its default, the index silently changes meaning.
- `:35` — "DOIs with more than one slash were stored in a mangled form (the second slash
  rendered as an underscore)". Understated: **every** slash after the first becomes an
  underscore, not just the second (`canonicalise_doi`, `conditions.py:107-108`), and the
  filename rule also destroys parentheses and case (`build_index.py:49`), which the
  canonicaliser does **not** reverse. `project_log.md:24` records 10 such DOIs.
- `:51` — describes popularity as "a well-established versus long-tail distinction". This is
  a *concept*, not a rule. See 6.F.

---

## 6.C `analyse_results.py` is pilot-era and mis-reports the D3 data — HIGH

This is the script most likely to be opened during a demo, and it produces defensible-looking
but wrong output on `results_d3.csv`. All five verified by running it read-only during this
audit.

### D1 — the exclusion list silently drops a valid D3 item — **HIGH**

`analyse_results.py:50`:
```python
EXCLUDE = {2, 34, 45}
```
These are **pilot** item indices (the 67-item set). Applied to D3, `item_idx 34` and `45`
don't exist, but **`item_idx 2` does — it is D3-03**, a perfectly valid item whose Condition
D entry is oracle-sourced, provenance-supported and verified
(`contradictions_cache_d3.json`, entry `"2"`).

Actual output: `Condition D - CONFLICT resolution (filtered; excludes [2, 34, 45]) …
grounded_but_wrong: 100.0% (22/22)`.

Your published headline is **0/24** (`analysis_d3.md:13`), which is right. But the script in
your repo prints **22** as the denominator. If an examiner runs it, the numbers won't match
your thesis.

### D2 — hard-coded "67" printed over a 12-item run — **HIGH**

`analyse_results.py:98`: `"TABLE 1 - Outcome distribution by condition (all 67 items, unfiltered)"`
and `:159`: `"Condition D - same metrics UNFILTERED (all 67), for transparency"`. Both print
verbatim over a 12-item, 24-cell-per-condition run. `:30` in the docstring likewise says
"honest for n=67".

### D3 — no model split; 8b and 70b are silently pooled — **HIGH**

`by_condition()` (`:84-88`) groups by `condition` only. Every table therefore reports n=24
per condition without ever stating that this is 12 items × 2 models. **RQ3 (model size) is
not answerable from this script at all.** The per-model numbers in `analysis_d3.md:9-13`
came from the ad-hoc analysis, not from here.

### D4 — the "paired" B1-vs-B2 comparison discards half the data — **HIGH (genuine bug)**

`analyse_results.py:182-188`:
```python
b1 = {r["item_idx"]: r["failure_type"] for r in bycond["B1"]}
b2 = {r["item_idx"]: r["failure_type"] for r in bycond["B2"]}
both = set(b1) & set(b2)
```
The dict is keyed on `item_idx` **only**. With two models in the file, the second row for
each item overwrites the first. Verified: 24 B1 rows collapse to 12 keys, and the surviving
`model_tag` is **`70b` for all 12** (the 8b rows are silently discarded). The printed
`Paired (n=12): correct in B1 only = 0, correct in B2 only = 1` is a **70b-only** result
labelled as if it were the whole dataset.

### D5 — the exclusion is described as covering B2 but is applied only to D — **MEDIUM**

Docstring `:22-23`: "EXCLUDE list: items that are non-assertional or provenance-mismatched,
so their ground truth can't support **D / B2** scoring." Runtime banner `:235`: "excluded
items for **D/B2** scoring". But `exclude_items=EXCLUDE` is passed **only** in
`print_rq1()`'s three D calls (`:150, :152, :155`). Every B2 rate — `:138` in RQ1 and `:172`
in the B1/B2 contrast — is computed with no exclusion at all. *This is exactly the class of
thing the brief asked me to look for: an exclusion applied to one condition but described
as applying to two.*

### D6 — a stale caveat that is now false, printed on every run — **MEDIUM**

`analyse_results.py:236-237` prints: *"NOTE: absolute levels are provisional (**pilot
questions embed the claim**)."* The whole point of the D3 rewrite was that questions are
"phrased so as not to disclose its answer" (`methodology_capture.md:49`). The script tells
the reader the opposite about the current data. (Whether the D3 questions *fully* achieve
that is itself arguable — see 6.G.)

### D7 — `analyse_results.py:4` "turns results.csv" and `:224` defaults to `results.csv` — LOW

The default CSV is the frozen **pilot**. Running `python analyse_results.py` with no
arguments analyses the superseded study without saying so.

---

## 6.D Code comments that describe behaviour the code does not implement — MEDIUM

### D8 — `build_contradictions.py` says 70B; the code uses 8B — **MEDIUM**

Docstring `:9-10`: *"Uses a **STRONGER editor model (Llama 3.3 70B)** to rewrite that
passage…"*. Code `:65`: `EDITOR_MODEL = "llama-3.1-8b-instant"`.

The *comment block* immediately above (`:59-64`) explains the 8B choice honestly and at
length, so the file contradicts itself within six lines. `run_config_d3.json:18` correctly
records `"contradiction_builder": "llama-3.1-8b-instant"`. **The consequence to own:** the
counterfactual builder, the provenance checker, the contradiction verifier, the correctness
judge *and* the 8B subject model are **all the same model**. That is a much narrower
independence claim than "a stronger editor model" implies.

### D9 — `build_contradictions.py` docstring names the wrong eval set and count — **LOW**

`:6` "For each question in **pilot_eval_set.json**"; `:12` "Caches everything to
**contradictions_cache.json**"; `:63` "enough to build **all 67** in one pass". The defaults
are `d3_eval_set.json` (`:47`) and `contradictions_cache.json` (`:55`) — so `:12` is
accidentally right about the *default* but the run used `RAG_CONTRADICTIONS_CACHE=
contradictions_cache_d3.json`. Note also `run_experiment.py:60` defaults `CONTRADICTIONS`
to the **pilot** filename while `EVAL_SET` (`:53`) defaults to the **D3** file — so running
`python run_experiment.py` with no env vars pairs the D3 eval set with the *pilot's*
contradictions cache, which is index-misaligned. The D3 run avoided this only because the
env var was set.

### D10 — "Four OUP sources are affected" is wrong by a factor of ~17 — **MEDIUM**

`conditions.py:99-101`:
> "*Four OUP sources are affected; single-slash DOIs are stored unchanged.*"

Measured directly from `owf_clean_v1`: **68 of 501** stored DOIs carry an underscore after
the first slash. **15** are OUP `10.1093/icesjms/*`. A further ~35 are genuinely mangled
multi-slash DOIs from IOP (`10.1088/1742-6596/…`), EDP (`10.1051/…`), Metz (`10.1127/…`),
ASCE (`10.1061/(ASCE)…`) and others. The remaining ~18 are Springer book chapters whose
*true* DOI legitimately contains an underscore.

The canonicalisation **rule** is correct and general; only the comment's count is wrong. But
the ASCE-style DOIs (`10.1061/_asce_hy.1943-7900.0001443`) are mangled in a way
`canonicalise_doi` **cannot** reverse (parentheses and case are gone), which
`project_log.md:24` independently confirms for 10 DOIs. None of the 12 eval-set gold DOIs
are affected.

### D11 — "four-condition study" throughout a five-condition system — **LOW but repeated**

`conditions.py:4`, `llm_generation.py:4`, `classifier.py` header, `README.md:3`,
`ARCHITECTURE.md`. `llm_generation.py:9-12` enumerates only A, B, C, D — B2 is missing from
the list of what the module backs, even though it is the condition that produced your 100%.
`methodology_capture.md:91` correctly records "Four conditions became five".

### D12 — `classifier.py:25` "an NLI model is a drop-in alternative" — **LOW**

It is not a drop-in. `nli_grounding_d3.py` scores **only** grounding and contradiction, on
context conditions only, with a different definition (entailment ≥ 0.5), and explicitly
disclaims equivalence (`nli_grounding_d3.py:24-26`). It cannot produce the abstention or
correctness judgments at all. `nli_explained.md` says the same.

### D13 — dead `--rebuild` flag — **LOW**

`core/rag_pipeline.py:375` parses `--rebuild`; nothing in `main()` ever reads `args.rebuild`.
`PROJECT.md:34` and `rag_pipeline.py:443` both tell the user to run it.

---

## 6.E Internal inconsistencies in the D3 reports themselves — MEDIUM

### D14 — `analysis_d3.md` says four McNemar tests, shows six — **MEDIUM**

`analysis_d3.md:43` (and `analysis_d3.json:211`): *"**Four** McNemar tests are reported (A vs
B1 and B1 vs B2, each pooled and per model, plus per-model splits)"*. The table at `:26-33`
has **six** rows. The sentence also double-counts ("each pooled and per model, **plus
per-model splits**"). Since the immediately following claim is that "p-values are
uncorrected for multiple comparisons", the wrong count is exactly the kind of thing a
statistically-minded examiner will pick at.

### D15 — `judge_validation_aneesha.md:12-13` says human-vs-human "is not yet done" — **LOW**

It was done the same day (`interannotator_kj_aneesha.md`, 2026-07-18 20:25). The Aneesha
report was written at 17:25 and never updated. It even instructs the reader "Do not cite the
numbers below as inter-annotator agreement" — correct advice, stale framing.

### D16 — `judge_validation_d3.{md,json}` is not what its name implies — **MEDIUM**

`score_judge_validation.py:39-40` hard-codes the output paths, so `--sheet` selects the input
but **not** the output. Running the scorer for Aneesha then for KJ overwrote the first
result. The surviving `judge_validation_d3.json` (2026-07-18 20:22) contains the **KJ** run
— confirmed by matching its confusion matrix to `judge_validation_kj.md:57-61`. The two
per-rater `.md` files are hand-transcribed and contain sections (marginals, degenerate-marginal
flags, disagreement lists) the scorer never emits, so they are **not** reproducible by
re-running it.

### D17 — NLI section 5 is permanently stale — **MEDIUM**

`nli_grounding_d3.md:69`: *"Skipped: human_grounded column not filled in
human_label_sheet_d3.csv."* The NLI script ran 2026-07-11; the human labels arrived
2026-07-17/18. Both rater CSVs *do* carry `human_grounded` on **72** cells
(`interannotator_kj_aneesha.md:36`). The three-way NLI-vs-judge-vs-human grounding
comparison — arguably the strongest validation available — **was never computed**, and the
report says so in a way that reads like a limitation of the data rather than of the timing.
(`nli_grounding_d3.py:324-351` would run it correctly if pointed at a rater CSV.)

### D18 — `project_log.md:23` says "96 cells scored" for NLI; the report says 25 / 75 — **LOW**

96 is the number of non-A cells fed to NLI (`nli_grounding_d3.py:185`, 120 − 24). The
headline agreement is over **25** (`nli_grounding_d3.md:11`) and the threshold sweep over
**75** (`:59`). The log line is right but reads as if 96 cells back the 0.80 figure.

---

## 6.F The popularity slice rests on a tag with no rule — HIGH (already self-documented)

`popularity_audit.md` (your own read-only audit, 2026-07-13) establishes, and I independently
re-confirmed from `d3_eval_set.json`:

- `popularity` exists only as a hand-written constant in `d3_eval_set.json`; **no code
  computes it and no script writes that file**.
- The one objective proxy that exists (`citation_count` in `paper_metadata.json`) does **not**
  track it: the most-cited paper in the set (Maar 2009, 163 cites) is tagged `low`; a `high`
  item (Berges 2024) has the fewest citations of all 12 (5).
- **Decisive:** `10.1016/j.marenvres.2017.01.009` (Van Hal 2017) is the source for **three**
  items with **two different** popularity tags — D3-04 = `high`, D3-12 = `low`, D3-16 = `low`.
  Same paper, same citation count, different label.

`analysis_d3.md:57-82` nonetheless reports a full popularity slice, and its most quotable
line is "A pooled by popularity high 3/4, low 0/14". With **2 high items and 3 medium items
across 12**, and a tag that provably isn't a function of any recorded input, that slice
cannot bear weight. Say so before you're asked.

---

## 6.G Design facts the code makes awkward — things a sharp examiner will find

These are not documentation errors; they are properties of the implementation that your
write-up should state explicitly.

### D19 — Condition C's distractor pick is degenerate, and one context is on-topic — **HIGH**

Mechanism: `random.seed(item_idx)` then `random.choice(DISTRACTOR_QUERIES)` over a 10-item
list (`conditions.py:257-259`, seeded at `run_experiment.py:173`).

Measured from `results_d3.jsonl`: only **6 distinct distractor queries** across 12 items.
Items 3/4/8 (D3-04, D3-05, D3-10) share byte-identical distractor contexts; so do items
5/6/10 (D3-07, D3-08, D3-12); so do items 9/11 (D3-11, D3-16). **The 24 C cells therefore
span 6 contexts, not 12.**

The only anti-collision mechanism is the item's own gold-DOI exclusion
(`conditions.py:260`). There is **no topic-level guard whatsoever** — no distance floor
between distractor query and question, no tag exclusion, no check that the retrieved chunks
fail to support the claim. And it shows: **D3-11** asks about fish biomass in closed OWF
areas and drew the distractor *"commercial fish stock displacement by wind farm exclusion
zones"* — the same subject — retrieving chunks from `10.1007/s10750-014-1997-z` (**D3-10's**
gold paper) and `10.1093/icesjms_fsac107` (**D3-09's** gold paper). D3-11 (8b) is one of the
four cells counted as "correct despite irrelevant context". Another item's gold paper is not
excluded by construction.

### D20 — Condition D receives the "use ONLY the documents" instruction — **MEDIUM**

`llm_generation.py:57-62` is used byte-identically for B1, B2, C **and** D. So D = 0/24
measures *instruction-following under conflict*, not unprompted credulity. The code itself
flags this as the knob to vary (`llm_generation.py:54-56`) and `methodology_capture.md:80`
notes D's 1-document-vs-5 asymmetry — but neither states the instruction confound.

### D21 — B1 = 92% while gold-paper Hit@5 = 0.667 — **MEDIUM**

Cross-tabulated during this audit: of the four items whose gold paper is **not** in the top 5
(D3-03, D3-08, D3-11, D3-12), B1 was judged **correct on three of them, for both models**.
Only D3-12/8b became a `retrieval_failure`. `retrieval_recall_d3.md:84-93` addresses this
honestly. The defensible reading — supported by inspecting the answers — is that **other
papers in the corpus assert the same finding**, so gold-DOI Hit@k *understates* context
adequacy. But it also means **Hit@k and B1 correctness measure different things, and the
92% is not evidence that the retriever found the right paper.**

### D22 — The 8B judge is measurably more lenient than either human — **MEDIUM**

`judge_outlier_cells.md` (a): on **6 cells both humans agreed and only the judge dissented**;
**4 of the 6 cross the correct/not-correct boundary and all 4 run the same way — humans say
not-correct, judge says `correct`.** Recomputed from the two rater CSVs during this audit:

| condition | judge (published) | KJ labels | Aneesha labels |
|---|---|---|---|
| A correct | 8/24 (33.3%) | 6/24 (25.0%) | 7/24 (29.2%) |
| B1 correct | 22/24 (91.7%) | 20/24 (83.3%) | 20/24 (83.3%) |
| B2 correct | 24/24 (100%) | 24/24 (100%) | 23/24 (95.8%) |
| C correct | 4/24 (16.7%) | 3/24 (12.5%) | **2/24 (8.3%)** |
| D correct | 0/24 (0%) | 0/24 (0%) | 0/24 (0%) |

**The cross-condition pattern is invariant across all three raters, and D = 0/24 is
invariant.** But every absolute level moves down under human labels, and **C nearly halves**
— two of the four "correct under irrelevant context" cells (D3-01/8b, D3-12/8b) were called
*abstention* by both humans. Quote the pattern, not the levels.

### D23 — NLI says only 79% of D answers are entailed by the false document — **MEDIUM**

`nli_grounding_d3.md:19`: entailed-by-false-doc = **0.7917** (19/24), while the judge called
**24/24** `grounded_but_wrong`. Five D cells (D3-01/8b, D3-02/70b, D3-03/8b, D3-09/8b,
D3-16/70b) fall below the 0.5 entailment cut. The *contradicts-gold* rate is **1.0** across
all 24 and flat across thresholds 0.5/0.7/0.9.

So the two halves of "grounded_but_wrong" have different support: **"wrong" is 100%
corroborated by an independent model family; "grounded" is 79%.** State it that way.

### D24 — D3-03's counterfactual copies its source — **LOW**

`COUNTERFACTUAL_SYSTEM` says "do not merely copy the source" (`build_contradictions.py:136`).
Entry `"2"` of `contradictions_cache_d3.json` reproduces two sentences of the oracle chunk
verbatim, including the real study identifier "Courseulles-sur-mer offshore wind farm", and
flips only the verb (`increased` → `decreased`). It is functionally valid but not an
independently written passage. `project_log.md:16` records that this entry was regenerated.

### D25 — `d3_eval_set.json` carries an unused `counterfactual` field — **MEDIUM**

Every item has a `counterfactual` string (e.g. D3-01: *"The temporary closure had no effect
on lobster abundance or size…"*). **Condition D does not use it.** D loads from
`contradictions_cache_d3.json`, built by the 8B editor
(`run_experiment.py:176`, `conditions.py:322-333`). A reader of the eval set would
reasonably assume the stored counterfactual is what gets injected. Worse, the two differ in
kind: the stored field for D3-01 is a *null* counterfactual ("no effect"), while the injected
one is a *directional reversal* ("significant decline"). Nothing in the repo explains the
field's purpose or why it is unused.

### D26 — Three of twelve items share one source paper — **MEDIUM**

D3-04, D3-12 and D3-16 all cite `10.1016/j.marenvres.2017.01.009`. So the 12 "independent"
items rest on **10 distinct papers**, and B2's 24/24 includes six cells oracled to the same
document. This compounds 6.F: the same paper carries both a `high` and a `low` popularity tag.

### D27 — D3-03's source-paper choice has no recorded justification — **MEDIUM**

Your own `d3_03_provenance.md` (2026-07-21) establishes that the pairing of D3-03 to
`10.1016/j.ecolind.2018.07.014` originates in automated `(surname, year)` matching in
`setup/04_build_pilot_eval_set.py:269-296`, that the Eklipse reference-list DOI for
"Raoux et al. 2018" (`10.1016/j.marpol.2017.12.007`) is **absent from the corpus entirely**,
and that **no justification for the choice exists anywhere** — unlike the documented
Kotta→Maar swap for D3-02 (`owf_clean_v1_MANIFEST.md:76`).

### D28 — Eval-set id gaps are unexplained in the eval set itself — **LOW**

The 12 items are D3-01..05, 07..12, 16. D3-06, D3-13, D3-14, D3-15 are absent.
`owf_clean_v1_MANIFEST.md` still records papers rescued specifically "to feed D3-13 / D3-14 /
D3-15". `methodology_capture.md:51` explains that 4 of 15 candidates were dropped and 2 added
— but the mapping from that account to the surviving id set is not recorded anywhere.

### D29 — Corpus completed to guarantee retrievability — **MEDIUM (already disclosed)**

`owf_clean_v1_MANIFEST.md` "D3 source rescue" records that 9 gold papers were appended to the
index specifically because they were missing. `methodology_capture.md:33-37` discloses this
honestly. Note the direct consequence for your denominators: `retrieval_recall_d3.md:42-44`
reports Hit@k "over a single denominator of 12" precisely *because* every gold paper was
added. Hit@5 = 0.667 is therefore recall **within a corpus curated to contain the answers**.

### D30 — Statistical independence of the pooled McNemar — **MEDIUM**

The pooled A-vs-B1 test treats 24 paired observations as independent, but they are 12 items
each measured under two models. The two models' errors on the same item are correlated
(they agree on 10/12 items in Condition A). The pooled p = 0.0001 is therefore
anti-conservative. The per-model tests (p = 0.0078 and p = 0.0312) do not have this problem
and both survive; lead with those.

---

# 7. Numbers provenance

Column key: **Reproducible?** = can you regenerate this number *today* by running something
in this repo against the frozen cache.

| Headline figure | Value confirmed | Derives from | Script | Reproducible? |
|---|---|---|---|---|
| **A = 33%** | 8/24 = 33.3% ✓ | `results_d3.jsonl` / `.csv` | `core/analyse_results.py` (prints 33.3% [18.0, 53.3]) | **YES** |
| **B1 = 92%** | 22/24 = 91.7% ✓ | same | same | **YES** |
| **B2 = 100%** | 24/24 = 100% ✓ | same | same | **YES** |
| **C = 17%** | 4/24 = 16.7% ✓ | same | same | **YES** |
| **D = 0/24** | 0 correct, 24/24 `grounded_but_wrong` ✓ | same | `analysis_d3.md:13` | **PARTLY — see below** |
| **Per-model splits** (A 3/12 vs 5/12; C 4/12 vs 0/12) | ✓ recomputed | `results_d3.jsonl` | **none** — `analyse_results.py` pools models | **NO script** (trivially recomputable by hand) |
| **McNemar A vs B1, p = 0.0001** (8b 0.0078, 70b 0.0312) | ✓ recomputed by hand | `results_d3.jsonl` | **none — no `mcnemar` anywhere in any `.py`** | **NO** |
| **McNemar B1 vs B2, p = 0.5** (per model 1.0) | ✓ recomputed by hand | `results_d3.jsonl` | **none** | **NO** |
| **Wilson intervals** | ✓ | `results_d3.csv` | `analyse_results.py:58-67` | **YES** (note z=1.96 here vs 1.95996 in `analysis_d3.json:16`) |
| **Hit@5 = 0.67** | 8/12 = 0.667 ✓ | `owf_clean_v1` + `d3_eval_set.json` | **none** — `retrieval_recall_d3.md` documents the path but no runner exists; `setup/05_evaluate_retrieval.py` points at the *frozen* index and *pilot* set and does no DOI canonicalisation | **NO** |
| **Hit@10 = 0.92** | 11/12 = 0.917 ✓ | same | same | **NO** |
| **Judge-vs-human kappa** (six-way 0.884 / binary 0.883, KJ) | ✓ in `judge_validation_d3.json` | `KJ_full_labels_d3_20260718.csv` + `human_label_key_d3.json` | `score_judge_validation.py` | **YES** — but it **overwrites** `judge_validation_d3.*` (D16) |
| **Aneesha-vs-judge** (six-way 0.8725 / binary 0.8996) | ✓ in `judge_validation_aneesha.md` | `AneeshaGunaratne_full_labels_d3_20260717.csv` + key | `score_judge_validation.py --sheet …` | **YES** — but rerunning destroys the KJ output |
| **Inter-annotator kappa** (six-way 0.9369 / binary 0.9492) | ✓ in `interannotator_kj_aneesha.md` | both rater CSVs | **none** — "computed inline" (`interannotator_kj_aneesha.md:6-9`) | **NO** |
| **NLI vs judge = 0.80 / kappa 0.2331** | ✓ | `results_d3.jsonl` | `nli_grounding_d3.py` | **YES** (CPU, deterministic, revision-pinned `b3546ea…`) |
| **NLI D contradicts-gold 1.0 / entailed-by-false 0.79** | ✓ | same | same | **YES** |
| **34,502 chunks / 501 papers** | ✓ verified directly in sqlite | `chroma_db_clean/chroma.sqlite3` | `owf_clean_v1_MANIFEST.md` | **YES** (queryable) |
| **1,732 deduplicated DOIs** | — | claimed at `methodology_capture.md:21` | **none** — no artefact records it | **NO — not determinable from the repo** |
| **514 open-access PDFs** | conflicts with 523 on disk / 523 in manifest | `methodology_capture.md:21` | — | **Inconsistent; not traceable** |
| **Popularity slice** ("A high 3/4, low 0/14") | ✓ arithmetically | hand-written `tags.popularity` | **none — the tag has no rule** (`popularity_audit.md` §6) | **Arithmetic yes; the axis is not reproducible** |

### The D = 0/24 caveat

The value is correct and is the **most robust number in the study** — invariant across the
judge, both human raters, and the NLI cross-check on the "contradicts gold" half (1.0). Two
qualifications:

1. `analyse_results.py` as committed prints **22/22**, not 24/24, because of the stale
   `EXCLUDE` set (D1). Your published 24/24 is right; the script disagrees with it.
2. NLI corroborates the "wrong" half at 100% but the "grounded" half at only **79%** (D23).

### Summary of what cannot be reproduced from this repo

Five reported quantities have **no producing script**:

1. every **McNemar** p-value and chi-square (`analysis_d3.md:26-33`)
2. the **per-model** correctness splits (`analysis_d3.md:9-13`)
3. **Hit@5 / Hit@10** on the clean index (`retrieval_recall_d3.md:50-53`)
4. **inter-annotator** kappa/PABAK (`interannotator_kj_aneesha.md:24-26`)
5. the **judge-outlier** cross-tabulation (`judge_outlier_cells.md`)

All five are arithmetically correct — I recomputed 1, 2 and the D-cell tabulations by hand
during this audit and they check out exactly. But if an examiner asks "show me the script
that produced your p-values", there isn't one. The honest answer is that these were computed
read-only over `results_d3.jsonl` in an analysis session and written straight to markdown;
the input is frozen and the arithmetic is checkable by hand, but the analysis code was not
committed. If you have time before the demo, **writing a single `analyse_d3.py` that
regenerates all five from `results_d3.jsonl` is the highest-value hour you could spend** —
it converts your five weakest provenance answers into one strong one.
