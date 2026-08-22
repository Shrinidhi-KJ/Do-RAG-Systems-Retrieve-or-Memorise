# Project technical reference — what this system actually does

Read-only audit, 29 July 2026. Every claim below was verified against the current code
and the frozen outputs in `data_pipeline/`. Where something could not be established
from the repo it is written as **not determinable from the repo** rather than guessed.

Scope note up front: **there is no dissertation manuscript anywhere in this repo.** The
only prose to compare code against is `methodology_capture.md`, `README.md`, `docs/*.md`,
the `*_audit.md` / `*_validation*.md` reports, and the code's own docstrings. Section 6
(in `discrepancies.md`) compares code against those. Any discrepancy against the actual
dissertation text has to be checked by you by hand.

---

## 0. Current state — what exists

### 0.1 Repo tree (large blobs excluded)

```
Dissertation/
├── API/API.txt
├── lit survey/            4 reference PDFs (FaithEval, EACL/EMNLP demos, RePCS/)
├── Proposal & Ethics/     ethics approval + research_proposal.docx (not read; .docx)
├── supervisor/            Eklipse report copy, supplied DOI scripts (zips)
└── data_pipeline/         <-- the entire system
    ├── core/                       THE EXPERIMENT (live)
    │   ├── run_experiment.py       entry point
    │   ├── conditions.py           A/B1/B2/C/D assembly + retriever
    │   ├── llm_generation.py       provider, prompts, retry
    │   ├── classifier.py           the LLM judge
    │   ├── build_contradictions.py Condition D builder (one-time)
    │   ├── analyse_results.py      tables (see §5 caveats)
    │   ├── rag_pipeline.py         retriever loader (live copy)
    │   ├── inspect_contradictions.py
    │   └── clean_index/            THE INDEXER (live)
    │       ├── build_index.py  config.py  chunking.py
    │       ├── embeddings.py   grobid_client.py  tei_parser.py
    │       ├── build_owf_clean_v1.py  validate_sample.py
    ├── setup/                      CORPUS BUILD (superseded for D3, see 0.2)
    │   ├── 01_clean_fake_pdfs.py  02_download_extra_sources.py
    │   ├── 03_enrich_metadata.py  04_build_pilot_eval_set.py
    │   ├── 05_evaluate_retrieval.py
    │   ├── doi_discovery_dualmode_clean_fixed_queryloader.py
    │   ├── doi_download_only.py   download_with_progress.py
    ├── nli_grounding_d3.py         H2b independent-family cross-check
    ├── export_human_labels.py      H2a blind sheet + key builder
    ├── score_judge_validation.py   H2a scorer
    ├── build_label_app.py          offline HTML labelling app
    ├── rag_pipeline.py             SUPERSEDED duplicate of core/rag_pipeline.py
    ├── handoff_bioagora/           byte-identical copies of 4 scripts + corpus_dois.csv
    ├── PDFs/                       523 .pdf + 4 log files
    ├── chroma_db_clean/            LIVE index
    ├── chroma_db/                  frozen pilot index (read-only)
    ├── archive/frozen_study/       frozen pilot artefacts + frozen_study.zip (245 MB)
    ├── docs/                       ARCHITECTURE / PROJECT / WALKTHROUGH / CUE_CARD (STALE)
    └── staging_d3/                 EMPTY
```

### 0.2 Real entry points vs dead / superseded

| Script | Status | Evidence |
|---|---|---|
| `core/run_experiment.py` | **LIVE** — produced `results_d3.jsonl` | `run_config_d3.json:3` created 2026-07-10T10:30, `results_d3.jsonl` 10:45 |
| `core/conditions.py`, `llm_generation.py`, `classifier.py` | **LIVE** — imported by the runner | `run_experiment.py:35-44` |
| `core/build_contradictions.py` | **LIVE** (one-time) — produced `contradictions_cache_d3.json` | file mtime 2026-07-10 10:12, before the run |
| `core/clean_index/*` | **LIVE** — built `owf_clean_v1` | `owf_clean_v1_MANIFEST.md` |
| `core/rag_pipeline.py` | **LIVE** — only for `load_existing_vector_store()` | `conditions.py:32` |
| `nli_grounding_d3.py`, `export_human_labels.py`, `score_judge_validation.py`, `build_label_app.py` | **LIVE** | outputs present and dated |
| `core/analyse_results.py` | **PARTLY LIVE** — its `load()` is imported for label reconstruction; its *tables* are pilot-era and mis-report D3 (see §5.4) | `export_human_labels.py:45`, `nli_grounding_d3.py:39` |
| `rag_pipeline.py` (repo root) | **SUPERSEDED DUPLICATE** — lacks the `embeddings=` parameter the clean profile needs | `diff` vs `core/rag_pipeline.py`; root copy's `load_existing_vector_store` has no `embeddings` arg |
| `setup/01..03`, `doi_*`, `download_with_progress.py` | **HISTORICAL** — built the PDF corpus; not re-run for D3 | outputs dated 2026-05-27..05-29 |
| `setup/04_build_pilot_eval_set.py` | **SUPERSEDED** — writes `pilot_eval_set.json` (67 items), **not** `d3_eval_set.json` | `popularity_audit.md:69-75`; grep: no script writes `d3_eval_set.json` |
| `setup/05_evaluate_retrieval.py` | **SUPERSEDED** — defaults to the frozen index + pilot set | `05_evaluate_retrieval.py:104-106` |
| `core/inspect_contradictions.py`, `clean_index/validate_sample.py` | utilities, not on the result path | — |
| `staging_d3/` | **EMPTY** | `ls` returns nothing |
| **McNemar / Wilson-table producer for `analysis_d3.*`** | **DOES NOT EXIST** | grep for `mcnemar` across all `*.py` → zero hits (see §5.1) |
| **Hit@k producer for `retrieval_recall_d3.md`** | **DOES NOT EXIST** as a committed script | grep: no `.py` writes that file |
| **Inter-annotator producer for `interannotator_kj_aneesha.md`** | **DOES NOT EXIST** — the file itself says it was "computed inline" | `interannotator_kj_aneesha.md:6-9` |

### 0.3 Frozen result caches and their timestamps

| Artefact | mtime | What it is |
|---|---|---|
| `d3_eval_set.json` | 2026-07-09 21:38 | the 12 live eval items |
| `contradictions_cache_d3.json` | 2026-07-10 10:12 | 12 frozen Condition-D counterfactuals |
| `run_config_d3.json` | 2026-07-10 10:30 | reproducibility header for the live run |
| `results_d3.jsonl` | 2026-07-10 10:45 | **120 result cells** (authoritative) |
| `results_d3.csv` | 2026-07-10 10:52 | flattened export of the above |
| `analysis_d3.json` / `.md` | 2026-07-10 11:25 | Wilson + McNemar + slices (no producing script) |
| `human_label_sheet_d3.csv` / `human_label_key_d3.json` | 2026-07-11 16:16 | blind sheet + answer key |
| `nli_grounding_d3.json` / `.md` | 2026-07-11 20:25 | DeBERTa cross-check |
| `AneeshaGunaratne_full_labels_d3_20260717.csv` | 2026-07-18 16:32 | rater 2 labels |
| `KJ_full_labels_d3_20260718.csv` | 2026-07-18 20:19 | rater 1 labels |
| `judge_validation_d3.json` / `.md` | 2026-07-18 20:22 | **holds the KJ run** (script overwrites a fixed path) |
| `retrieval_recall_d3.md` | 2026-07-19 10:58 | Hit@k on the clean index |
| `d3_03_provenance.md` | 2026-07-21 22:58 | D3-03 source audit |
| — frozen pilot — | | |
| `pilot_eval_set.json`, `contradictions_cache.json`, `results_cache.jsonl`, `results.csv` | 2026-05-29 .. 06-01 (copies in `archive/frozen_study/` re-dated 2026-07-03) | the superseded 67-item / 335-cell study |

