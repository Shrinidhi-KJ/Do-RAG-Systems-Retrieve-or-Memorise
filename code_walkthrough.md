# Code walkthrough — every Python file, as committed

Read-only audit, 29 July 2026. Nothing was run, modified or created except this file,
`code_shortlist.md`, and one line in `project_log.md`. Every claim below was checked
against the source; where a caller or a purpose could not be established it says
**not determinable from the repo** rather than guessing.

Paths are relative to `data_pipeline/` (the repo root) unless prefixed.

---

# 1. Inventory

**Status definitions.** LIVE = used by the D3 run or its analysis. SUPERSEDED = pilot-era,
still present, replaced by something else. UTILITY = one-off audit / export / build tool,
not on the result path but not obsolete. DEAD = nothing in the repo imports or calls it.

### LIVE (17 files)

| Path | Lines | Purpose | Evidence it is live |
|---|---|---|---|
| `core/run_experiment.py` | 434 | Experiment runner: item × condition × model, generate → judge → append | Produced `results_d3.jsonl` + `run_config_d3.json` (2026-07-10) |
| `core/conditions.py` | 356 | Builds the five conditions' context; owns the retriever | Imported `run_experiment.py:35-38`, `build_contradictions.py:39`, `analyse_d3.py:616` |
| `core/llm_generation.py` | 243 | Single HTTP gateway to the LLM; both system prompts | Imported `conditions.py:33`, `classifier.py:37`, `build_contradictions.py:40`, `run_experiment.py:41-44` |
| `core/classifier.py` | 170 | The 8B LLM judge; six-way failure taxonomy | Imported `run_experiment.py:39` |
| `core/build_contradictions.py` | 264 | One-time builder of Condition D's frozen counterfactuals | Produced `contradictions_cache_d3.json`; `EDITOR_MODEL` imported `run_experiment.py:40` |
| `core/rag_pipeline.py` | 447 | **Only** `load_existing_vector_store()` is live — the store loader | Imported `conditions.py:32` |
| `core/clean_index/config.py` | 117 | The `Config` dataclass: chunking, embedding, GROBID, paths | Imported `conditions.py:39/42`, `build_index.py:35`, `build_owf_clean_v1.py:37`, `validate_sample.py:28`, `__init__.py:16` |
| `core/clean_index/embeddings.py` | 28 | Single source of truth for the BGE recipe | Imported `conditions.py:40/43`, `build_index.py:109`, `build_owf_clean_v1.py:40` |
| `core/clean_index/build_index.py` | 201 | Reusable GROBID→parse→chunk→index engine + DOI↔filename mapping | Imported `build_owf_clean_v1.py:39`, `validate_sample.py:32` |
| `core/clean_index/build_owf_clean_v1.py` | 285 | **The driver that actually built `owf_clean_v1`**, with the triage policy | Produced `owf_clean_v1_MANIFEST.md` / `_papers.csv` / `_build_checkpoint.jsonl` |
| `core/clean_index/tei_parser.py` | 153 | TEI-XML → title/abstract/sections/captions under the KEEP/DROP policy | Imported `build_index.py:37`, `chunking.py:19`, `validate_sample.py:30` |
| `core/clean_index/chunking.py` | 82 | Section-bounded 1000/200 chunking into LangChain `Document`s | Imported `build_index.py:38`, `validate_sample.py:31` |
| `core/clean_index/grobid_client.py` | 81 | HTTP client for the GROBID container | Imported `build_index.py:36`, `build_owf_clean_v1.py:38`, `validate_sample.py:29` |
| `core/clean_index/__init__.py` | 18 | Package marker; re-exports `Config`, `default_config` | Makes `core.clean_index.*` importable (the path `conditions.py:39-40` tries first) |
| `analyse_d3.py` | 1088 | The five previously-unreproducible quantities + PASS/FAIL verification | Produced `analysis_d3_full.md` / `.json` (2026-07-29) |
| `score_judge_validation.py` | 234 | Human-vs-judge κ / PABAK / confusion matrix | Produced `judge_validation_d3.*`; cited in `judge_validation_kj.md:5` and `judge_validation_aneesha.md:5` |
| `nli_grounding_d3.py` | 430 | Independent-family (DeBERTa) grounding cross-check | Produced `nli_grounding_d3.md` / `.json` |

### UTILITY (5 files)

| Path | Lines | Purpose | Note |
|---|---|---|---|
| `export_human_labels.py` | 260 | Builds the blind rater sheet, the answer key and the rubric | Produced `human_label_sheet_d3.csv`, `human_label_key_d3.json`, `taxonomy_rubric.md`. Imports `analyse_results.load` (`:44`) |
| `build_label_app.py` | 632 | Emits the offline single-file HTML labelling app from sheet + rubric | Produced `label_app_d3_full.html`. Reads only blind inputs |
| `core/clean_index/validate_sample.py` | 175 | Side-by-side old-vs-new chunk comparison for eyeballing the clean rebuild | Opens the frozen sqlite with `mode=ro&immutable=1` (`:47`). Writes nothing |
| `core/inspect_contradictions.py` | 27 | Dumps the contradiction cache for manual review | **Hard-wired to the PILOT `contradictions_cache.json`** (`:15`), no env override — cannot show the D3 cache |
| `setup/03_enrich_metadata.py` | 248 | OpenAlex metadata enrichment → `paper_metadata.json` | Historical, but its output is still read live by `build_owf_clean_v1.py:44` and `popularity_audit.md` |

### SUPERSEDED (9 files)

| Path | Lines | Purpose | Evidence + what replaced it |
|---|---|---|---|
| `core/analyse_results.py` | 249* | Pilot results tables | Header comment marks it superseded. `EXCLUDE = {2,34,45}` are pilot indices; index 2 = valid D3-03, so D prints 22/22. Hard-codes "all 67 items" (`:98`). Pools 8b+70b. Replaced by `analyse_d3.py` — **except** `load()`, still imported by `export_human_labels.py:44` and `nli_grounding_d3.py:39` |
| `rag_pipeline.py` (root) | 435 | Older copy of `core/rag_pipeline.py` | `diff` shows its `load_existing_vector_store()` **lacks the `embeddings=` parameter** the clean profile requires. Nothing imports it: the only importer (`conditions.py:32`) runs with `core/` on `sys.path[0]`. Replaced by `core/rag_pipeline.py` |
| `setup/04_build_pilot_eval_set.py` | 496 | Auto-built the 67-item pilot eval set from the Eklipse PDF | Writes `pilot_eval_set.json` (`:381`), never `d3_eval_set.json`; emits no `tags` field. `popularity_audit.md:69-75` confirms no script writes the D3 set. Replaced by hand construction |
| `setup/05_evaluate_retrieval.py` | 219 | Pilot Hit@k | Defaults to the **frozen** index and **pilot** set (`:104-106`) and does raw DOI set intersection with **no canonicalisation** (`:78-84`). Produces 0.433, not 0.667. Replaced by `analyse_d3.py` stage 5 |
| `setup/doi_discovery_dualmode_clean_fixed_queryloader.py` | 1420 | DOI discovery across OpenAlex / Scopus / WoS | Ran 2026-05-27..05-29; outputs frozen. Its OpenAlex mode needs `descriptor_keywords.txt`, **which is not in the repo** |
| `setup/doi_download_only.py` | 379 | Per-DOI OA PDF resolution and download | Ran once; `PDFs/` is the frozen output |
| `setup/download_with_progress.py` | 135 | tqdm wrapper around the above (`imports at :17-24`) | Same |
| `setup/01_clean_fake_pdfs.py` | 116 | Detects and deletes HTML-saved-as-PDF files | Ran once → `fake_pdfs_removed.txt`. **Deletes files** (`:102`), gated behind an interactive `yes` (`:94`) |
| `setup/02_download_extra_sources.py` | 278 | CORE / Semantic Scholar / arXiv fallback downloader | Ran once; output folded into `PDFs/` |

\* 249 lines including the one-line superseded header added 2026-07-29; logic unchanged.

### DEAD (5 files)

| Path | Lines | Evidence for DEAD |
|---|---|---|
| `handoff_bioagora/score_judge_validation.py` | 234 | Byte-identical to the root copy (`diff` empty). Nothing imports from `handoff_bioagora/`. It is an outbound copy for the BioAgora project (`project_log.md:24`) |
| `handoff_bioagora/export_human_labels.py` | 260 | Byte-identical to the root copy. Same reasoning. Would fail if run in place: its `sys.path.insert(ROOT/"core")` resolves to `handoff_bioagora/core`, which does not exist |
| `handoff_bioagora/build_label_app.py` | 631 | Differs from the root copy by one leading blank line only. Same reasoning |
| `../supervisor/doi_download_only.py/doi_download_only.py` | 375 | Unpacked zip of the supervisor's original, kept for provenance. The adapted copy in `setup/` is the one that ran |
| `../supervisor/doi_discovery_dualmode_clean_fixed_queryloader.py/doi_discovery_dualmode_clean_fixed_queryloader.py` | 1418 | Same |

