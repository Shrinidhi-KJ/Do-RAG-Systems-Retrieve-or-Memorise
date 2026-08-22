# Code shortlist and side effects

Read-only audit, 29 July 2026. Companion to `code_walkthrough.md` (sections 1–4).

---

# 5. The shortlist — six files

Chosen by **what carries the study's claims**, not by size. If a file's behaviour changing
would change a number you report or a sentence you defend, it is on this list. Ranked by how
likely you are to be pushed on it.

---

## 1. `core/conditions.py` (356 lines)

**Why it is first.** Every claim in the study is a claim about what the model was shown.
This file *is* what the model was shown. A, B1, B2, C and D differ nowhere else.

**The single most important thing to know:**

> **Condition C's only protection against showing the model relevant context is excluding
> that item's own gold DOI (`:260` → `:167-168`). There is no topic-level guard of any
> kind — and it leaked.**

Say it before you are asked. The distractor is `random.choice` over a fixed 10-item list
seeded by item index (`:257-259`), which for 12 items draws only **6 distinct queries** —
items 3/4/8, 5/6/10 and 9/11 got byte-identical distractor contexts. And D3-11 (fish biomass
in closed OWF areas) drew *"commercial fish stock displacement by wind farm exclusion
zones"*, retrieving **D3-09's and D3-10's gold papers**, because the exclusion only removes
*this* item's gold. D3-11/8b is one of the four cells counted as "correct under irrelevant
context". The defensible framing: **C ≈ 17% is an upper bound on memorisation-under-noise,
not a measurement of it.**

Also have ready: B2's mechanism is a ChromaDB metadata `where` filter applied *inside* the
vector search (`:291-293`), not a post-hoc drop, and it does not go through `retrieve()` at
all. Verified zero leakage across all 24 B2 cells.

---

## 2. `core/classifier.py` (170 lines)

**Why.** Every number in every table is a judge output. If the judge is wrong, everything is.

**The single most important thing to know:**

> **Parsing is `v.strip().upper().startswith(TOKEN)` (`:75, 81, 87, 93`) with no
> out-of-vocabulary detection, no retry, and the raw judge string is never stored.**

Anything not starting with the positive token silently becomes the negative class:
`"The answer is CORRECT"` parses as **INCORRECT**. Mitigated only by `max_tokens=5`. Because
the raw string is discarded, you **cannot audit how many malformed replies occurred** — the
honest answer is "unknowable after the fact". The failure direction is at least conservative
(a malformed reply scores an answer wrong, not right).

Second thing, because it is the most common follow-up: **`grounded` is left `null`, never
`false`, on abstentions, correct answers and all of Condition A** — those paths return
before `:135`. It is populated on **25 of 120** cells. Every grounding statistic, including
the NLI agreement of 0.80, is over that 25.

---

## 3. `core/run_experiment.py` (434 lines)

**Why.** It is the entry point, and it is where your reproducibility claim lives.

**The single most important thing to know:**

> **The content-addressed cache key (`content_hash`, `:122-144`) hashes the exact prompt
> text, the ordered context ids, the real model name, k, temperature, seed and a
> condition-specific extra — so a changed input produces a new key and regenerates rather
> than silently reusing a stale answer.**

That is the strongest engineering claim in the project and it is genuinely implemented.
Pair it with the honesty note the code writes into the artefact itself (`:261-268` →
`run_config_d3.json:53`): greedy at temperature 0 is **not** bit-deterministic without a
seed, and `SEED = None` (`:99`), so results are "reproducible in distribution, not
bit-identical".

The gotcha to own before an examiner finds it: **`EVAL_SET` defaults to the D3 file but
`CONTRADICTIONS` defaults to the *pilot* filename** (`:53` vs `:60`). A bare
`python run_experiment.py` pairs the D3 eval set with the pilot's contradictions cache, which
is index-misaligned. Nothing checks. The real run avoided it only because the env var was set.

---

## 4. `core/build_contradictions.py` (264 lines)

**Why.** Condition D produced your cleanest result (0/24, invariant across the judge, both
human raters and the NLI check). Everything about that result rests on how these 12 passages
were made.

**The single most important thing to know:**

> **The docstring at `:9-10` claims "a STRONGER editor model (Llama 3.3 70B)". Line 65 sets
> `EDITOR_MODEL = "llama-3.1-8b-instant"`.**