### 0.4 Which ChromaDB collection is live

```
chroma_db_clean/chroma.sqlite3   collection owf_clean_v1     dim 384   34,502 embeddings   501 distinct DOIs   <-- LIVE
chroma_db/chroma.sqlite3         collection wind_farm_papers dim 384   45,830 embeddings                       <-- frozen, read-only
archive/frozen_study/chroma_db/  copy of the above
```

`owf_clean_v1` is selected by the default retrieval profile (`conditions.py:81`, default
`"clean"`), confirmed in `run_config_d3.json:5-7`. Neither collection has a
`collection_metadata` row, so `hnsw:space` was never set and ChromaDB's **default L2**
applies — the distances in `retrieval_recall_d3.md` (0.27–0.57 on unit-norm vectors) are
consistent with squared L2. Rank order is identical to cosine either way.

---

## 1. System map — DOI discovery to the numbers in the results tables

```
                          ==== LAYER 1: CORPUS (historical, May–July 2026) ====

 [OWF_ScopusQueries.txt]    [hybrid_openalex_queries.json]   [OWF_WoS_Retry_Queries.txt]
            \                          |                              /
             +-------------------------+-----------------------------+
                                       v
   setup/doi_discovery_dualmode_clean_fixed_queryloader.py
        in : query files, OpenAlex/Crossref APIs
        out: dois_raw_*.txt, doi_sources*.txt, debug_rejections.tsv
                                       v
                            dois_merged_final.txt  (1,732 dedup DOIs — per methodology_capture.md:21)
                                       v
   setup/doi_download_only.py  +  setup/02_download_extra_sources.py
        (Unpaywall / OpenAlex / CORE / Semantic Scholar / arXiv)
        out: PDFs/*.pdf                    filename = DOI with non-word chars -> "_"
                                       v
   setup/01_clean_fake_pdfs.py  -> fake_pdfs_removed.txt
   setup/03_enrich_metadata.py  -> paper_metadata.json (OpenAlex, incl. citation_count)
   manual triage               -> TRIAGE_REPORT.md, wrong_pdf_candidates.csv (15 excluded)
                                       v
                              PDFs/  (523 .pdf on disk today)
                                       v
   core/clean_index/build_index.py   [GROBID 0.8.0 @ localhost:8070]
        grobid_client.process_fulltext -> TEI XML
        tei_parser.parse_tei           -> title/abstract/sections/captions, TEI <back> dropped
        chunking.build_documents       -> 1000/200 chars, SECTION-BOUNDED
        embeddings.build_embeddings    -> BAAI/bge-small-en-v1.5, query-prefix recipe, L2-normalised
        Chroma.from_documents / add_documents
        out: chroma_db_clean/  collection owf_clean_v1
             501 papers, 34,502 chunks   (7 GROBID failures skipped)
        log: owf_clean_v1_MANIFEST.md, owf_clean_v1_papers.csv, owf_clean_v1_build_checkpoint.jsonl

                          ==== LAYER 2: EVAL SET (hand-built) ====

   Eklipse report (Descriptor 3 findings)
        + manual verification against each primary paper
        + hand-written tags {compartment, answer_type, popularity}
                                       v
                            d3_eval_set.json   12 items, ids D3-01..D3-16 with gaps
        !! NO SCRIPT PRODUCES THIS FILE. setup/04_build_pilot_eval_set.py writes the
           SUPERSEDED pilot_eval_set.json (67 items) and emits no `tags` field at all.
        workbook: H1_gold_verification_workbook.md

                          ==== LAYER 3: THE EXPERIMENT (2026-07-10) ====

   core/build_contradictions.py           (RAG_EVAL_SET / RAG_CONTRADICTIONS_CACHE)
        get_oracle_chunks (oracle top-3 by claim_text)
        check_provenance  (8b, MATCH/MISMATCH)
        make_counterfactual (8b, temperature 0.4, max_tokens 600)
        verify_contradiction (8b, CONTRADICTS/CONSISTENT)
        out: contradictions_cache_d3.json   12/12 oracle-sourced, provenance True, verified True
                                       v
   core/run_experiment.py   for each (model_tag in {8b,70b}) x (item 0..11) x (cond in A,B1,B2,C,D)
        |
        +-- prepare_cell()            -> conditions.prepare_A/B1/B2/C/D  (retrieval + context, NO LLM)
        +-- build_prompt()            -> (system, user) exactly as sent
        +-- content_hash()            -> sha256 over model/cond/item/prompt/context_ids/k/temp/seed/extra
        +-- skip if hash already in results_d3.jsonl        (idempotent resume)
        +-- generate_answer()         -> Groq OpenAI-compatible /v1, temp 0.0, max_tokens 512
        +-- classifier.classify()     -> 8b judge: abstained -> correct -> grounded -> retrieval_hit
        +-- append one JSON line
        out: results_d3.jsonl (120 cells) ; run_config_d3.json
                                       v
   run_experiment.py --export results_d3.csv    (10 flat columns)

                          ==== LAYER 4: ANALYSIS & VALIDATION ====

   results_d3.csv --+--> [AD HOC, NO SCRIPT] --> analysis_d3.json / analysis_d3.md
                    |        Wilson CIs, McNemar (A vs B1, B1 vs B2), popularity/C/D slices
                    |        --> A 33% / B1 92% / B2 100% / C 17% / D 0/24, p=0.0001 etc.
                    |
                    +--> export_human_labels.py --> human_label_sheet_d3.csv (blind, shuffled)
                    |                               human_label_key_d3.json
                    |                               taxonomy_rubric.md
                    |         -> build_label_app.py -> label_app_d3_full.html
                    |         -> KJ + Aneesha label all 120 independently
                    |         -> score_judge_validation.py -> judge_validation_d3.{md,json}
                    |                                        (copied to judge_validation_kj.md /
                    |                                         judge_validation_aneesha.md)
                    |         -> [AD HOC] interannotator_kj_aneesha.md, judge_outlier_cells.md
                    |
                    +--> nli_grounding_d3.py (DeBERTa-v3-large-mnli, CPU) -> nli_grounding_d3.{md,json}
                    |
                    +--> [AD HOC, NO SCRIPT] -> retrieval_recall_d3.md  (Hit@5 0.667 / Hit@10 0.917)
                    |
                    +--> [AD HOC audits] popularity_audit.md, nli_explained.md, d3_03_provenance.md
```

---

## 2. Stage by stage