Also present and dead-by-inspection: the two `__MACOSX/._*.py` AppleDouble resource forks
under `supervisor/` (0 bytes of Python; zip extraction artefacts).

**Repo totals:** 34 Python files outside `venv/` (39 counting the `__MACOSX` stubs and the
two directories that share a `.py` name). 17 LIVE · 5 UTILITY · 9 SUPERSEDED · 5 DEAD.

---

# 2. File by file, in dependency order

## Tier 0 — leaf modules with no local imports

### `core/clean_index/config.py` (117 lines)

**What it is for.** One dataclass that defines an entire indexing run: where the PDFs are,
what collection to write, the embedding recipe, the chunk geometry, the GROBID endpoint,
and the KEEP/DROP policy. Making it a `Config` object rather than module constants is what
lets a new corpus be a new config instead of a code edit. It is imported by both the
indexer and the retrieval path, which is what stops the two drifting apart.

**Public surface.**
- `Config` (dataclass) — 16 fields; `describe() -> str` renders a human-readable summary of
  the active recipe (used at `build_index.py:101`).
- `default_config() -> Config` (`:115-117`) — the canonical OWF configuration. Returns a
  fresh `Config()` with all defaults.
- Module constants `BGE_QUERY_INSTRUCTION` (`:26`), `DEFAULT_DROP_SECTION_KEYWORDS`
  (`:31-37`), `DEFAULT_SECTION_LABEL_MAP` (`:41-63`).

**Reads / writes.** Nothing at import time. It only *names* paths.

**Called by.** `conditions.py:39` (or `:42` on the fallback import), `build_index.py:35`,
`build_owf_clean_v1.py:37`, `validate_sample.py:28`, `__init__.py:16`.
**Calls.** Nothing.

**Constants that matter.**

| Constant | file:line | Value |
|---|---|---|
| `chunk_size` / `chunk_overlap` | `:86-87` | 1000 / 200 characters |
| `embedding_model` | `:79` | `BAAI/bge-small-en-v1.5` |
| `query_instruction` | `:26,80` | `"Represent this sentence for searching relevant passages:"` |
| `embed_instruction` | `:81` | `""` — passages embedded plain |
| `normalize_embeddings` | `:82` | `True` |
| `device` | `:83` | `"cpu"` |
| `db_dir` / `collection_name` | `:75-76` | `chroma_db_clean/` / `owf_clean_v1` |
| `grobid_url` / `grobid_timeout` | `:90-91` | `http://localhost:8070` / 300 s |
| `keep_captions` | `:92` | `True` |
| `batch_size` | `:97` | 50 |
| `failure_log` / `skip_list` | `:98-99` | `clean_index_failures.log` / `clean_index_skiplist.txt` |

**Gotchas.**
- The **distance metric is never set.** There is no `hnsw:space` anywhere, so ChromaDB's
  default L2 applies. Confirmed: neither sqlite file has a `collection_metadata` row. On
  unit-norm vectors this is order-equivalent to cosine, but it depends on a library
  default, not on anything this repo states.
- `failure_log` and `skip_list` **do not exist on disk.** The only surviving record of the
  7 build failures is `owf_clean_v1_MANIFEST.md`.
- `section_label_map` uses `field(default_factory=...)` (`:94`) so each `Config` gets its
  own dict — mutating one config's map will not poison the next. `drop_section_keywords`
  is a tuple, so it is immutable by construction.

---

### `core/clean_index/embeddings.py` (28 lines)

**What it is for.** The single place the embedding object is constructed, so index time and
query time provably use the same recipe. It wraps `HuggingFaceBgeEmbeddings`, which applies
`query_instruction` on `embed_query()` and `embed_instruction` on `embed_documents()` —
exactly the asymmetric BGE recipe the model was trained for.

**Public surface.**
- `build_embeddings(config) -> HuggingFaceBgeEmbeddings` (`:20-28`). Takes a `Config`,
  returns a configured embeddings object.

**Reads / writes.** Downloads the model from the HuggingFace hub on first use, then reads
the local HF cache. Writes nothing to the repo.

**Called by.** `conditions.py:64` (via `_clean_embeddings()`), `build_index.py:110`,
`build_owf_clean_v1.py:40`.
**Calls.** `langchain_community.embeddings.HuggingFaceBgeEmbeddings`.

**Gotchas.** The correctness of the whole retrieval story rests on the class applying the
prefix to queries only. That is asserted in the docstring (`:13-14`) but **never tested**
anywhere in the repo. If a langchain version changed that behaviour, retrieval would
silently degrade with no error.

---

### `core/clean_index/grobid_client.py` (81 lines)

**What it is for.** A thin `requests` wrapper around a locally-running GROBID container.
It POSTs one PDF and returns the TEI-XML string, or raises.

**Public surface.**
- `class GrobidError(RuntimeError)` (`:27-28`).
- `GrobidClient(base_url="http://localhost:8070", timeout=300)` (`:32-34`).
- `.is_alive() -> bool` (`:36-42`) — GETs `/api/isalive`, 10 s timeout; returns False on any
  `RequestException` rather than raising.
- `.process_fulltext(pdf_path) -> str` (`:44-81`) — POSTs to `/api/processFulltextDocument`
  and returns the TEI. Raises `GrobidError` if the file is missing, the request fails, the
  status is not 200, or the body has no `<TEI`.

**Reads / writes.** Reads the PDF binary. Writes nothing. **Opens a network connection to
`localhost:8070`.**

**Called by.** `build_index.py:88`, `build_owf_clean_v1.py:38`, `validate_sample.py:29`.
**Calls.** `requests`.

**Constants that matter.** GROBID request flags (`:57-62`): `consolidateHeader=0`,
`consolidateCitations=0`, `includeRawAffiliations=0`, `segmentSentences=0` — no external
metadata lookups, so extraction is offline apart from the container itself.

**Gotchas.** `is_alive()` swallows every network error into `False`, so an unreachable
service and a broken service look identical. The 300 s timeout is per PDF; a hung container
stalls a full-corpus build for 300 s per file with no aggregate deadline.

---

### `core/clean_index/tei_parser.py` (153 lines)

**What it is for.** Turns GROBID's TEI-XML into a clean structured document under the
KEEP/DROP policy. It keeps title, abstract, body sections and figure/table captions, and
never reads TEI `<back>` at all — which is how reference lists disappear from the index.

**Public surface.**
- `Section` (dataclass: `label`, `head`, `text`) `:30-35`
- `Caption` (dataclass: `kind`, `text`) `:37-41`
- `ParsedDoc` (dataclass: `title`, `abstract`, `tei_doi`, `sections`, `captions`,
  `dropped_heads`; method `n_body_units()`) `:43-53`
- `canonical_label(head, label_map) -> str` (`:73-84`) — maps a raw heading to one of the 7
  canonical labels, stripping leading numbering with a regex (`:78`); returns `"other"` if
  unmatched.
- `is_dropped_head(head, drop_keywords) -> bool` (`:87-91`) — substring match, case-folded.
- `parse_tei(xml_str, drop_keywords, label_map) -> ParsedDoc` (`:96-153`) — the main entry.

**Reads / writes.** Pure function over a string. No I/O.

**Called by.** `build_index.py:81`, `validate_sample.py:30`.
**Calls.** `xml.etree.ElementTree` (stdlib — deliberately, so lxml is not a dependency,
`:17-18`).

**Gotchas.**
- Only **direct-child** `<p>` elements of a `<div>` are collected (`:131-134`). That is what
  prevents duplication across nested divs, but it also means text inside any other element
  (lists, quotes, nested non-`<p>` structures) is **silently dropped with no warning**.
- Table grids are deliberately not reconstructed — a table contributes its `<figDesc>`
  caption only (`:14-15`, `:146-151`). Recorded as a limitation.
- GROBID's own DOI is parsed (`:108-111`) into `tei_doi` but **never used**; the canonical
  DOI always comes from the filename. So a filename/DOI mismatch would go undetected even
  though the cross-check data is sitting right there.
- `canonical_label` falls through to a `startswith` scan (`:81-83`) over an unordered dict,
  so a heading like "Data availability statement" could in principle match `"data"` →
  `methods`. In practice the drop-list catches it first (`:128`), but the ordering is
  load-bearing and undocumented.

---

### `core/clean_index/chunking.py` (82 lines)