The comment block at `:59-64` explains the 8B choice honestly (free-tier token caps), so the
file contradicts itself within six lines — and `run_config_d3.json:18` records 8B correctly.
The consequence to state plainly: **the counterfactual writer, the provenance checker, the
verifier, the correctness judge and the 8b subject model are all the same model.**

Second thing: `make_counterfactual` runs at **temperature 0.4** (`:155`) — the only non-zero
temperature in the project. That is exactly why the cache is frozen and never regenerated at
runtime (`:14-20`), and why step 15 in the reproduction order is marked do-not-re-run.

---

## 5. `core/clean_index/config.py` (117 lines)

**Why.** Every retrieval parameter you will be asked to justify is in this one 117-line file,
and it is imported by *both* the indexer and the query path — which is the reason index-time
and query-time cannot drift.

**The single most important thing to know:**

> **The BGE recipe is asymmetric by design: the instruction prefix goes on **queries only**
> (`:26, :80`), passages are embedded plain (`:81`), everything normalised (`:82`).**

This is the single biggest retrieval fix over the frozen pilot index, which embedded queries
and passages identically. `:23-25` says so in the file.

Have this ready too, because it is a fair question and the answer is slightly uncomfortable:
**the distance metric is never configured.** There is no `hnsw:space` anywhere and neither
sqlite file has a `collection_metadata` row, so ChromaDB's **default L2** applies. On
unit-norm vectors that is order-equivalent to cosine — so describe it as *L2 on normalised
vectors, order-equivalent to cosine*, never as "cosine similarity". Chunking is 1000/200
**characters** (`:86-87`), not tokens.

---

## 6. `analyse_d3.py` (1088 lines)

**Why.** It is the answer to "show me the script that produced your p-values", and it is the
only thing on this list that is safe to run live.

**The single most important thing to know:**

> **It verifies rather than merely computes: 34 checks against the previously published
> values, and on any mismatch it prints the discrepancy, states which side is more likely
> correct and why, and exits non-zero — it never adjusts itself to match.**

Currently 34/34 PASS. Two supporting details worth having: pairing for McNemar is strictly on
`(item_id, model_tag)` with a runtime assertion of 12 pairs per model and 24 pooled
(`:352-377`) — precisely the defect that makes `core/analyse_results.py`'s "paired" block
wrong; and it applies **no exclusion list of any kind**, unlike the pilot script whose
`EXCLUDE = {2,34,45}` drops the valid item D3-03 and reports Condition D as 22/22.

Run it as `..\venv\Scripts\python.exe analyse_d3.py`. Stage 5 needs the venv; everything
else runs under bare Python via `--skip-retrieval`.

---

### Two that just missed, and why

- **`core/llm_generation.py`** — you should still know that the grounded system prompt
  (`:57-62`) is byte-identical across B1, B2, C **and** D, so D measures instruction-following
  under conflict rather than unprompted credulity. But that is one fact, not a file's worth.
- **`core/clean_index/tei_parser.py`** — carries the "no reference lists in the index" claim.
  Worth knowing that TEI `<back>` is never read at all, and that only **direct-child** `<p>`
  elements are collected (`:131-134`), so text in lists or nested non-`<p>` structures is
  silently dropped.

---

# 6. State and side effects

Everything in the repo that writes to disk, mutates a cache, opens a network connection, or
installs packages. Ordered by how badly it could bite during a live demonstration.

## 6.1 Package auto-installation — 8 sites

| Site | Fires when | Demo risk |
|---|---|---|
| **`core/rag_pipeline.py:57`** — `ensure_packages()` called at **module level**, outside any `if __name__` guard; shells out to `os.system(f"{sys.executable} -m pip install ...")` at `:54` | **On any import of `conditions`** — which means `run_experiment`, `build_contradictions`, and `analyse_d3.py --retrieval` all trigger it | 🔴 **HIGHEST.** This is the one you already know about, but note *how* it fires: not on running `rag_pipeline.py`, but on importing `conditions`. It probes 9 packages (`:34-43`); if any is missing under the current interpreter it pip-installs. Observed live during this audit: running `analyse_d3.py` under bare system Python printed `Installing missing packages: langchain, langchain-community, ...` and then `'C:\Users\<user>' is not recognized` — **the `os.system` call fails on the space in your home path**, so nothing was installed, but the attempt is real and the error message is alarming mid-demo. **Always launch with `..\venv\Scripts\python.exe`.** |
| `rag_pipeline.py:54` (root copy) | Same, if ever imported | 🟡 unreachable in normal use, same behaviour if reached |
| `setup/02_download_extra_sources.py:37,44` | On import (requests, tqdm) | 🟢 you will not run this |
| `setup/03_enrich_metadata.py:41,48` | On import | 🟢 |
| `setup/04_build_pilot_eval_set.py:41,48` | On import (pypdf, tqdm) | 🟢 |
| `setup/download_with_progress.py:30` | On import (tqdm) | 🟢 |