### 2.1 Discovery

**What it does.** `setup/doi_discovery_dualmode_clean_fixed_queryloader.py` loads
Boolean query blocks from the supervisor-supplied query files and runs them against
OpenAlex (and ingests Scopus / Web of Science exports), screening and de-duplicating
into a single DOI list. Rejections are logged to TSV so the screen is auditable. It ran
once, 2026-05-27 to 05-29; nothing in the D3 study re-runs it.

**Parameters in force.** Query sets: `OWF_ScopusQueries.txt`,
`hybrid_openalex_queries.json`, `OWF_WoS_Retry_Queries.txt`, `OWF_BirdsQuerySplit.txt`.
Outputs: `dois_raw_*.txt`, `doi_sources*.txt`, `dois_merged_final.txt`,
`debug_rejections.tsv` (92 KB), `debug_openalex_rescreen.tsv`. The "1,732 deduplicated
DOIs" figure is stated at `methodology_capture.md:21`; the counting step that produced it
is **not determinable from the repo** (no script emits that number).

**Design decisions.** Dual-mode (API + exported CSV) rather than API-only, so
subscription databases could contribute. Rejections logged rather than silently dropped.

**Failure modes handled / not handled.** Handled: duplicate DOIs across sources, a retry
pass for WoS (`*_wos_retry.txt`), a separate bird-descriptor split. Not handled: no
inter-rater screening of the inclusion decision — screening is single-pass and automated.

---

### 2.2 Download

**What it does.** `setup/doi_download_only.py` resolves each DOI to an open-access PDF
(Unpaywall / OpenAlex first), with `02_download_extra_sources.py` adding CORE, Semantic
Scholar and arXiv for the failures. Files land in `PDFs/` named by the DOI with every
non-word character replaced by `_`.

**Parameters in force.**
- Filename rule: `re.sub(r"[^\w\-_.]", "_", doi) + ".pdf"` — `core/clean_index/build_index.py:49`
- Reverse rule used at index time: **only the first `_` becomes `/`** —
  `build_index.py:45`, mirrored at `core/rag_pipeline.py:93`

**Design decisions.** DOI-as-filename makes the DOI the primary key for the whole
downstream pipeline with no separate manifest. The cost is the mangling below.

**Failure modes handled.** HTML paywall pages saved as `.pdf` are detected and removed
(`setup/01_clean_fake_pdfs.py` → `fake_pdfs_removed.txt`). `<100` chars of extracted text
counts as a failure.

**Failure modes NOT handled.** The filename rule is **lossy and irreversible in general**.
`10.1093/icesjms/fsy006` → `10.1093/icesjms_fsy006` is recoverable, and
`conditions.canonicalise_doi()` (`conditions.py:93-108`) inverts it on the query side. But
`10.1061/(ASCE)HY.1943-7900.0001443` → `10.1061/_asce_hy...` also loses parentheses and
case, which the canonicaliser does **not** cover. In the live index **68 of 501 DOIs**
carry an underscore after the first slash; **15** are OUP `10.1093/icesjms/*`, ~35 are
IOP/EDP/Metz-style multi-slash, and ~18 are Springer book chapters whose *true* DOI
legitimately contains `_`. `project_log.md:24` records 10 DOIs the canonicaliser cannot
reverse. **None of the 12 eval-set gold DOIs are affected beyond the recoverable
slash case** (verified: all 12 canonicalised DOIs resolve to chunks in `owf_clean_v1`).

---

### 2.3 GROBID parsing

**What it does.** `core/clean_index/grobid_client.py` POSTs each PDF to a local GROBID
`processFulltextDocument` endpoint; `tei_parser.parse_tei()` walks the returned TEI with
the stdlib `xml.etree.ElementTree`, keeping title (metadata), abstract, and every body
`<div>` that carries its own direct `<p>` children, plus every `<figure>/<figDesc>`
caption. TEI `<back>` is never read at all.

**Parameters in force.**
- GROBID URL / timeout: `http://localhost:8070`, 300 s — `clean_index/config.py:90-91`
- Image: `lfoppiano/grobid:0.8.0` — `build_index.py:91`, `owf_clean_v1_MANIFEST.md`
- Captions kept: `keep_captions = True` — `config.py:92`
- Drop-list (18 heading keywords: reference, bibliography, acknowledg, funding, grant,
  conflict of interest, competing interest, declaration of competing, author contribution,
  credit authorship, data availability, supplementary, supporting information, appendix,
  annex, ethics, consent to publish) — `config.py:31-37`, applied at `tei_parser.py:87-91,128-130`
- Section-label map (21 headings → 7 canonical labels) — `config.py:41-63`, applied at
  `tei_parser.py:73-84` with leading numbering stripped by regex (`tei_parser.py:78`)

**Design decisions.** GROBID's CRF structure over the earlier regex cleaner
(`core/rag_pipeline.py:128-148`), which left reference lists in the index — the reason the
frozen index has 45,830 chunks and the clean one only 34,502. Direct-child `<p>` iteration
only (`tei_parser.py:131-134`), so a paragraph belongs to exactly one unit and nested divs
never duplicate text. The DOI comes from the **filename**, not from GROBID's own
`<idno type="DOI">` — the TEI DOI is parsed (`tei_parser.py:108-111`) but stored only as a
cross-check field and is never used downstream.

**Failure modes handled.** GROBID 500s and malformed TEI are caught separately
(`build_index.py:132-141`), appended to a failure log **and** a skip list, and the build
continues. 7 PDFs failed this way; the authoritative list is in `owf_clean_v1_MANIFEST.md`.

**Failure modes NOT handled.** Table grids are deliberately not reconstructed — a table
contributes its caption only (`tei_parser.py:14-15`). Running headers/footers are assumed
handled by GROBID upstream, not verified here. One PDF with glyph-encoded digits
(`10.3389/fclim.2024.1353939`) had to be re-extracted with **pymupdf outside this
pipeline**, producing 100 chunks with **no section structure** — a one-off exception
recorded in the manifest but not implemented in the code. The build logs
(`clean_index_failures.log`, `clean_index_skiplist.txt`) named at `config.py:98-99`
**do not exist on disk today**; the manifest is the only surviving record.

---

### 2.4 Chunking

**What it does.** `chunking.build_documents()` splits each unit (abstract, then each body
section, then each caption) **independently**, so a chunk can never straddle a section
boundary. Chunk indices run continuously across the whole paper; `total_chunks` is
stamped after the fact.

**Parameters in force.**
- `chunk_size = 1000`, `chunk_overlap = 200` characters — `config.py:86-87`
- Splitter: `RecursiveCharacterTextSplitter`, `length_function=len`,
  `separators=["\n\n", "\n", ". ", " ", ""]`, `is_separator_regex=False` — `chunking.py:22-29`
- Per-chunk metadata: `doi, title, source, section, section_head, is_caption,
  caption_kind, chunk_index, total_chunks` — `chunking.py:52-61,81`
- Chunk id: `md5(f"{doi}_{idx}")[:12]` — `build_index.py:53`

**Design decisions.** Section-bounded over whole-paper splitting: chosen because the
frozen index let chunks run from one section into the next, and from body text straight
into a reference list. Captions kept as their own units because in this literature the
quantitative finding often lives in a table or figure caption. Character-based (not
token-based) sizing was retained from the pilot for continuity.