**What it is for.** Splits a `ParsedDoc` into LangChain `Document` chunks, splitting each
section (and the abstract, and each caption) **independently** so no chunk straddles a
section boundary. Attaches the per-chunk metadata the rest of the pipeline keys on.

**Public surface.**
- `build_documents(parsed, doi, source, config) -> List[Document]` (`:32-82`).

**Reads / writes.** Pure. No I/O.

**Called by.** `build_index.py:83`, `validate_sample.py:31`.
**Calls.** `RecursiveCharacterTextSplitter`, `langchain_core.documents.Document`.

**Constants that matter.** Splitter settings at `:22-29`: separators
`["\n\n", "\n", ". ", " ", ""]`, `length_function=len`, `is_separator_regex=False`.
Emission order at `:65-76`: abstract → body sections → captions. Metadata keys at `:52-61`.

**Gotchas.**
- `chunk_index` is a **running counter across the whole paper** (`:42`, `:63`), not per
  section — so chunk 0 is always the abstract's first piece, and the index carries no
  section information on its own.
- `total_chunks` is stamped **after** the loop (`:79-81`), so it is correct but is written
  to every `Document` by mutation.
- Empty pieces are skipped silently (`:47-49`). There is **no minimum chunk length**, so a
  one-line section becomes a chunk of its own and competes in retrieval on equal footing.
- Sizing is by **characters, not tokens**, inherited from the pilot.

---

### `core/llm_generation.py` (243 lines)

**What it is for.** The one and only place this project talks to a language model. Subject
answers, all four judge calls, the counterfactual writer and its verifier all funnel through
`complete()`, so they provably share transport, retry policy and temperature handling. It
also owns the two system prompts.

**Public surface.**
- `resolve_provider() -> (base_url, api_key)` (`:74-85`) — reads `LLM_BASE_URL` (default
  Groq) and `LLM_API_KEY` falling back to `GROQ_API_KEY`. Never returns the key to a caller
  that logs it: `run_experiment.build_run_config` takes only `base_url` (`:232`).
- `get_client() -> OpenAI` (`:88-100`) — lazily builds one module-global client; raises
  `RuntimeError` with a Windows-specific hint if no key is set.
- `build_prompt(question, context=None) -> (system_prompt, user_message)` (`:103-127`) —
  `context is None` → parametric prompt and the bare question; otherwise the grounded
  prompt and a `Documents:` block with each chunk under `[Document N]`.
- `generate_answer(question, context=None, model=GROQ_MODEL, temperature=0.0,
  max_tokens=512, max_retries=5) -> str` (`:130-154`) — builds the prompt and delegates.
- `complete(system_prompt, user_message, model=..., temperature=..., max_tokens=...,
  max_retries=5) -> str` (`:157-203`) — the single chat-completion call with backoff.
  Returns the stripped message content; raises `RuntimeError` after the retries.

**Reads / writes.** Reads env vars only. Writes nothing. **Opens an HTTPS connection to the
provider on every call.**

**Called by.** `conditions.py:33` (`generate_answer`), `classifier.py:37` (`complete`),
`build_contradictions.py:40` (`complete`), `run_experiment.py:41-44`
(`build_prompt`, `generate_answer`, `resolve_provider`, and the three constants).
**Calls.** `openai.OpenAI`.

**Constants that matter.**

| Constant | file:line | Value |
|---|---|---|
| `GROQ_MODEL` | `:35` | `llama-3.1-8b-instant` (fallback only; the runner always pins a model) |
| `GROQ_DEFAULT_BASE_URL` | `:45` | `https://api.groq.com/openai/v1` |
| `DEFAULT_TEMPERATURE` | `:49` | `0.0` |
| `DEFAULT_MAX_TOKENS` | `:50` | `512` |
| `GROUNDED_SYSTEM_PROMPT` | `:57-62` | used byte-identically for **B1, B2, C and D** |
| `PARAMETRIC_SYSTEM_PROMPT` | `:65-69` | Condition A only |

**Gotchas.**
- **Only `RateLimitError` and `APIError` are retried** (`:190-199`). Any other exception —
  a connection reset, an empty `choices` list, a JSON decode failure — propagates
  immediately and, in `run_experiment.py`, is **not** caught by the `except RuntimeError`
  handler at `:421`, so it aborts the run with a traceback rather than a clean resume.
- Backoff is `2, 4, 8, 16, 32` s and **never consults `Retry-After`**; worst case one call
  blocks for ~62 s before raising.
- `max_tokens=512` truncation is **not detected**. `finish_reason` is never inspected, so a
  cut-off answer is judged as though complete.
- The client is a module global (`:71`), built once. Changing `LLM_BASE_URL` mid-process has
  no effect.
- The grounded prompt says "use **ONLY** the information in the provided documents", and D
  gets it too — so Condition D measures instruction-following under conflict. The code
  itself flags this as the knob to vary (`:54-56`).

---

## Tier 1 — modules that build on Tier 0

### `core/rag_pipeline.py` (447 lines) — **one live function**

**What it is for.** Historically the whole pilot pipeline: load PDFs, regex-clean, chunk,
embed, index, and a retrieval-test CLI. For the D3 study **only `load_existing_vector_store`
is used**; everything else built the frozen `wind_farm_papers` collection and has been
replaced by `core/clean_index/`.

**The live function.**
- `load_existing_vector_store(db_dir="chroma_db", collection_name="wind_farm_papers",
  embedding_model="BAAI/bge-small-en-v1.5", embeddings=None) -> Chroma` (`:281-306`).
  If `embeddings` is passed it is used for the query path; if `None` it falls back to plain
  `HuggingFaceEmbeddings` with **no prefix** — the recipe the frozen collection was built
  with. `conditions.get_store()` always passes the BGE builder for the clean profile
  (`conditions.py:135-136`).

**Other public functions (not on the D3 path).** `ensure_packages()` `:33-57`,
`load_pdfs(pdf_dir)` `:74-121`, `clean_document_text(text)` `:128-148`,
`clean_documents(docs)` `:151-173`, `chunk_documents(docs, 1000, 200)` `:180-217`,
`create_vector_store(chunks, db_dir, collection_name, embedding_model)` `:224-278`,
`test_retrieval(vectorstore, queries, top_k=5)` `:313-357`, `main()` `:364-444`.

**Reads / writes.** `main()` reads `PDFs/` and writes `chunks_metadata.json` (`:420`) and
the Chroma collection. `load_existing_vector_store` reads the collection only.

**Called by.** `conditions.py:32`.
**Calls.** langchain loaders/splitters/embeddings/Chroma, `pypdf`, `tqdm`.

**Gotchas — this file has the sharpest ones in the repo.**
- **`ensure_packages()` runs at import time** (`:57`, module level, outside any guard). Any
  import of `conditions` therefore triggers a dependency scan, and if anything is missing it
  shells out to `os.system("... pip install ...")`. See `code_shortlist.md` §6 item 1.
- **`--rebuild` is a dead flag.** Parsed at `:375`, never read in `main()`. The help text
  (`:443`) and `docs/PROJECT.md:34` both tell you to use it. Running that command rebuilds
  the **frozen** `chroma_db/` regardless, because `--db_dir` defaults to it (`:367`).
- `load_pdfs` derives the DOI with `.replace("_", "/", 1)` (`:93`) — the same first-underscore
  rule as `build_index.filename_to_doi`, duplicated rather than shared.
- The root-level `rag_pipeline.py` is an **older copy without the `embeddings=` parameter**.
  It is unreachable in normal use because `core/` lands on `sys.path[0]`, but if the repo
  root were ever put on the path first, `get_store()` would raise `TypeError` — a loud
  failure, which is the good outcome.

---

### `core/clean_index/build_index.py` (201 lines)

**What it is for.** The reusable engine of the clean indexer: map filename→DOI, call GROBID,
parse, chunk, embed, write to Chroma in batches, and log every failure. It has a CLI, but
the canonical corpus was actually built by `build_owf_clean_v1.py`, which imports this
module's pieces and layers a triage policy on top.

**Public surface.**
- `filename_to_doi(pdf_name) -> str` (`:43-45`) — `10.1016_j.x.pdf` → `10.1016/j.x`.
  **Replaces only the first underscore.**
- `doi_to_filename(doi) -> str` (`:47-49`) — `re.sub(r"[^\w\-_.]", "_", doi) + ".pdf"`.
- `extract_one(client, pdf_path, config) -> (docs, parsed)` (`:78-84`).
- `build(config, limit=None, dry_run=False, single_pdf=None)` (`:87-168`).
- `main()` (`:171-197`) — CLI with `--pdf_dir --dois_file --db_dir --collection
  --grobid_url --limit --pdf --dry-run --health`.
- `_chunk_id(doi, idx)` (`:52-53`) — `md5(f"{doi}_{idx}")[:12]`.