## 6.2 Network connections — 5 kinds

| What | Where | Fires when | Demo risk |
|---|---|---|---|
| **LLM API (Groq by default)** | `llm_generation.py:180` via `get_client()` `:88-100` | Every `generate_answer` and every judge call | 🔴 `run_experiment.py` and `build_contradictions.py` make live paid/rate-limited calls. **Neither is needed for the demo.** `analyse_d3.py` makes zero LLM calls |
| **HuggingFace model download** | `nli_grounding_d3.py:70` (`HfApi().model_info`), `:74-75` (`from_pretrained`) — **at module import, `:96`** | Merely importing `nli_grounding_d3.py` | 🔴 downloads ~1.6 GB. Do not open this file in a REPL during the demo |
| **HuggingFace embedding download** | `clean_index/embeddings.py:22` → `HuggingFaceBgeEmbeddings` | First `get_store()` call — so `analyse_d3.py` stage 5 | 🟡 ~130 MB, but **cached locally** after the first run. It is already cached on this machine. If the HF cache were cleared or you demoed offline, stage 5 would stall or fail |
| **GROBID at `localhost:8070`** | `grobid_client.py:39, 65` | Only the indexing scripts | 🟢 you will not run them |
| **Scopus / WoS / OpenAlex / Unpaywall / CORE / Semantic Scholar / arXiv** | `setup/doi_discovery_*.py:515,819,910,988`; `setup/doi_download_only.py`; `setup/02_*.py`; `setup/03_*.py` | Only those scripts | 🟢 |

## 6.3 Disk writes

**Frozen artefacts that a script would overwrite:**

| File written | By | When | Guard? |
|---|---|---|---|
| `contradictions_cache_d3.json` | `build_contradictions.py:173-174` via `save_cache` | **After every single item** (`:247`) | 🔴 **None.** Full rewrite, no backup, no atomic temp-file swap. A crash mid-`json.dump` truncates the frozen cache. And the writer runs at temperature 0.4, so a re-run yields *different passages* |
| `run_config_d3.json` | `run_experiment.py:274` | Unconditionally at `:393`, **before any work** | 🔴 **None.** Even a `--status`-adjacent mistake rewrites the timestamp |
| `results_d3.jsonl` | `run_experiment.py:226` | Append per completed cell | 🟡 append-only, and the content hash prevents duplicate work — but new lines would be added if any input changed |
| `human_label_sheet_d3.csv`, `human_label_key_d3.json`, `taxonomy_rubric.md` | `export_human_labels.py:195, 210, 214` | Every run | 🔴 **None.** Default args + fixed seed (`:54`) reproduce byte-identical output, so an accidental default run is recoverable — but `--n` or `--seed` silently replaces the key **both rater CSVs join against** |
| `judge_validation_d3.md` / `.json` | `score_judge_validation.py:193, 229` | Every run | 🔴 **Hard-coded paths (`:39-40`); `--sheet` does not change them.** This already happened: scoring Aneesha then KJ overwrote the first result. The surviving file is the KJ run |
| `nli_grounding_d3.md` / `.json` | `nli_grounding_d3.py:355, 416` | Every run | 🟡 hours of CPU, so an accident is slow rather than silent |
| `owf_clean_v1_MANIFEST.md`, `_papers.csv` | `build_owf_clean_v1.py:242, 249` | Every run | 🔴 full overwrite |
| `chunks_metadata.json` | `core/rag_pipeline.py:420`, `rag_pipeline.py:408` | Only `rag_pipeline.py main()` full-pipeline path | 🟡 the repo calls it "the one safe-to-lose artifact" (`PROJECT.md:125`) |

**Append-only / self-cleaning:**

- `clean_index_failures.log` and `clean_index_skiplist.txt` — appended at
  `build_index.py:72-75`. **Neither exists on disk today**, so the only record of the 7 build
  failures is the manifest.
- `owf_clean_v1_build_checkpoint.jsonl` — appended at `build_owf_clean_v1.py:162`, merged
  back at `:221-227`.