**Failure modes handled.** Empty pieces are dropped (`chunking.py:47-49`). A paper with no
parseable body still yields its abstract.

**Failure modes NOT handled.** 1000 characters is ~150–200 words — a chunk can end
mid-sentence when no separator fits. There is no minimum chunk length, so a one-line
section becomes a chunk of its own. Section-bounding also means a finding split across a
results paragraph and its table caption lands in two chunks that may not both be retrieved.

---

### 2.5 Embedding and indexing

**What it does.** `embeddings.build_embeddings()` returns a single
`HuggingFaceBgeEmbeddings` object used at **both** index time and query time, which is the
whole point of putting it in one module. `build_index.build()` batches documents into
Chroma with explicit deterministic ids.

**Parameters in force.**
- Model: `BAAI/bge-small-en-v1.5`, 384-dim (confirmed in the sqlite `collections` row) — `config.py:79`
- **Query prefix:** `"Represent this sentence for searching relevant passages:"` — `config.py:26,80`
- **Passage prefix:** `""` (passages embedded plain) — `config.py:81`
- Normalisation: `normalize_embeddings = True` — `config.py:82`
- Device: `cpu` — `config.py:83`
- Batch size: 50 — `config.py:97`, used at `build_index.py:154`
- Collection / dir: `owf_clean_v1` in `chroma_db_clean/` — `config.py:75-76`
- Distance metric: **never set**, so ChromaDB's default L2 applies (no `collection_metadata`
  row exists in either sqlite file). On unit-norm vectors this is order-equivalent to cosine.

**Design decisions.** The BGE *asymmetric* recipe (instruction on queries only) replaced
the pilot's symmetric no-prefix recipe — `config.py:23-25` calls this "the single biggest
retrieval fix versus the frozen index". A **new** collection in a **separate** directory
rather than an in-place rebuild, so the frozen study stays byte-comparable
(`config.py:11-13`). Ids are content-independent (`md5(doi_idx)`), so re-running the build
over the same paper overwrites rather than duplicates.

**Failure modes handled.** Extraction failures never silently drop a paper — logged and
skip-listed. `--dry-run` parses and chunks without importing torch or chromadb.

**Failure modes NOT handled.** The id scheme keys on `(doi, chunk_index)`, so if a paper is
re-extracted with a *different* number of chunks, stale high-index chunks from the previous
build are left behind rather than deleted. There is no assertion that the query-side
embedding object matches the one used at index time — it is enforced only by convention
(both call `build_embeddings(default_config())`).

---

### 2.6 Retrieval

**What it does.** `conditions.retrieve()` (`conditions.py:140-178`) is the single retrieval
call every document condition goes through. It loads a process-wide singleton store
(`get_store()`, `conditions.py:130-137`), runs `similarity_search_with_score`, optionally
drops chunks whose source DOI is in an exclude set, and returns exactly `k` records of
`{text, doi, chunk_index, score}`.

**Parameters in force.**
- `k = 5` everywhere in the experiment — `run_experiment.py:96` (`DEFAULT_K = 5`), passed
  through `prepare_cell(..., k=DEFAULT_K)` at `run_experiment.py:152`
- Profile: `RAG_RETRIEVAL_PROFILE`, default `"clean"` — `conditions.py:81`
- Profile table (db_dir / collection / embeddings builder) — `conditions.py:66-79`
- Over-fetch when excluding: `fetch_k = k + 10` — `conditions.py:162`
- Score semantics: `float(score)` with the comment "Chroma distance: lower = more
  similar" — `conditions.py:174`
- DOI canonicalisation before matching: `conditions.py:93-108`

**Design decisions.** Reusing one `retrieve()` for B1 and C guarantees the two conditions
differ only in the query string and the exclusion, not in the retrieval mechanics. The
store is cached in a module global so the 384-dim model loads once per process.
Over-fetching by a fixed +10 rather than looping until `k` survive.

**Failure modes handled.** Multi-slash DOI mangling (canonicalisation on the query side
only — stored data is never mutated). Exclusion is applied per **chunk**, so no chunk of an
excluded paper survives.

**Failure modes NOT handled.** `fetch_k = k + 10` is a fixed budget: if more than 10 of the
top 15 chunks belong to excluded papers, `retrieve()` silently returns **fewer than k**
chunks with no warning. (It did not bite in this run — all 24 C cells have exactly 5
context docs, verified in `results_d3.jsonl`.) There is no MMR, no re-ranking, no
deduplication by paper: `retrieval_recall_d3.md` shows D3-07 returning **all ten** top
chunks from the same paper.

---

### 2.7 Condition construction

Covered in full in §3.

---

### 2.8 Generation

**What it does.** `llm_generation.complete()` is the one HTTP call site for everything —
subject answers, judge calls, counterfactual construction. `build_prompt()` selects
between the two system prompts and numbers the documents.

**Parameters in force.**
- Provider: `LLM_BASE_URL` else `https://api.groq.com/openai/v1` — `llm_generation.py:45,83`
- Key: `LLM_API_KEY` else `GROQ_API_KEY` — `llm_generation.py:84`
- Subject models: `8b = llama-3.1-8b-instant`, `70b = llama-3.3-70b-versatile` —
  `run_experiment.py:87-90`
- `temperature = 0.0` — `llm_generation.py:49`, re-exported as `run_experiment.py:97`
- `max_tokens = 512` — `llm_generation.py:50`, `run_experiment.py:98`
- `seed = None` (unset) — `run_experiment.py:99`
- Retries: 5, exponential backoff starting at 2 s and doubling — `llm_generation.py:176-199`

**Design decisions.** One `complete()` with a pluggable system prompt rather than separate
clients — so the judge and the subject provably share transport, retry and temperature
handling. The provider is env-selected so Groq's 2026-08-16 retirement of these models
does not require a code edit (`run_experiment.py:84-86`). The determinism claim is made
honestly and recorded in the artefact itself (`run_experiment.py:261-268` →
`run_config_d3.json:53`): greedy at temperature 0 is **not** bit-deterministic without a
seed, so results are "reproducible in distribution, not bit-identical".

**Failure modes handled.** `RateLimitError` and `APIError` both back off and retry; after 5
attempts a `RuntimeError` propagates, and `run_experiment.py:421-426` catches it, prints
progress and exits **0** so a daily-cap stop is not mistaken for a crash. The append-only
JSONL means a hard kill loses at most one line, and `load_done_hashes()` tolerates a torn
final line (`run_experiment.py:217-218`).

**Failure modes NOT handled.** A non-rate-limit, non-API exception (network reset,
`resp.choices` empty) is not caught and aborts the run. There is no per-call token
accounting. `max_tokens=512` truncation is not detected — a truncated answer is judged as
though complete.

---

### 2.9 Classification (the judge)

Covered in full in §4.

---

### 2.10 Analysis

**What it does.** `core/analyse_results.py` reads a flat results CSV and prints four
tables: outcome distribution by condition, RQ1 rates with Wilson intervals, a B1-vs-B2
contrast, and an RQ2 failure decomposition. Its `load()` function is also imported by
`export_human_labels.py` and `nli_grounding_d3.py` as the single definition of the six-way
label, so the human sheet and the NLI cross-check cannot drift from the tables.