**Reads / writes.** Reads PDFs and GROBID. Writes the Chroma collection, plus appends to
`config.failure_log` and `config.skip_list` (`:71-75`).

**Called by.** `build_owf_clean_v1.py:39` (imports `filename_to_doi`, `doi_to_filename`,
`extract_one`, `_chunk_id`), `validate_sample.py:32`.
**Calls.** `config`, `grobid_client`, `tei_parser`, `chunking`, `embeddings` (lazily at
`:109`), `langchain_chroma.Chroma`.

**Gotchas.**
- `filename_to_doi` is **lossy in one direction only**. `doi_to_filename` destroys slashes,
  parentheses and (via the source data) case; `filename_to_doi` restores only the first
  slash. This is the origin of the 68 mangled DOIs in the live index, and it is why
  `conditions.canonicalise_doi` exists.
- Chunk ids key on `(doi, chunk_index)`, so re-extracting a paper that now yields **fewer**
  chunks leaves the surplus high-index chunks from the previous build orphaned in the
  collection. Nothing detects this.
- `flush()` is called inside the per-document loop (`:154-155`) but the batch check is
  `>= config.batch_size` evaluated per document, so batches can overshoot slightly. Harmless.
- Both `except` arms (`:132`, `:137`) append to the skip list, so a transient GROBID 500
  permanently skip-lists a PDF unless the list is manually cleaned.

---

### `core/clean_index/build_owf_clean_v1.py` (285 lines) — **the actual index builder**

**What it is for.** The study-specific driver that produced `owf_clean_v1`. It layers the
triage policy on the engine: 15 named PDFs excluded with reasons, one glyph-broken paper
routed through pymupdf instead of GROBID, one GROBID retry, and a per-paper manifest.

**Public surface.** `load_meta_titles()` `:73`, `pymupdf_fulltext(pdf_path)` `:85`,
`pymupdf_documents(text, doi, source, title, cfg)` `:97`,
`grobid_with_retry(client, pdf, cfg, retries=1)` `:113`, `main()` `:124`,
`write_manifest(rows, cfg, store)` `:232`.

**Reads / writes.** Reads `PDFs/` and `paper_metadata.json` (`:44`). Writes
`owf_clean_v1_MANIFEST.md` (`:45`), `owf_clean_v1_papers.csv` (`:45`),
`owf_clean_v1_build_checkpoint.jsonl` (append, `:162`), and the Chroma collection.

**Called by.** Nothing — it is a `python -m` entry point.
**Calls.** `config`, `grobid_client`, `build_index`, `embeddings`, `fitz` (pymupdf),
langchain.

**Constants that matter.** `EXCLUDE` dict (`:49-`) — 15 DOIs with a reason string each,
mirrored verbatim into the manifest. `--resume` (`:127`) skips DOIs already in the
checkpoint.

**Gotchas.**
- **`fitz` (pymupdf) is imported at module level (`:33`) but is not in `requirements.txt`.**
  The file will not import without it.
- The glyph paper's pymupdf path produces chunks with **no section structure** — a
  documented one-off exception that the manifest records but the code treats as normal.
- The checkpoint is append-only and is merged back in at `:221-227`, so a partial run
  followed by a full run without `--resume` would double-count rows in the manifest
  (not in Chroma, where ids dedupe).

---

### `core/conditions.py` (356 lines) — **the heart of the design**

**What it is for.** Defines what each of the five conditions actually shows the model, and
owns the single retrieval function they share. Everything that distinguishes A from B1 from
B2 from C from D lives here in about 120 lines.

**Public surface.**
- `canonicalise_doi(doi) -> str` (`:93-108`) — keep the first slash, turn every later slash
  into an underscore. Query-side only; stored data is never mutated.
- `get_store() -> Chroma` (`:130-137`) — memoised singleton; builds the profile's embeddings
  and calls `load_existing_vector_store`.
- `retrieve(question, k=5, exclude_dois=None) -> list[dict]` (`:140-178`) — returns up to `k`
  dicts of `{text, doi, chunk_index, score}`. Over-fetches `k+10` when excluding.
- `prepare_A(question) -> (public, None)` (`:214-217`)
- `prepare_B1(question, k=5) -> (public, context)` (`:228-234`)
- `prepare_B2(question, gt_dois, k=5) -> (public, context|None)` (`:277-308`)
- `prepare_C(question, k=5, gt_dois=None, distractor_query=None, seed=None)` (`:245-264`)
- `prepare_D(question, contradiction_text) -> (public, context)` (`:322-333`)
- `condition_A/B1/B2/C/D(...)` (`:220, 237, 311, 267, 336`) — prepare+generate wrappers.
  **Used only by the `__main__` demo at `:341-356`**; the runner never calls them (verified
  by grep across every `.py` in the repo).
- Module constants `PROFILE` `:81`, `DB_DIR` `:88`, `COLLECTION` `:89`, `EMB_MODEL` `:90`,
  `DISTRACTOR_QUERIES` `:114-125`, `RETRIEVAL_PROFILES` `:66-79`.

**Reads / writes.** Reads env `RAG_RETRIEVAL_PROFILE`, `RAG_DB_DIR`, `RAG_COLLECTION`, and
the Chroma collection. **Writes nothing.**

**Called by.** `run_experiment.py:35-38` (the five `prepare_*` plus `PROFILE`, `COLLECTION`,
`DB_DIR`), `build_contradictions.py:39` (`get_store`, `canonicalise_doi`),
`analyse_d3.py:616` (`retrieve`, `canonicalise_doi`, `COLLECTION`, `DB_DIR`, `PROFILE`,
`EMB_MODEL`).
**Calls.** `rag_pipeline.load_existing_vector_store` (`:32`), `llm_generation.generate_answer`
(`:33`), `clean_index.config.default_config` + `clean_index.embeddings.build_embeddings`
(`:39-43`).

**Constants that matter.**

| Constant | file:line | Note |
|---|---|---|
| `PROFILE` default | `:81` | `"clean"` — raises `ValueError` on an unknown value (`:82-85`) |
| clean profile | `:67-72` | `chroma_db_clean/` + `owf_clean_v1` + BGE query-prefix |
| frozen profile | `:73-78` | `chroma_db/` + `wind_farm_papers` + `embeddings=None` (no prefix) |
| `fetch_k` | `:162` | `k + 10` when excluding, else `k` |
| B2 filter | `:291` | `{"doi": x}` or `{"doi": {"$in": [...]}}` |
| D provenance stub | `:332` | `doi = "SYNTHETIC_COUNTERFACTUAL"`, `chunk_index`/`score` `None` |
| `DISTRACTOR_QUERIES` | `:114-125` | 10 hand-written off-topic queries |

**Gotchas — the important ones.**
- **`random.seed(item_idx)` (`:257-258`) seeds the *global* `random` module**, not a local
  `Random` instance. Two consequences: (a) any other code that draws from `random` after a
  `prepare_C` call inherits that seed; (b) with 12 items and a 10-item list, only **6
  distinct queries** are drawn — items 3/4/8, 5/6/10 and 9/11 receive byte-identical
  distractor contexts. Verified in `results_d3.jsonl`.
- **Condition C's only anti-collision guard is the item's own gold DOI.** There is no
  topic-level check of any kind. Another item's gold paper is free to enter, and did:
  D3-11's "irrelevant" context contains D3-09's and D3-10's gold papers.
- **`fetch_k = k + 10` is a fixed budget.** If more than 10 of the top 15 chunks belong to
  excluded papers, `retrieve` returns **fewer than k** chunks silently — no warning, no
  exception. It did not bite here (all 24 C cells have exactly 5 docs) but nothing checks.
- B2 does **not** go through `retrieve()`. It calls `similarity_search_with_score` directly
  with a metadata filter (`:293`), so the exclusion logic, the over-fetch and the `_meta`
  helper are all bypassed and its provenance dict is built inline (`:303-306`).
- `canonicalise_doi` handles slashes only. It cannot reverse the parenthesis-and-case loss
  in ASCE-style DOIs; `project_log.md:24` records 10 such DOIs.
- The comment at `:99-101` says "Four OUP sources are affected". Measured: 15 OUP DOIs and
  68 underscore-bearing DOIs in the live index.
- `_store` is a module global (`:127`). Changing `RAG_COLLECTION` after the first retrieval
  in a process has no effect.

---

### `core/classifier.py` (170 lines) — **the judge**

**What it is for.** Takes one answered cell plus the gold claim and assigns one of six
labels, using four separate one-word LLM judgments in a fixed order. It is condition-aware
on purpose: "the context lacked the answer" only means *retrieval failure* in B1/B2.