- `nli_cell_cache_d3.jsonl` — appended at `nli_grounding_d3.py:234`, then **deleted on
  success** at `:419`. Configurable via `NLI_CACHE` (`:56`).

**Writes only its own new files:** `analyse_d3.py` (`analysis_d3_full.md` / `.json`),
`build_label_app.py` (one HTML file).

**Writes nothing at all:** `conditions.py`, `classifier.py`, `llm_generation.py`,
`clean_index/config.py`, `embeddings.py`, `tei_parser.py`, `chunking.py`,
`grobid_client.py`, `validate_sample.py`, `inspect_contradictions.py`.

## 6.4 File deletion

| Site | What | Guard |
|---|---|---|
| `setup/01_clean_fake_pdfs.py:102` | `path.unlink()` on every detected fake PDF | 🟡 interactive `input("Delete N fake files? (yes/no): ")` at `:94`; aborts unless you type exactly `yes`. Writes the list to `fake_pdfs_removed.txt` **before** deleting |
| `nli_grounding_d3.py:419` | `CACHE.unlink()` — its own resume cache | 🟢 intentional cleanup, wrapped in `try/except FileNotFoundError` |

There is no other `unlink`, `os.remove`, or `shutil` call in the repo.

## 6.5 In-memory mutable state

| What | Where | Why it matters |
|---|---|---|
| **`random.seed(item_idx)` seeds the *global* `random` module** | `conditions.py:257-258` | Not a local `Random` instance. Any code drawing from `random` after a `prepare_C` call inherits that seed. In practice this is why the distractor pick is reproducible — but it is a global side effect from a function that looks pure |
| `_store` module global | `conditions.py:127`, set in `get_store()` `:130-137` | Memoised for the whole process. Changing `RAG_COLLECTION` or `RAG_DB_DIR` after the first retrieval has **no effect** |
| `_client` module global | `llm_generation.py:71`, set in `get_client()` `:88-100` | Same: changing `LLM_BASE_URL` mid-process does nothing |
| `_CFG` / `PROFILE` resolved **at import** | `conditions.py:81-90` | The retrieval profile is fixed the moment the module is imported. Setting the env var afterwards is too late |
| NLI model loaded **at import** | `nli_grounding_d3.py:96` | `MID, REV, TOK, MODEL, ID2LABEL, IDX = load_nli()` runs on import, not in `main()` |
| `classify()` returns a **shallow** copy | `classifier.py:109` (`dict(result)`) | `context_docs` and `retrieved_meta` are shared with the caller's dict; mutating one mutates both |
| `total_chunks` stamped by mutation | `chunking.py:79-81` | Documents already appended are modified in place after the loop |

## 6.6 What could realistically fire unexpectedly during a live demonstration

Ranked, with the mitigation:

1. **`ensure_packages()` pip-installing (or failing loudly) because you launched the wrong
   Python.** Observed during this audit. **Mitigation: always
   `..\venv\Scripts\python.exe analyse_d3.py`.** If you want a zero-risk demo, use
   `python analyse_d3.py --skip-retrieval` — it is stdlib-only, never imports `conditions`,
   and prints 30/30 in about a second.
2. **Opening `nli_grounding_d3.py` in a REPL or importing it to "show the NLI code"** —
   downloads and loads ~1.6 GB at import. **Mitigation: display it in an editor, never
   import it.**
3. **Running `python core/analyse_results.py` to show "the analysis".** It prints
   `Condition D ... (22/22)` and `all 67 items` over your 12-item run. **Mitigation: demo
   `analyse_d3.py`. The superseded header comment at line 1 is your cue.**
4. **Running `python core/run_experiment.py` "to show it works".** It rewrites
   `run_config_d3.json` before doing anything, and with no env vars it pairs the D3 eval set
   with the *pilot* contradictions cache. **Mitigation: `--status` is read-only and safe;
   never run it bare.**
5. **A demo machine with no network.** `analyse_d3.py --skip-retrieval` is unaffected. Stage 5
   needs no network *provided* the BGE model is in the local HF cache — it is, but that is a
   cache, not a guarantee.
6. **`chroma_db_clean/chroma.sqlite3`'s mtime changing when you run stage 5.** This is
   expected and harmless: SQLite re-dates the file whenever a connection opens. Content is
   unchanged (verified: 34,502 embeddings, 501 DOIs, identical table hash, HNSW segment files
   untouched). `analyse_d3.py` asserts the row counts before reading precisely so that mtime
   is not mistaken for evidence of a change. Worth being able to say if someone notices.