**Parameters in force.**
- `EXCLUDE = {2, 34, 45}` — `analyse_results.py:50`
- `CONDITIONS`, `OUTCOMES` — `analyse_results.py:52-55`
- Wilson `z = 1.96` — `analyse_results.py:58`
- Label rule `failure_type or "correct"` — `analyse_results.py:79`
- Default CSV: `results.csv` (the **pilot**) — `analyse_results.py:224`

**Design decisions.** Wilson rather than the normal approximation, explicitly because n is
small and proportions are extreme. `no_answer` cells are dropped from rate denominators
(`analyse_results.py:119-120`) on the grounds that the model was never asked. Every
filtered number is printed alongside its unfiltered twin.

**Failure modes handled.** Empty denominators return `(0,0,0)` from `wilson()`.

**Failure modes NOT handled — and these matter.** The script is pilot-era and produces
**wrong or misleading output on the D3 data**. See `discrepancies.md` §6 items D1–D5. In
particular it pools 8b and 70b into one denominator with no model split, its `EXCLUDE` set
silently drops a valid D3 item, its paired B1/B2 comparison collapses 24 rows to 12, and it
prints "all 67 items" over a 12-item run.

---

## 3. The five conditions, exactly

All five go through the same generation call; only the `context` argument differs.
`run_experiment.prepare_cell()` (`run_experiment.py:152-185`) is the single dispatch point.

### The two prompt templates — verbatim

**Parametric system prompt (Condition A only)** — `llm_generation.py:65-69`:

```
You are a scientific question-answering assistant for offshore wind farm environmental research. Answer the question concisely and factually. If you are not sure, say so rather than guessing.
```

The user message for A is **the bare question string**, nothing else (`llm_generation.py:111`).

**Grounded system prompt (B1, B2, C and D — byte-identical across all four)** —
`llm_generation.py:57-62`:

```
You are a scientific question-answering assistant for offshore wind farm environmental research. Answer the question using ONLY the information in the provided documents. If the documents do not contain the answer, say so explicitly rather than guessing. Be concise and factual.
```

**Grounded user message template** — `llm_generation.py:116-126`:

```
Documents:
[Document 1]
<chunk 1 text, .strip()ed>

[Document 2]
<chunk 2 text>

... (blank line between documents)

Question: <question>

Answer based only on the documents above.
```

This identity across B1/C/D is the design's load-bearing control and is stated as such at
`llm_generation.py:13-14`. Note the consequence: **Condition D receives the same "use ONLY
the documents" instruction as B1**, so D measures instruction-following-under-conflict, not
unprompted credulity.

---

### Condition A — no documents

`prepare_A()`, `conditions.py:214-217`:

```python
def prepare_A(question):
    public = {"condition": "A", "question": question, "context_docs": [], "retrieved_meta": []}
    return public, None
```

`gen_context = None` flows to `build_prompt(question, None)` → `llm_generation.py:110-111`
returns `(PARAMETRIC_SYSTEM_PROMPT, question)`. No retrieval call is made at all.
Verified: all 24 A cells in `results_d3.jsonl` have `context_docs == []`.

---

### Condition B1 — standard RAG

`prepare_B1()`, `conditions.py:228-234`:

```python
def prepare_B1(question, k=5):
    retrieved = retrieve(question, k=k)
    context = [r["text"] for r in retrieved]
    ...
```

The **raw item question** is the query — no rewriting, no expansion, no HyDE. `k=5` from
`run_experiment.py:96`. No exclusions. Verified: all 24 B1 cells have exactly 5 context
docs.

---

### Condition B2 — oracle

**What B2 restricts to, and by what mechanism** — `prepare_B2()`, `conditions.py:277-308`:

```python
store = get_store()
if isinstance(gt_dois, str):
    gt_dois = [gt_dois]
gt_dois = [canonicalise_doi(d) for d in gt_dois]                       # :290
flt = {"doi": gt_dois[0]} if len(gt_dois) == 1 else {"doi": {"$in": gt_dois}}   # :291
docs_scores = store.similarity_search_with_score(question, k=k, filter=flt)     # :293
```

The mechanism is a **ChromaDB metadata `where` filter on the `doi` field**, applied inside
the vector search — *not* a post-hoc drop, and *not* `conditions.retrieve()`. B2 therefore
bypasses the corpus-wide ranking entirely: it ranks only chunks of the gold paper(s).
Every D3 item has exactly one `matched_dois` entry, so the single-DOI branch (`{"doi": ...}`)
was taken for all 12.

Canonicalisation at `:290` is what makes the four OUP-style gold DOIs findable
(`10.1093/icesjms/fsy006` → `10.1093/icesjms_fsy006`).

**When the paper is absent:** `:294-297` returns `oracle_available=False` and
`gen_context=None`; `run_experiment.py:169` sets `can_generate=False`, `run_prepared()`
writes `answer=None`, and `classifier.classify()` labels it `no_answer`
(`classifier.py:113-115`). **This path never fired in the D3 run** — all 12 gold papers are
indexed, and there are zero `no_answer` cells.

**Verified with zero exceptions:** every one of the 120 `retrieved_meta` entries across the
24 B2 cells carries the item's own canonicalised gold DOI. No leakage.

---

### Condition C — irrelevant documents

`prepare_C()`, `conditions.py:245-264`:

```python
if seed is not None:
    random.seed(seed)                                     # :257-258
dq = distractor_query or random.choice(DISTRACTOR_QUERIES)  # :259
retrieved = retrieve(dq, k=k, exclude_dois=gt_dois)         # :260
```

The seed is the **item index**, passed at `run_experiment.py:173`
(`prepare_C(question, k=k, gt_dois=gt_dois, seed=item_idx)`).

**How distractors are selected.** A fixed hand-written list of **10** off-topic queries
spanning the D1–D11 MSFD descriptors — `conditions.py:114-125`:

```
non-indigenous species colonising offshore wind turbine foundations
marine litter accumulation around offshore installations
eutrophication and nutrient enrichment in coastal seas
seabed sediment disturbance during foundation installation
contaminant release from anti-corrosion coatings on turbines
food web changes from artificial reef effects
hydrological regime and current patterns near wind farms
commercial fish stock displacement by wind farm exclusion zones
seabird collision risk with turbine rotors
electromagnetic fields from subsea cables and elasmobranchs
```

One is chosen at random, seeded by item index, then run through the *same* retriever as B1.
The returned chunks are therefore **real, fluent, on-corpus scientific text** — a harder
test than random noise, which is the stated rationale (`conditions.py:110-113`).

**What prevents topical collision with the real answer — and what does not.**

The **only** guard is DOI-level exclusion of the item's own gold paper(s):
`retrieve(dq, k=k, exclude_dois=gt_dois)` at `:260` → canonicalised into an exclude set at
`conditions.py:153-160` → chunk-level drop at `:167-168`. Verified working: **zero** C cells
contain a chunk from their own gold DOI.