**Public surface.**
- `judge_abstained(answer) -> bool` (`:73-75`)
- `judge_correct(answer, claim_text) -> bool` (`:78-81`)
- `judge_grounded(answer, context_docs) -> bool` (`:84-87`)
- `judge_retrieval_hit(context_docs, claim_text) -> bool` (`:90-93`)
- `classify(result, claim_text) -> dict` (`:96-143`) — returns a **copy** of the input dict
  plus `abstained`, `correct`, `grounded`, `retrieval_hit`, `failure_type`.
- `_join(context_docs)` (`:69-70`) — numbers passages `[1] … [2] …`.
- `_self_test()` (`:146-166`) — four synthetic cases, one per label.
- `JUDGE_MODEL = "llama-3.1-8b-instant"` (`:39`).

**Reads / writes.** No files. **Makes 1–4 network calls per cell.**

**Called by.** `run_experiment.py:39` (imports `classify`, `JUDGE_MODEL`), invoked at
`run_experiment.py:291`.
**Calls.** `llm_generation.complete`.

**Decision order** (`:113-143`): `answer is None` → `no_answer`; ABSTAIN → `abstention`;
CORRECT → `failure_type = None`; Condition A → `parametric_error`; compute `grounded`; in
B1/B2 compute `retrieval_hit` and if MISS → `retrieval_failure`; else `grounded_but_wrong`
or `ungrounded_hallucination`.

**Gotchas.**
- **Parsing is `v.strip().upper().startswith(TOKEN)` with no out-of-vocabulary detection and
  no retry.** Anything that does not start with the positive token silently becomes the
  negative class. `"The answer is CORRECT"` parses as **INCORRECT**. Mitigated only by
  `max_tokens=5`.
- **The raw judge string is never stored** — only the boolean. A malformed reply is
  unrecoverable after the fact; you cannot audit how many occurred.
- **`grounded` is left `None`, never `False`, on abstentions, correct answers and all of
  Condition A**, because those paths return before `:135`. In the frozen run it is populated
  on only **25 of 120** cells. Same for `correct` on abstentions.
- The one `retrieval_failure` cell has `grounded=False` recorded even though the label is
  `retrieval_failure`, because grounding is computed at `:135` before the hit test at `:137`.
- `retrieval_hit` fired on exactly **one** cell in 120, so it is not a usable statistic.
- `classify` returns `dict(result)` (`:109`) — a **shallow** copy, so `context_docs` and
  `retrieved_meta` are shared with the caller's dict.

---

### `core/build_contradictions.py` (264 lines)

**What it is for.** The one-time, offline builder of Condition D's counterfactual passages.
For each item it pulls the oracle passage, checks the gold paper really is about the claim,
rewrites the passage to assert the opposite, verifies the rewrite contradicts the claim, and
freezes everything to a JSON cache. Freezing is the point: D is reproducible and auditable
because the passages never change between runs.

**Public surface.**
- `get_oracle_chunks(store, claim_text, gt_dois, k=3) -> list[str]` (`:73-89`) — queries by
  **`claim_text`**, not the question, with a DOI metadata filter. Returns `[]` if not indexed.
- `check_provenance(claim_text, chunks) -> bool` (`:114-126`) — 3-example few-shot
  MATCH/MISMATCH, biased to MATCH when unsure (`:99`).
- `make_counterfactual(question, original, claim_text, model=None) -> str` (`:144-156`).
- `verify_contradiction(claim_text, counterfactual, model=None) -> bool` (`:159-162`).
- `load_cache()` / `save_cache(cache)` (`:165-174`).
- `main()` (`:177-260`) — `--limit --regenerate --only_failed --model`.
- `EDITOR_MODEL = "llama-3.1-8b-instant"` (`:65`).

**Reads / writes.** Reads `RAG_EVAL_SET` (default `d3_eval_set.json`, `:47`) and the Chroma
collection. **Writes `RAG_CONTRADICTIONS_CACHE` (default `contradictions_cache.json`,
`:55`) after every item (`:247`).**

**Called by.** `run_experiment.py:40` imports `EDITOR_MODEL` (for the run-config record
only). `main()` is a manual entry point.
**Calls.** `conditions.get_store`, `conditions.canonicalise_doi`, `llm_generation.complete`.

**Constants that matter.** `temperature=0.4, max_tokens=600` for the rewrite (`:155`) —
**the only non-zero temperature in the entire project**. Source truncated to
`original[:900]` (`:150`). Oracle `k=3` (`:73`). Prompts: `COUNTERFACTUAL_SYSTEM`
`:129-141`, `VERIFY_SYSTEM` `:67-70`, `PROVENANCE_SYSTEM` `:92-111`.

**Gotchas.**
- **The docstring at `:9-10` claims "a STRONGER editor model (Llama 3.3 70B)". `:65` sets
  8B.** The comment block at `:59-64` explains the 8B choice honestly, so the file
  contradicts itself within six lines. Net effect: writer, provenance checker, verifier,
  judge and the 8b subject are **all the same model**.
- Docstring `:6` says `pilot_eval_set.json`; the default is `d3_eval_set.json`. `:63` says
  "all 67".
- **`save_cache` rewrites the whole file after every item (`:247`) with no backup.** A crash
  mid-`json.dump` truncates the frozen cache. Nothing guards against re-running it against
  the D3 cache path.
- 3 model calls per item (provenance, rewrite, verify), so `--limit` matters for the token cap.

---

### `core/run_experiment.py` (434 lines) — **entry point**

**What it is for.** The runner. It walks every (item × condition × model) cell, builds the
inputs *without* generating so a content-addressed key can be computed first, skips anything
already in the cache, then generates, judges, and appends one JSON line. Built to survive
free-tier token caps across multiple days.

**Public surface.**
- `content_hash(model_name, condition, item_id, prompt_text, context_ids, k, temperature,
  seed, extra=None) -> str` (`:122-144`) — sha256 over a sorted JSON payload.
- `human_key(item_idx, condition, model_tag, chash) -> str` (`:147-149`) — the greppable
  `"{idx}|{cond}|{model}|{hash8}"`. **This is the string `export_human_labels.row_uid`
  hashes**, so it is load-bearing for the human-label join.
- `prepare_cell(item, item_idx, condition, contradictions, k=5)` (`:152-185`) — dispatches to
  the five `prepare_*`; returns `(public, gen_context, can_generate, extra)`.
- `cell_signature(...) -> dict` (`:188-203`)
- `load_done_hashes() -> set` (`:206-222`)
- `append_result(rec)` (`:225-227`)
- `build_run_config(model_tags, conditions) -> dict` (`:230-269`)
- `write_run_config(...)` (`:272-276`)
- `run_prepared(sig, item, item_idx, condition, model_tag, model_name) -> dict` (`:279-302`)
- `cmd_status(...)` (`:305-337`), `cmd_export(path)` (`:340-361`), `main()` (`:364-430`)
- `_context_ids(public)` (`:112-119`)

**Reads / writes.**
Reads: `RAG_EVAL_SET` (`:53`, default `d3_eval_set.json`), `RAG_CONTRADICTIONS_CACHE`
(`:60`, **default `contradictions_cache.json` — the pilot file**), `RAG_RESULTS_FILE`
(`:68`, default `results_cache.jsonl`), the Chroma collection, the LLM API.
Writes: appends to the results JSONL (`:226`); overwrites `RAG_RUN_CONFIG` (`:71`, default
`run_config.json`) at `:274`; `--export` writes a CSV (`:356`).

**Called by.** Nothing — it is the top-level entry point.
**Calls.** `conditions` (`:35-38`), `classifier` (`:39`), `build_contradictions` (`:40`),
`llm_generation` (`:41-44`).

**Constants that matter.**

| Constant | file:line | Value |
|---|---|---|
| `MODELS` | `:87-90` | `{"8b": "llama-3.1-8b-instant", "70b": "llama-3.3-70b-versatile"}` |
| `ALL_CONDITIONS` | `:92` | `["A","B1","B2","C","D"]` |
| `DEFAULT_K` | `:96` | `5` |
| `TEMPERATURE` | `:97` | `0.0` |
| `MAX_TOKENS` | `:98` | `512` |
| `SEED` | `:99` | `None` — unset |
| `KEY_SCHEMA_VERSION` | `:100` | `2` |
| C seed | `:173` | `seed=item_idx` |

**Gotchas.**
- **`EVAL_SET` defaults to the D3 file but `CONTRADICTIONS` defaults to the *pilot*
  filename** (`:53` vs `:60`). A bare `python run_experiment.py` therefore pairs the D3 eval
  set with the pilot's contradictions cache, which is index-misaligned. The real run avoided
  this only because the env var was set. There is no consistency check between the two.
- `write_run_config` **overwrites** its target before any work (`:393`), so re-running with
  the D3 env vars would rewrite `run_config_d3.json` with a new timestamp.
- The `except RuntimeError` at `:421` catches the rate-limit path and exits **0**. Any other
  exception aborts with a traceback. `sys.exit(0)` on a token cap is deliberate but means a
  wrapper script cannot distinguish "finished" from "stopped early" by exit code.
- `cmd_status` counts *distinct item indices with at least one record*, not content hashes
  (`:307-308`), so it can report a cell as done when the cached record is from a different
  prompt or model revision.
- `cmd_export` writes 10 flat columns (`:354-355`) and drops `cell_key`, `content_hash`,
  `context_docs`, `retrieved_meta`. Downstream tools that need those read the JSONL directly.
- `content_hash` includes the full prompt text, so a whitespace change to a system prompt
  invalidates every cached cell.

---

## Tier 2 — analysis and validation

### `analyse_d3.py` (1088 lines) — **entry point, current analysis**

**What it is for.** The single producing script for the five quantities that previously
existed only as prose. It regenerates per-condition correctness, McNemar, inter-annotator
agreement, the judge-outlier cross-tab and Hit@k from the frozen artefacts, then verifies
every figure against the published value and prints a PASS/FAIL table.

**Public surface (selected).** `wilson(k, n, z)` `:114`; `mcnemar_exact(b, c)` `:126`;
`cohen_kappa(pairs)` `:155` (returns `(po, pe, kappa, n, k, degenerate)`); `pabak(po, k)`
`:178`; `require(condition, message)` `:223`; `load_cells()` `:232`; `load_raters()` `:275`;
`stage1_correctness` `:312`; `_paired` `:352`; `stage2_mcnemar` `:379`;
`stage3_interannotator` `:420`; `stage4_judge_outliers` `:505`; `stage5_retrieval(max_k=10)`
`:564`; `build_checks` `:682`; `print_verification` `:760`; `print_failure_report` `:783`;
`write_markdown` `:833`; `main()` `:1007`. `class AnalysisError(RuntimeError)` `:218`.

**Reads / writes.** Reads `results_d3.jsonl`, `d3_eval_set.json`, `human_label_key_d3.json`,
both rater CSVs, and (stage 5 only) the Chroma collection read-only. **Writes only
`analysis_d3_full.md` and `analysis_d3_full.json`.**

**Called by.** Nothing — entry point.
**Calls.** Lazily imports `conditions` inside `stage5_retrieval` (`:616`), so stages 1–4 are
stdlib-only.

**Constants that matter.** `N_ITEMS=12`, `N_CELLS=120` (`:59-60`); `EXPECTED_PAPERS=501`,
`EXPECTED_CHUNKS=34502` (`:66-67`); `WILSON_Z=1.959963984540054` (`:73`).

**Gotchas.**
- Stage 5 needs the project venv. Under bare system Python the import fails, is caught at
  `:617`, and re-raised as an `AnalysisError` telling you to use `--skip-retrieval`.
- Every structural assumption is a `require()` that aborts with exit code 2 rather than
  producing a partial report.
- The index integrity check reads sqlite in `mode=ro` **before** any Chroma client opens the
  file, because opening a Chroma collection bumps the sqlite mtime without changing content.

---

### `core/analyse_results.py` (249 lines) — SUPERSEDED, but `load()` is live

Pilot-era table printer. Superseded by `analyse_d3.py` because on D3 data it applies the
pilot `EXCLUDE = {2,34,45}` (`:50`) — index 2 is the valid item D3-03, so Condition D reads
22/22 — hard-codes "all 67 items" (`:98`, `:159`), pools 8b and 70b with no split (`:84-88`),
and its paired B1/B2 block keys a dict on `item_idx` alone (`:182-188`), silently discarding
all 12 8b rows. Its docstring says the exclusion covers "D / B2" but `exclude_items` is
passed only on the three D calls (`:150,152,155`).

**Still live:** `load(path)` (`:75-81`), the canonical six-way label reconstruction
(`failure_type or "correct"`), imported by `export_human_labels.py:44` and
`nli_grounding_d3.py:39`. Also `wilson(k, n, z=1.96)` (`:58-67`).

---

### `score_judge_validation.py` (234 lines)

**What it is for.** Scores one completed human sheet against the judge key: six-way κ,
binary correct-vs-not κ, the grounding decision, a confusion matrix and per-condition
agreement. Reports observed agreement and PABAK alongside κ, never κ alone, because the
marginals here are heavily skewed.

**Public surface.** `norm_label(s)` `:43`; `parse_bool(s)` `:50`;
`condition_from_cell_key(cell_key)` `:61`; `observed_agreement(pairs)` `:67`;
`cohen_kappa(pairs)` `:73` → `(po, pe, kappa, n, k)`; `pabak(po, k)` `:88`; `rnd(x, p=4)`
`:96`; `load_joined(sheet_path, key_path)` `:100`; `main()` `:124`.

**Reads / writes.** Reads `--sheet` (default `human_label_sheet_d3.csv`) and `--key`
(default `human_label_key_d3.json`). **Writes `judge_validation_d3.md` and `.json` at
hard-coded paths (`:39-40`).**

**Called by.** Nothing directly; `interannotator_kj_aneesha.md:6-9` says its functions were
imported ad hoc for the human-vs-human comparison, but no such script is in the repo.

**Gotchas.**
- **`--sheet` selects the input but not the output.** Scoring Aneesha then KJ overwrote the
  first result; the surviving `judge_validation_d3.json` is the **KJ** run. The two
  per-rater `.md` files are hand-transcriptions containing sections the scorer never emits.
- The grounding block is restricted to rows where `judge_grounded is not None` (`:167-168`)
  — only 25 cells, minus 1 blank = 24 — even though the raters filled 72.
- A `row_uid` in the sheet but not the key raises `SystemExit` (`:107`); the reverse is not
  checked.

---

### `nli_grounding_d3.py` (430 lines) — entry point

**What it is for.** Re-checks the grounding decision with a model from a different family
(DeBERTa-v3-large-MNLI), so the grounding signal does not rest on the Llama family alone.
Deterministic and resumable; asserts at runtime that its label reconstruction matches
`analyse_results.load()`.

**Public surface.** `load_nli()` `:67` → `(mid, rev, tok, model, id2label, idx)`;
`nli_batch(premises, hypotheses)` `:100`; `over(premise_list, hypothesis)` `:109`;
`split_sentences(t)` `:118`; `main_claim_sentence(answer)` `:124`;
`observed_agreement` `:134`; `cohen_kappa` `:138`; `pabak_binary(po)` `:151`; `main()` `:160`.

**Reads / writes.** Reads `results_d3.jsonl`, `results_d3.csv`, `d3_eval_set.json`, and
optionally the sheet + key. Writes `nli_grounding_d3.md` / `.json`, plus an append-only
resume cache `NLI_CACHE` (default `nli_cell_cache_d3.jsonl`, `:56`) which it **deletes on
success** (`:419`). **Downloads the DeBERTa model from HuggingFace** and calls `HfApi()` to
pin a revision (`:70`).

**Called by.** Nothing — entry point.
**Calls.** `analyse_results.load` (`:39`), `torch`, `transformers`, `huggingface_hub`.

**Constants that matter.** `MODEL_ID` `:58`, `FALLBACK_ID = "roberta-large-mnli"` `:59`,
`GROUND_THRESHOLD = 0.5` `:60`, `THRESHOLDS = [0.5, 0.7, 0.9]` `:61`,
`torch.manual_seed(0)` `:63`.

**Gotchas.**
- `torch`, `transformers` and `huggingface_hub` are **not in `requirements.txt`**.
- `load_nli()` runs at **module import** (`:96`), so merely importing this file downloads and
  loads a ~1.6 GB model. There is no `--skip` path.
- If `MODEL_ID` fails it silently falls back to `roberta-large-mnli`, a **different model
  family with different label ordering**, and the run continues. The output records which
  model was used (`:243-244`), so it is auditable — but nothing stops it.
- Section 5 (three-way NLI/judge/human) reports "skipped" because it reads the **blind**
  `human_label_sheet_d3.csv` (`:48`), whose `human_grounded` column is empty by
  construction. The completed rater CSVs were never substituted.
- Labels are mapped **by name** (`:79-87`), which is what makes the fallback survivable.

---

### `export_human_labels.py` (260 lines) — UTILITY, entry point

Builds the blind rater workbook. `row_uid(cell_key) = sha1(cell_key)[:10]` (`:66-68`) — so
the join key is a stable function of `run_experiment.human_key`. `judge_label_of(rec)`
(`:71-73`) restates the label rule; a zero-drift guard (`:177-179`) aborts if it disagrees
with the imported `analyse_results.load()`. `stratified_subset` (`:118-157`) forces in the
two singleton cells (`:57-60`) and takes one per populated stratum.