**There is no topic-level check of any kind.** No embedding-distance floor between the
distractor query and the item question, no compartment/tag exclusion, no check that the
retrieved chunks fail to support the claim. Two consequences are visible in the frozen data:

1. **The seeded pick is not uniform across items.** `random.seed(i)` + `random.choice` over
   a 10-item list gives only **6 distinct queries across the 12 items**. Items 3, 4 and 8
   (D3-04, D3-05, D3-10) all drew *"seabed sediment disturbance during foundation
   installation"* and received **byte-identical distractor contexts**; items 5, 6 and 10
   (D3-07, D3-08, D3-12) all drew the EMF query and likewise; items 9 and 11 (D3-11, D3-16)
   both drew the exclusion-zone query. So the 24 C cells span 6 contexts, not 12.

2. **At least one item's "irrelevant" context is topically on-point.** D3-11 asks
   *"Within the closed areas of offshore wind farms, how does the reduced fishing pressure
   affect fish biomass?"* and drew the distractor *"commercial fish stock displacement by
   wind farm exclusion zones"* — the same subject. Its five distractor chunks came from
   `10.1007/s10750-014-1997-z` (×2, which is **D3-10's** gold paper),
   `10.1016/j.marpol.2009.12.004`, `10.1093/icesjms_fsac107` (**D3-09's** gold paper) and
   `10.1016/j.jmarsys.2020.103434`. The exclusion only removes *this* item's gold, so
   another item's gold paper — which may assert the same finding — is free to enter.
   D3-09's C context likewise contains D3-03's and D3-02's gold papers.

   D3-11 (8b) is one of the four cells counted as "correct under irrelevant context".

---

### Condition D — contradictory document

`prepare_D()`, `conditions.py:322-333`:

```python
def prepare_D(question, contradiction_text):
    context = [contradiction_text]
    public = {"condition": "D", "question": question, "context_docs": context,
              "retrieved_meta": [{"doi": "SYNTHETIC_COUNTERFACTUAL", "chunk_index": None, "score": None}]}
    return public, context
```

**Exactly one document**, never retrieved, always loaded from the frozen cache. The runner
looks it up by **string item index** (`run_experiment.py:176`,
`contradictions.get(str(item_idx))`) and hashes the text into the cache key
(`run_experiment.py:183`), so editing a counterfactual forces regeneration rather than a
silent reuse. A missing entry yields `can_generate=False` → `answer=None` → `no_answer`
(`run_experiment.py:177-180`). That path did not fire.

**How the counterfactual is produced** — `build_contradictions.py`, one-time, per item:

1. `get_oracle_chunks(store, claim_text, gt_dois, k=3)` — `:73-89`. Note it queries by
   **`claim_text`**, not by the question, deliberately (`:75-77`), and canonicalises the DOIs.
2. `check_provenance(claim_text, chunks)` — `:114-126`, an 8b MATCH/MISMATCH call with a
   3-example few-shot prompt (`PROVENANCE_SYSTEM`, `:92-111`) biased to answer MATCH when
   unsure. Failure → `source="provenance_mismatch"` and the claim text is used as the style
   source instead of the paper.
3. `make_counterfactual(question, original, claim_text)` — `:144-156`. **temperature 0.4,
   max_tokens 600**, source passage truncated to `original[:900]` so a long chunk cannot be
   parroted.
4. `verify_contradiction(claim_text, counterfactual)` — `:159-162`, an 8b
   CONTRADICTS/CONSISTENT call at temperature 0.

The counterfactual system prompt verbatim — `build_contradictions.py:129-141`:

```
You construct counterfactual passages for a controlled NLP evaluation. You are given a QUESTION, the TRUE CLAIM (the correct answer), and a SOURCE passage for style. Write a single self-contained passage that reads like a scientific finding but asserts the DIRECT OPPOSITE of the true claim -- flip its key fact (reverse the direction, invert the magnitude, or negate the conclusion). The passage MUST explicitly state the opposite finding in a complete sentence; do not merely copy the source, trail off, or change the subject. Keep it self-contained and roughly 3-6 sentences. Do NOT include acknowledgements, funding text, figure/table references, or citations to unrelated work. Do NOT add any disclaimer or note that it is altered. Output ONLY the passage.
```

Verify prompt — `build_contradictions.py:67-70`:

```
You judge whether a passage contradicts a claim on its key fact. Reply with exactly one word: CONTRADICTS or CONSISTENT. No other text.
```

**What the frozen cache actually holds.** `contradictions_cache_d3.json`, 12 entries keyed
`"0"`–`"11"`, each with `question, claim_text, gt_dois, source, provenance_supported,
oracle_preview, original, contradiction, verified`. Every one of the 12:

- `source = "oracle"` (none fell back to claim text, none flagged provenance mismatch)
- `provenance_supported = true`
- `verified = true`
- `contradiction` length 543–901 characters

`project_log.md:16` records that D3-03 and D3-04 were regenerated on 2026-07-10 as
single-direction negations, before the run.

**One honest caveat visible in the cache:** D3-03's counterfactual reproduces two full
sentences of the source passage verbatim (including the real study identifier
"Courseulles-sur-mer offshore wind farm") and flips only the verb — despite the prompt's
"do not merely copy the source". It does assert the opposite finding, so it is functionally
valid, but it is not an independently-written passage.

---

## 4. The judge

### 4.1 Model and settings

- Model: `llama-3.1-8b-instant` — `classifier.py:39` (`JUDGE_MODEL`)
- `temperature = 0.0`, `max_tokens = 5` on **every** judge call — `classifier.py:74,80,86,92`
- Same transport, retry and backoff as the subject (`llm_generation.complete()`)
- Recorded in the artefact at `run_config_d3.json:17` (`"judge": "llama-3.1-8b-instant"`)

The 8B choice is justified in-code at `classifier.py:40-44` on free-tier grounds: the 70B
daily cap (~100k tokens) cannot support thousands of judge calls, and these are one-word
judgments. The role separation is explicit: subject varies, judge and D-builder are pinned
(`run_experiment.py:79-83`).

### 4.2 The four sub-judgments — prompts verbatim

`_ABSTAIN_SYS` — `classifier.py:46-51`:
```
Decide whether the ANSWER declines to give a factual answer -- e.g. it says the information is not in the documents, it cannot determine it, or it does not know -- as opposed to asserting a substantive answer. Reply with exactly one word: ABSTAIN or ANSWER.
```

`_CORRECT_SYS` — `classifier.py:52-56`:
```
Judge whether the ANSWER is factually consistent with the reference CLAIM on its key fact (direction, magnitude, or conclusion). Minor wording differences are fine. Reply with exactly one word: CORRECT or INCORRECT.
```

`_GROUNDED_SYS` — `classifier.py:57-62`:
```
Judge whether the ANSWER is supported by (derivable from) the PASSAGES. If the answer's key assertion comes from the passages, it is GROUNDED; if it asserts things absent from the passages, it is UNGROUNDED. Reply with exactly one word: GROUNDED or UNGROUNDED.
```

`_HIT_SYS` — `classifier.py:63-66`:
```
Judge whether the PASSAGES contain information that addresses the CLAIM's finding (same subject and variable). Reply with exactly one word: HIT or MISS.
```

User messages: `f"Answer:\n{answer}"`; `f"Reference claim:\n{claim_text}\n\nAnswer:\n{answer}"`;
`f"Passages:\n{_join(context_docs)}\n\nAnswer:\n{answer}"`;
`f"Claim:\n{claim_text}\n\nPassages:\n{_join(context_docs)}"` — `classifier.py:74,79,85,91`.
`_join` numbers passages `[1] … [2] …` (`classifier.py:69-70`) — note this differs from the
generation-side `[Document 1]` numbering.

### 4.3 The label set

Six labels, defined at `classifier.py:9-17` and mirrored for the human raters in
`taxonomy_rubric.md`, plus a seventh bookkeeping value:

| label | when |
|---|---|
| `correct` | stored as **empty `failure_type`**, reconstructed by `analyse_results.load()` |
| `abstention` | judge says ABSTAIN |
| `parametric_error` | wrong, Condition A only |
| `retrieval_failure` | wrong, B1/B2 only, and `retrieval_hit` is MISS |
| `grounded_but_wrong` | wrong, has context, judged GROUNDED |
| `ungrounded_hallucination` | wrong, has context, judged UNGROUNDED |
| `no_answer` | `answer is None` (B2 oracle absent, or D entry missing) — never fired in D3 |

### 4.4 Decision order and short-circuiting

`classify()`, `classifier.py:96-143`:

```
answer is None                -> no_answer                        (:113-115)
judge_abstained -> True       -> abstention                       (:118-121)
judge_correct   -> True       -> failure_type = None (= correct)   (:123-126)
condition == "A"              -> parametric_error                 (:129-131)
judge_grounded                                                     (:135)
condition in (B1, B2): judge_retrieval_hit; if MISS -> retrieval_failure  (:136-140)
else: grounded_but_wrong if grounded else ungrounded_hallucination (:142)
```

Cost: 1 call for an abstention, 2 for a correct answer, 3 for a wrong C/D cell, 4 for a
wrong B1/B2 cell. Condition-awareness is deliberate (`classifier.py:19-23`): calling
"context lacks the answer" a *retrieval failure* is meaningless in C and D where the
context is wrong by design.

### 4.5 Parsing, and what happens on a malformed response

Every judge parses the same way — e.g. `classifier.py:75`:

```python
return v.strip().upper().startswith("ABSTAIN")
```

`.strip().upper().startswith(<POSITIVE_TOKEN>)`. So:

- **There is no out-of-vocabulary detection and no retry on a bad label.** Anything that
  does not start with the positive token is silently read as the negative class.
- `"The answer is CORRECT"` → parsed as **INCORRECT**. `"Correct."` → parsed as CORRECT
  (case-folded). `""` → negative. `"GROUNDED (mostly)"` → GROUNDED.
- The asymmetry is mitigated by `max_tokens=5`, which makes a preamble unlikely, and by
  the fact that `"INCORRECT"` does not start with `"CORRECT"` (so no false positive there).
- The failure direction is **conservative on correctness** (a malformed reply scores the
  answer wrong) and **conservative on grounding** (a malformed reply pushes toward
  `ungrounded_hallucination`).
- No raw judge string is stored — only the boolean. So a malformed reply is
  **unrecoverable after the fact**; you cannot audit how many occurred. There were zero
  `ungrounded_hallucination` labels in the whole D3 run, which is consistent with (but not
  proof of) no parse failures.

### 4.6 How `grounded` is recorded — including the abstention convention

The field is **only** written when the code reaches `classifier.py:135`. Everywhere else it
retains the `None` set at `:110-111`. Verified against all 120 cells in `results_d3.jsonl`:

| condition | grounded | abstained | correct | retrieval_hit | failure_type | n |
|---|---|---|---|---|---|---|
| A | `None` | False | True | `None` | correct | 8 |
| A | `None` | False | False | `None` | parametric_error | 1 |
| A | `None` | **True** | `None` | `None` | abstention | 15 |
| B1 | `None` | False | True | `None` | correct | 22 |
| B1 | `None` | **True** | `None` | `None` | abstention | 1 |
| B1 | **False** | False | False | **False** | retrieval_failure | 1 |
| B2 | `None` | False | True | `None` | correct | 24 |
| C | `None` | False | True | `None` | correct | 4 |
| C | `None` | **True** | `None` | `None` | abstention | 20 |
| D | **True** | False | False | `None` | grounded_but_wrong | 24 |

**The convention applied to abstentions: `grounded` is left `null`, never `false`.** An
abstention returns at `classifier.py:120-121` before any grounding call. The same is true
of `correct` cells (return at `:125-126`) and all Condition A cells (return at `:130-131`).

Consequences you should state before an examiner finds them:

- `grounded` is populated on only **25 of 120 cells** (24 D + the single B1
  `retrieval_failure`). Every downstream grounding statistic is over that 25, not over 120.
- `correct` is `null` on abstentions — correctness was never assessed for them. Treating
  abstention as "not correct" in the tables is a **downstream convention**
  (`analysis_d3.md:3`), not a judge output.
- `retrieval_hit` is populated on exactly **one** cell, so Hit-as-judged is not a usable
  statistic; the retrieval-quality evidence is the separate Hit@k measurement (§5.5).
- The one `retrieval_failure` cell has `grounded=False` recorded even though the label is
  `retrieval_failure` — grounding is computed at `:135` *before* the hit test at `:137`.

---

## 5. Statistics — which test, applied to what, computed where

### 5.1 McNemar exact test — **NOT REPRODUCIBLE FROM ANY SCRIPT IN THIS REPO**

A repo-wide grep for `mcnemar`, `binomtest`, `binom_test` across every `.py` file returns
**zero hits**. The McNemar results exist only as *text* in `analysis_d3.md:24-43` and
`analysis_d3.json:152-212`. `project_log.md:18` records that they were produced, but the
producing code was never written to disk.

**What is reported** (`analysis_d3.md:26-33`) — six rows, not four:

| comparison | scope | b | c | discordant n | chi2 (cc) | p (exact) |
|---|---|---|---|---|---|---|
| A vs B1 | pooled | 0 | 14 | 14 | 12.0714 | 0.0001 |
| A vs B1 | 8b | 0 | 8 | 8 | 6.125 | 0.0078 |
| A vs B1 | 70b | 0 | 6 | 6 | 4.1667 | 0.0312 |
| B1 vs B2 | pooled | 0 | 2 | 2 | 0.5 | 0.5 |
| B1 vs B2 | 8b | 0 | 1 | 1 | 0.0 | 1.0 |
| B1 vs B2 | 70b | 0 | 1 | 1 | 0.0 | 1.0 |

**Which pairs it runs on:** only **A vs B1** and **B1 vs B2**, each pooled across models and
split by model. Pairing is **within item, across condition**, with the same subject model.
There is **no** McNemar for A vs C, B1 vs C, or anything involving D.

**Recomputed by hand from `results_d3.jsonl` during this audit and confirmed correct:**
- A correct = 8, B1 correct = 22, discordant b(A-only)=0 / c(B1-only)=14, and 8+14 = 22 ✓
- Continuity-corrected chi-square `(|b−c|−1)²/(b+c)`: 13²/14 = 12.0714 ✓, 7²/8 = 6.125 ✓,
  5²/6 = 4.1667 ✓, 1²/2 = 0.5 ✓, 0²/1 = 0.0 ✓
- Exact two-sided binomial with b=0: `2 × 0.5^c` → 2·2⁻¹⁴ = 0.000122 ✓, 2·2⁻⁸ = 0.0078 ✓,
  2·2⁻⁶ = 0.03125 ✓, 2·0.25 = 0.5 ✓, 2·0.5 = 1.0 ✓

So the **numbers are arithmetically right and re-derivable from the frozen cache by hand**
— but not by running anything in this repo. The pooled test also treats the 8b and 70b
observations on the same item as independent pairs, which they are not (see
`viva_questions.md` Q7).

### 5.2 Wilson interval — `analyse_results.py:58-67`

```python
def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0, 0.0)
    p = k / n
    denom  = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denom
    half   = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))
```

Standard Wilson score interval, no continuity correction, `z = 1.96` hard-coded, clamped to
[0,1]. `analysis_d3.json:16` records `wilson_z = 1.959963984540054` (the exact normal
quantile) rather than 1.96, so the ad-hoc analysis script used a slightly more precise z
than `analyse_results.py` does — differences are in the third decimal and do not change any
reported interval.

Applied to: per-condition correctness (pooled and per model) in `analysis_d3.md:9-20`, and
to every rate `analyse_results.print_rq1()` prints. **Not** applied to any agreement metric.

### 5.3 Cohen's kappa and PABAK — `score_judge_validation.py:73-93`

```python
def cohen_kappa(pairs):                       # :73-85
    n = len(pairs)
    cats = sorted(set(a for a,_ in pairs) | set(b for _,b in pairs))
    k  = len(cats)
    po = sum(1 for a,b in pairs if a == b) / n
    ca, cb = Counter(a for a,_ in pairs), Counter(b for _,b in pairs)
    pe = sum((ca[c]/n) * (cb[c]/n) for c in cats)
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 1e-12 else None
    return (po, pe, kappa, n, k)

def pabak(po, k):                             # :88-93
    return (k*po - 1) / (k - 1)               # reduces to 2*po - 1 when k == 2
```

Textbook Cohen's kappa, unweighted. `pe` sums over the union of categories seen in *either*
rater's marginal, so a category used by only one rater still contributes. Degenerate
marginals return `kappa = None` rather than dividing by zero — which is why the grounding
row reads "undefined". PABAK uses Byrt's multi-category generalisation for the six-way row
(k = number of categories *observed*, which was 5, not 6) and the binary form 2·p₀−1 for the
two binary rows; this is stated in the output at `score_judge_validation.py:209-212`.

**Computed on three things** (`score_judge_validation.py:140-186`):
1. six-way `human_label` vs `judge_label` over all 120 rows
2. binary `correct` vs `not_correct` over all 120 rows
3. the grounding decision, restricted to rows where `judge_grounded is not None`
   (`:167-168`) — which is only 25, minus 1 blank = **24**

Plus per-condition *observed agreement only* (no kappa) at `:178-186`.

A near-identical implementation lives in `nli_grounding_d3.py:138-152` for the NLI-vs-judge
comparison, with a binary-only PABAK.

**Results as frozen:**

| pairing | metric | n | observed | kappa | PABAK | source |
|---|---|---|---|---|---|---|
| KJ vs judge | six-way | 120 | 0.9250 | 0.8838 | 0.9062 | `judge_validation_d3.json:5-12` |
| KJ vs judge | binary | 120 | 0.9417 | 0.8829 | 0.8833 | `judge_validation_d3.json:59-64` |
| KJ vs judge | grounding | 24 | 1.0 | **null (degenerate)** | 1.0 | `judge_validation_d3.json:65-72` |
| Aneesha vs judge | six-way | 120 | 0.9167 | 0.8725 | 0.8958 | `judge_validation_aneesha.md:45` |
| Aneesha vs judge | binary | 120 | 0.95 | 0.8996 | 0.90 | `judge_validation_aneesha.md:46` |
| KJ vs Aneesha | six-way | 120 | 0.9583 | 0.9369 | 0.9444 | `interannotator_kj_aneesha.md:24` |
| KJ vs Aneesha | binary | 120 | 0.975 | 0.9492 | 0.95 | `interannotator_kj_aneesha.md:25` |
| KJ vs Aneesha | grounding | 72 | 1.0 | **undefined** | 1.0 | `interannotator_kj_aneesha.md:26` |
| NLI vs judge | grounding | 25 | 0.80 | 0.2331 | 0.60 | `nli_grounding_d3.md:11-15` |

Reproducibility: the three **judge-vs-human** rows run from `score_judge_validation.py`.
The **KJ-vs-Aneesha** rows do not — `interannotator_kj_aneesha.md:6-9` states the scorer's
functions "were imported, not reimplemented, computed inline because the scorer only
supports human-vs-key joins, not human-vs-human." No such script exists on disk. Same for
`judge_outlier_cells.md`.

Also note `score_judge_validation.py:39-40` writes to **fixed** paths `judge_validation_d3.md`
/ `.json` regardless of `--sheet`. Running it for Aneesha then KJ overwrote the first
result; the surviving `judge_validation_d3.*` is the **KJ** run, and the per-rater `.md`
files are hand-written transcriptions with extra sections the scorer never emits.

### 5.4 What `analyse_results.py` computes — and its limits on D3

It computes **no significance test at all** — only Wilson intervals and raw counts. Running
it unmodified on `results_d3.csv` (done read-only during this audit) reproduces
A 33.3% / B1 91.7% / B2 100% / C 16.7% and D 0%, but with four defects documented as
D1–D5 in `discrepancies.md`: pilot `EXCLUDE` set applied to D3 (D reported 22/22 rather than
24/24), "all 67 items" printed over 12, no model split, and a paired B1/B2 comparison that
silently discards the 8b half of the data.

### 5.5 Hit@k — `retrieval_recall_d3.md`

Hit@1 = Hit@3 = Hit@5 = 8/12 = **0.667**; Hit@10 = 11/12 = **0.917**. Definition: a hit at
rank r means at least one of the top-r chunks has a canonicalised DOI in the item's gold
set. Denominator is all 12 (every gold paper is indexed, so no "indexed-only" subset).
Misses at k=5: D3-03 (first gold at rank 8), D3-08 (rank 9), D3-11 (nowhere in top 10),
D3-12 (rank 8).

The report documents the exact reused code path
(`conditions.retrieve` → `similarity_search_with_score` on `owf_clean_v1` with the BGE
query-prefix embeddings, raw question as query), but **the runner script itself is not in
the repo**. The only committed Hit@k script, `setup/05_evaluate_retrieval.py`, defaults to
the **frozen** index and the **pilot** eval set (`:104-106`) and performs raw DOI set
intersection with **no canonicalisation** (`:78-84`) — so it produces the superseded
0.433, not 0.667, and cannot be pointed at the clean index without also being given a
canonicalising matcher.

---

*Sections 6 and 7 are in `discrepancies.md`. Section 8 is in `viva_questions.md`.*