**Writes `human_label_sheet_d3.csv` (`:195`), `human_label_key_d3.json` (`:210`) and
`taxonomy_rubric.md` (`:214`) unconditionally, with no overwrite guard.** With default args
the fixed seed (`DEFAULT_SEED = 20260711`, `:54`) makes the output byte-identical, so an
accidental re-run is recoverable — but `--n` or `--seed` would silently replace the key both
rater CSVs join against.

---

### `build_label_app.py` (632 lines) — UTILITY, entry point

Emits a self-contained offline HTML labelling app from `human_label_sheet_d3.csv` and
`taxonomy_rubric.md`. Blindness is enforced, not assumed: it never opens the key, and a
build-time self-check parses the generated HTML back and aborts if any per-row judge field
or value is present (`BANNED_ROW_FIELDS`, `:48-`). Writes one HTML file (`:184`), default
`label_app_d3_<title>.html`. Label dropdowns are derived from the rubric's
applicable-conditions text rather than a second hard-coded mapping.

---

### `core/clean_index/validate_sample.py` (175 lines) — UTILITY

Side-by-side old-vs-new chunk comparison for ~5 PDFs. Opens the frozen sqlite with
`mode=ro&immutable=1` (`:47`), which is stricter than anything else in the repo — no `-wal`
or `-shm` side files are created. Writes nothing. Requires GROBID.

### `core/inspect_contradictions.py` (27 lines) — UTILITY

Prints the claim next to the retrieved oracle chunks per item. **Hard-wired to
`contradictions_cache.json` at `:15` with no argument and no env override**, so it dumps the
*pilot* cache; it cannot show `contradictions_cache_d3.json` without editing the file.

---

## Tier 3 — superseded corpus-build scripts (short entries)

- **`setup/doi_discovery_dualmode_clean_fixed_queryloader.py`** (1420) — dual-mode DOI
  discovery over OpenAlex / Scopus / WoS with local AND-group re-screening. Ran May 2026;
  outputs (`dois_raw_*.txt`, `doi_sources*.txt`, `debug_rejections.tsv`,
  `hybrid_openalex_queries.json`) are frozen. Its OpenAlex mode requires
  `--descriptor_file descriptor_keywords.txt`, **which is not in the repo**, so the OpenAlex
  half is not reproducible as committed. Keys from `SCOPUS_API_KEY` / `WOS_API_KEY`
  (`:1326-1327`). Nothing replaced it; it simply is not re-run.
- **`setup/doi_download_only.py`** (379) — per-DOI OA resolution (Unpaywall → OpenAlex →
  landing-page scrape → Elsevier direct) and download. Superseded only in the sense that
  `PDFs/` is now frozen.
- **`setup/download_with_progress.py`** (135) — tqdm wrapper; imports six functions from
  `doi_download_only` (`:17-24`). Same status.
- **`setup/01_clean_fake_pdfs.py`** (116) — detects HTML-saved-as-PDF and **deletes** them
  (`:102`) behind an interactive `input("... yes/no")` (`:94`). Wrote
  `fake_pdfs_removed.txt`. One-shot.
- **`setup/02_download_extra_sources.py`** (278) — CORE / Semantic Scholar / arXiv fallback
  for DOIs that failed round one. One-shot.
- **`setup/03_enrich_metadata.py`** (248) — OpenAlex enrichment → `paper_metadata.json`
  (1,716 records incl. `citation_count` from `cited_by_count`, `:103`). Historical, but its
  output is still read by `build_owf_clean_v1.py:44` and by the popularity audit.
- **`setup/04_build_pilot_eval_set.py`** (496) — extracted cited claims from the Eklipse PDF
  and matched them to corpus papers by `(surname, year)` (`:269-296`), with the corpus
  pre-filtered to downloaded PDFs (`:423`). Wrote `pilot_eval_set.json` (`:381`). **Replaced
  by hand construction**: no script writes `d3_eval_set.json`, and this one emits no `tags`
  field at all. It is the origin of D3-03's unjustified source pairing
  (`d3_03_provenance.md:186`).
- **`setup/05_evaluate_retrieval.py`** (219) — pilot Hit@k. Defaults to the frozen index and
  pilot set (`:104-106`); matches DOIs by raw set intersection with **no canonicalisation**
  (`:78-84`), so mangled multi-slash gold DOIs count as misses. Produced the superseded
  0.433. Replaced by `analyse_d3.py` stage 5.
- **`rag_pipeline.py`** (root, 435) — older copy of `core/rag_pipeline.py` lacking the
  `embeddings=` parameter. Unreachable because `core/` lands on `sys.path[0]`. Replaced by
  `core/rag_pipeline.py`.

## Tier 4 — dead copies (short entries)

- **`handoff_bioagora/score_judge_validation.py`**, **`export_human_labels.py`**,
  **`build_label_app.py`** — outbound copies for the BioAgora collaboration
  (`project_log.md:24`). The first two are byte-identical to the root originals; the third
  differs by one leading blank line. Nothing in this repo imports them, and
  `export_human_labels.py` would fail if run in place because its
  `sys.path.insert(ROOT/"core")` resolves to a directory that does not exist there.
- **`supervisor/doi_download_only.py/doi_download_only.py`** and
  **`supervisor/doi_discovery_.../doi_discovery_....py`** — unpacked zips of the supervisor's
  originals, kept for provenance. The `setup/` copies (which add repo-root path anchoring)
  are the ones that ran. Both directories also contain `__MACOSX/._*.py` AppleDouble stubs.

---

# 3. Call graph (LIVE modules only)

```
  ENTRY POINTS (run directly; nothing imports them)
  ================================================

  [python core/run_experiment.py]                                  <== THE EXPERIMENT
        |
        |-- conditions            (prepare_A/B1/B2/C/D, PROFILE, COLLECTION, DB_DIR)
        |-- classifier            (classify, JUDGE_MODEL)
        |-- build_contradictions  (EDITOR_MODEL  -- constant only, for the run-config record)
        `-- llm_generation        (build_prompt, generate_answer, resolve_provider,
                                   GROQ_MODEL, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS)

  [python core/build_contradictions.py]                            <== D CACHE (one-time)
        |-- conditions            (get_store, canonicalise_doi)
        `-- llm_generation        (complete)

  [python -m core.clean_index.build_owf_clean_v1]                  <== THE INDEX (one-time)
        |-- clean_index.config          (default_config)
        |-- clean_index.grobid_client   (GrobidClient, GrobidError)
        |-- clean_index.build_index     (filename_to_doi, doi_to_filename, extract_one, _chunk_id)
        |-- clean_index.embeddings      (build_embeddings)
        `-- fitz (pymupdf)              [glyph-paper path only]

  [python analyse_d3.py]                                           <== CURRENT ANALYSIS
        `-- conditions  [LAZY, stage 5 only, inside stage5_retrieval at :616]
                        (retrieve, canonicalise_doi, COLLECTION, DB_DIR, PROFILE, EMB_MODEL)

  [python nli_grounding_d3.py]                                     <== NLI CROSS-CHECK
        |-- analyse_results       (load  -- label reconstruction only)
        `-- torch / transformers / huggingface_hub   [model loaded AT IMPORT, :96]

  [python score_judge_validation.py]                               <== JUDGE VALIDATION
        `-- (stdlib only)

  [python export_human_labels.py]                                  <== RATER WORKBOOK
        `-- analyse_results       (load)

  [python build_label_app.py]                                      <== LABELLING APP
        `-- (stdlib only)


  SHARED MODULE LAYERS (nothing below imports anything above it)
  =============================================================

     conditions.py
         |                                     .-------------------------.
         |-- rag_pipeline.load_existing_vector_store   (core/ copy only) |
         |        `-- langchain_chroma.Chroma  <-------------------------'
         |        `-- !! ensure_packages() FIRES AT IMPORT (rag_pipeline.py:57) !!
         |-- llm_generation.generate_answer
         `-- clean_index.config.default_config  +  clean_index.embeddings.build_embeddings

     classifier.py                build_contradictions.py
         `-- llm_generation.complete   `-- llm_generation.complete
                                       `-- conditions.get_store / canonicalise_doi

     llm_generation.py            <-- LEAF. openai client only. No local imports.

     clean_index/build_index.py
         |-- .config      |-- .grobid_client   (requests -> localhost:8070)
         |-- .tei_parser  `-- .chunking -> .tei_parser (ParsedDoc)
         `-- .embeddings  [lazy, :109]

     clean_index/config.py        <-- LEAF
     clean_index/embeddings.py    <-- LEAF (langchain only)
     clean_index/tei_parser.py    <-- LEAF (stdlib xml.etree only)
     clean_index/grobid_client.py <-- LEAF (requests only)


  THE ONE CROSS-TIER EDGE WORTH KNOWING
  =====================================
  conditions.py:32   `from rag_pipeline import load_existing_vector_store`
  is an UNQUALIFIED import. It resolves to core/rag_pipeline.py only because the
  runner lives in core/, so core/ is sys.path[0]. analyse_d3.py, nli_grounding_d3.py
  and export_human_labels.py each do sys.path.insert(0, ROOT/"core") to reproduce
  that. Put the repo root on the path first and you get the SUPERSEDED root copy,
  whose load_existing_vector_store() has no `embeddings=` parameter -> TypeError.
```

---

# 4. Reproduction order

Timings are the repo's own estimates where recorded (`archive/README_RUN_ORDER.md`,
`docs/PROJECT.md`) and are marked as such; where nothing is recorded they say so.

### Legend

🔴 **FROZEN — DO NOT RE-RUN.** Re-running destroys or invalidates a published artefact.
🟡 **Re-runnable but pointless / costly.** Safe in principle, not needed.
🟢 **Safe to re-run.** Read-only or byte-identical output.

---

### Layer 1 — corpus (all frozen)

| # | Command | Produces | Time | Status |
|---|---|---|---|---|
| 1 | `python setup/doi_discovery_dualmode_clean_fixed_queryloader.py --sources openalex --descriptor_file descriptor_keywords.txt ...` | `dois_raw_discovered.txt`, `doi_sources.txt`, `debug_rejections.tsv`, `hybrid_openalex_queries.json` | not recorded | 🔴 **and NOT REPRODUCIBLE** — `descriptor_keywords.txt` is not in the repo |
| 2 | same script `--sources wos --scopus_wos_query_file OWF_WoS_Retry_Queries.txt ...` | `dois_wos_retry.txt` etc. | 30–60 min (`README_RUN_ORDER.md:47`) | 🔴 needs `WOS_API_KEY` |
| 3 | same script `--sources scopus --scopus_wos_query_file OWF_BirdsQuerySplit.txt ...` | `dois_birds_extra.txt` etc. | 20–30 min (`:79`) | 🔴 needs `SCOPUS_API_KEY` |
| 4 | PowerShell `Sort-Object -Unique` merges (`README_RUN_ORDER.md:70,103`) | `dois_merged_final.txt` (frozen) | seconds | 🔴 |
| 5 | `python setup/download_with_progress.py --email <you> --dois_file dois_merged_final.txt --output_dir PDFs` | `PDFs/*.pdf` | 1–2 h (`:104`) | 🔴 **network + writes into `PDFs/`** |
| 6 | `python setup/02_download_extra_sources.py --email <you> --dois_file dois_merged_final.txt` | more `PDFs/*.pdf`, `extra_sources_log.tsv` | not recorded | 🔴 |
| 7 | `python setup/01_clean_fake_pdfs.py` | `fake_pdfs_removed.txt`; **deletes PDFs** | minutes | 🔴 **DESTRUCTIVE** — deletes files after an interactive `yes` |
| 8 | `python setup/03_enrich_metadata.py --email <you>` | `paper_metadata.json` (1,716 records) | not recorded | 🔴 |
| 9 | Manual triage → `TRIAGE_REPORT.md`, `wrong_pdf_candidates.csv` | the 15-file exclusion list now hard-coded at `build_owf_clean_v1.py:49-` | — | 🔴 human step, not scripted |

### Layer 2 — the index (frozen)

| # | Command | Produces | Time | Status |
|---|---|---|---|---|
| 10 | `docker run --rm --init -p 8070:8070 lfoppiano/grobid:0.8.0` | GROBID on :8070 | ~1 min to start | 🟢 prerequisite only |
| 11 | `python -m core.clean_index.build_index --health` | prints ALIVE / NOT REACHABLE | seconds | 🟢 |
| 12 | `python -m core.clean_index.validate_sample` | prints old-vs-new chunk comparison | minutes | 🟢 writes nothing |
| 13 | `python -m core.clean_index.build_owf_clean_v1` | `chroma_db_clean/` (**501 papers, 34,502 chunks**), `owf_clean_v1_MANIFEST.md`, `_papers.csv`, `_build_checkpoint.jsonl` | hours (CPU embedding; the pilot's 45,830-chunk build was ~45 min per `PROJECT.md:34`, so this is the same order) | 🔴 **NEVER RE-RUN.** Every Hit@k rank and every B1/B2/C context in `results_d3.jsonl` is a function of this exact collection. `analyse_d3.py` asserts 501/34,502 before reading |

### Layer 3 — the eval set (frozen, and not scripted)

| # | Step | Produces | Status |
|---|---|---|---|
| 14 | Hand construction from the Eklipse Descriptor 3 findings, verified against each primary paper | `d3_eval_set.json` (12 items) | 🔴 **No script produces this file.** `setup/04_build_pilot_eval_set.py` writes the superseded 67-item `pilot_eval_set.json` and emits no `tags`. Workbook: `H1_gold_verification_workbook.md` |

### Layer 4 — the experiment (frozen)

| # | Command | Produces | Time | Status |
|---|---|---|---|---|
| 15 | `set RAG_EVAL_SET=d3_eval_set.json` · `set RAG_CONTRADICTIONS_CACHE=contradictions_cache_d3.json` · `python core/build_contradictions.py` | `contradictions_cache_d3.json` (12 entries, all oracle/verified) | ~36 LLM calls | 🔴 **NEVER RE-RUN.** Rewrites the file after every item with no backup, and the writer runs at **temperature 0.4** — you would get different passages, invalidating all 24 D cells |
| 16 | `set RAG_RESULTS_FILE=results_d3.jsonl` · `set RAG_RUN_CONFIG=run_config_d3.json` (plus the two above) · `python core/run_experiment.py` | `results_d3.jsonl` (120 cells), `run_config_d3.json` | one pass, no rate-limit stops (`project_log.md:17`) | 🔴 **NEVER RE-RUN.** Idempotent by content hash *if nothing changed*, but it **overwrites `run_config_d3.json` unconditionally at `:393`** before doing anything |
| 17 | `python core/run_experiment.py --export results_d3.csv` | `results_d3.csv` | seconds | 🟡 would reproduce the same 10 columns; no reason to |
| 18 | `python core/run_experiment.py --status` | progress table | seconds | 🟢 read-only |

### Layer 5 — validation (mixed)

| # | Command | Produces | Time | Status |
|---|---|---|---|---|
| 19 | `python export_human_labels.py` | `human_label_sheet_d3.csv`, `human_label_key_d3.json`, `taxonomy_rubric.md` | seconds | 🔴 **DO NOT RE-RUN.** No overwrite guard. With default args the fixed seed reproduces byte-identical output, but any `--n`/`--seed` silently replaces the key both rater CSVs join against |
| 20 | `python build_label_app.py` | `label_app_d3_full.html` | seconds | 🟡 deterministic; no need |
| 21 | Two independent raters label all 120 cells | `KJ_full_labels_d3_20260718.csv`, `AneeshaGunaratne_full_labels_d3_20260717.csv` | days | 🔴 human step |
| 22 | `python score_judge_validation.py --sheet KJ_full_labels_d3_20260718.csv` | `judge_validation_d3.md` / `.json` | seconds | 🟡 works, but **hard-coded output paths** — running it for the other rater silently overwrites |
| 23 | `python nli_grounding_d3.py` | `nli_grounding_d3.md` / `.json` | hours on CPU (96 cells × several NLI passes) | 🔴 **do not re-run for the demo.** Downloads ~1.6 GB at import |

### Layer 6 — analysis (safe)

| # | Command | Produces | Time | Status |
|---|---|---|---|---|
| 24 | `..\venv\Scripts\python.exe analyse_d3.py` | `analysis_d3_full.md` / `.json` + a 34/34 PASS table | ~1–2 min (embedding model warm-up dominates) | 🟢 **SAFE — this is the one to demo.** Read-only; two consecutive runs are byte-identical apart from the timestamp |
| 25 | `python analyse_d3.py --skip-retrieval` | same, stages 1–4, 30/30 PASS | ~1 s | 🟢 stdlib only; runs under any Python |
| 26 | `python core/analyse_results.py --csv results_d3.csv` | pilot-era tables | ~1 s | 🟡 **prints wrong denominators on D3** — see §2. Do not demo |

### The minimum path from an empty corpus

Steps 1 → 26. Realistically 1–5 are days of wall-clock (API rate limits and downloads),
13 is hours, 21 is days of human labelling, and 23 is hours of CPU. **Everything from step 1
to step 23 is frozen.** The only steps that should ever be re-run are 10–12, 18, and 24–25.
