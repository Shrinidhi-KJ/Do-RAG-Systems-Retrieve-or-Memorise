# PROJECT.md — operational manual

Developer/operator reference for the four-condition RAG diagnostic. For the research
question and findings, see [../README.md](../README.md). This file is *how to run it and
what to watch out for*.

Throughout, the **repo root** is `…\Desktop\Dissertation\data_pipeline`. Scripts now
resolve all data paths to the repo root via `ROOT = Path(__file__).resolve().parent.parent`,
so **the standard form is to run from the repo root** with a folder prefix, e.g.
`python core\run_experiment.py`. Running from inside `core/` (`python run_experiment.py`)
or with an absolute path works identically.

---

## 1. How to run

### One-time setup
```powershell
# Activate the project venv (it lives one level up, in Desktop\Dissertation\)
cd C:\Users\<you>\Desktop\Dissertation
.\venv\Scripts\Activate.ps1
cd data_pipeline

# Install pinned dependencies (first time only)
python -m pip install -r requirements.txt

# Groq key for this session (scripts read it from the OS environment; they do NOT
# auto-load .env). Use setx instead to persist it across terminals, then reopen.
$env:GROQ_API_KEY = "gsk_..."
```

### Layer 2 — the experiment (the part you actually run day to day)
```powershell
python core\rag_pipeline.py --rebuild          # (re)build chroma_db/   — no Groq, ~45 min
python setup\05_evaluate_retrieval.py          # retrieval Hit@k        — no Groq
python core\build_contradictions.py            # Condition-D docs       — COSTS Groq tokens
python core\run_experiment.py                  # the full run           — COSTS Groq tokens
python core\run_experiment.py --status         # progress, runs nothing — no Groq
python core\run_experiment.py --export results.csv   # flatten cache     — no Groq
python core\analyse_results.py                 # results tables         — no Groq
```

### Layer 1 — corpus building (already complete; run only to extend the corpus)
```powershell
# Discovery needs Scopus/WoS keys from the environment ($env:SCOPUS_API_KEY / $env:WOS_API_KEY).
# The full multi-source flag set is preserved in archive\README_RUN_ORDER.md.
python setup\doi_discovery_dualmode_clean_fixed_queryloader.py --sources scopus wos --scopus_wos_query_file OWF_ScopusQueries.txt
python setup\download_with_progress.py   --email <you> --dois_file dois_merged_final.txt
python setup\02_download_extra_sources.py --email <you> --dois_file dois_merged_final.txt
python setup\01_clean_fake_pdfs.py                                    # then rebuild the index
python setup\03_enrich_metadata.py       --email <you> --dois_file dois_merged_final.txt
python setup\04_build_pilot_eval_set.py  --report_pdf "2025-10-27-Eklipse_Report_WindFarm_Final.pdf"
```

**Groq token cost summary:** only `build_contradictions.py` (data construction) and
`run_experiment.py` (generation + LLM-judge classification) call Groq. Everything else —
discovery, downloading, metadata, indexing, retrieval evaluation, status, export,
analysis — is free of Groq calls (it uses OpenAlex/Scopus/WoS/Unpaywall, local
embeddings, or pure file processing).

---

## 2. File reference

### `core/` — Layer 2 (the experiment engine)
| Script | Role | Groq |
|---|---|:--:|
| `rag_pipeline.py` | PDF → clean → chunk (1000/200) → BGE-small embed → ChromaDB; also a retrieval-test CLI | no |
| `llm_generation.py` | Groq Llama-3.1-8B wrapper (lazy client, temp 0, rate-limit backoff); backs all conditions + judges | — |
| `conditions.py` | The five conditions A/B1/B2/C/D; uses the pipeline's exact retriever | yes¹ |
| `classifier.py` | Diagnostic taxonomy via LLM-as-judge (abstained/correct/grounded/retrieval_hit → `failure_type`) | yes¹ |
| `build_contradictions.py` | One-time builder of Condition-D counterfactuals → `contradictions_cache.json` | **yes** |
| `run_experiment.py` | The runner: items × conditions × models → classify → append `results_cache.jsonl`; idempotent/resumable | **yes** |
| `analyse_results.py` | Aggregates `results.csv` into the dissertation tables (Wilson 95% CIs) | no |
| `inspect_contradictions.py` | Dumps the contradiction cache (claim vs oracle chunk) for human review | no |

¹ via `run_experiment.py`; not called directly in normal use.

### `setup/` — Layer 1 (one-off corpus acquisition)
| Script | Role |
|---|---|
| `doi_discovery_dualmode_clean_fixed_queryloader.py` | Discover DOIs from OpenAlex / Scopus / Web of Science (needs Scopus/WoS keys) |
| `doi_download_only.py` | Core PDF-download library (Unpaywall / OpenAlex / Elsevier / HTML fallback) |
| `download_with_progress.py` | Progress-bar wrapper over `doi_download_only` — the downloader you run |
| `01_clean_fake_pdfs.py` | Remove HTML paywall pages saved as `.pdf` |
| `02_download_extra_sources.py` | Second-pass downloader (CORE / Semantic Scholar / arXiv) |
| `03_enrich_metadata.py` | Fetch OpenAlex metadata → `paper_metadata.json` |
| `04_build_pilot_eval_set.py` | Extract Eklipse claims, match to corpus → `pilot_eval_set.json` |
| `05_evaluate_retrieval.py` | Retrieval recall Hit@k / recall@k → `retrieval_evaluation.json` |

### Data artifacts (in repo root)
| File / dir | One-line description |
|---|---|
| `chroma_db/` | Vector index — 45,830 chunks from 510 papers |
| `PDFs/` | The corpus — 514 downloaded PDFs (~2.1 GB) |
| `pilot_eval_set.json` | 67 ground-truth items: `question`, `claim_text`, `matched_dois`, `citations` |
| `contradictions_cache.json` | 67 frozen Condition-D counterfactuals (oracle-sourced, verified) |
| `results_cache.jsonl` | Append-only experiment log — 335 cells (67 × 5 conditions × 1 model) |
| `results.csv` | Flattened cache for analysis |
| `paper_metadata.json` | OpenAlex metadata for 1,715 discovered DOIs |
| `chunks_metadata.json` | Preview metadata for every chunk (regenerated on each `--rebuild`) |
| `retrieval_evaluation.json` | Hit@k / recall@k results (Hit@5 ≈ 43%) |
| `2025-10-27-Eklipse_Report_WindFarm_Final.pdf` | Source report the eval set is built from |
| `dois*.txt`, `doi_sources*.txt`, `OWF_*.txt`, `hybrid_openalex_queries.json`, `debug_*.tsv` | DOI/query provenance — the corpus-construction record |
| `archive/` | Superseded README + stale smoke-test files |

---

## 3. Data artifacts — the never-delete rule

These represent **days of compute and metered API calls** and cannot be casually
regenerated. **Never delete, move, or overwrite** them (except via the documented
backup step in §5):

- **`chroma_db/`** — ~45 min of CPU embedding; the searchable index.
- **`PDFs/`** — hours of rate-limited downloading from many publishers.
- **`results_cache.jsonl`** — the actual experiment output, accumulated across multiple
  token-capped days. Append-only and crash-safe (a hard kill loses at most one line).
- **`contradictions_cache.json`** — the frozen Condition-D inputs; freezing them is what
  makes the run reproducible.
- **`pilot_eval_set.json`**, **`paper_metadata.json`** — the ground truth and the
  metadata it was matched against (1,715 OpenAlex calls).
- **`results.csv`** — derived, but it is the analysis input; keep it.

`chunks_metadata.json` is the one safe-to-lose artifact (rebuilt on every index rebuild).

---

## 4. Gotchas

- **Always use the venv Python.** If you run a `core/` script with system Python instead
  of the project venv, LangChain raises a `TypedDict`/`typing_extensions` error on import.
  Activate the venv (`.\venv\Scripts\Activate.ps1`) or call `..\venv\Scripts\python.exe`
  explicitly. (`requirements.txt` pins the working versions.)
- **DOI ↔ filename quirk.** PDFs are named by DOI with **only the first underscore mapped
  back to a slash**: file `10.1016_j.apenergy.2024.124437.pdf` ⇄ DOI
  `10.1016/j.apenergy.2024.124437` (`pdf_file.replace(".pdf","").replace("_","/",1)` in
  `rag_pipeline.load_pdfs`). Downloaders go the other way via `re.sub(r"[^\w\-_.]","_",doi)`.
  Keep this in mind whenever you match DOIs against files on disk.
- **Free-tier token caps + clean resume.** Groq free tier: **8B ≈ 500k tokens/day
  (~14,400 req/day)**, **70B ≈ 100k tokens/day**. `run_experiment.py` uses 8B for both the
  subject model and the judges because the full run is thousands of calls. When the daily
  cap is hit, the generation layer raises `RuntimeError` after its retries; the runner
  **catches it, prints progress, and exits cleanly** (nothing half-written). Just re-run
  the **same command** the next day — it skips completed cells via each cell's key in
  `results_cache.jsonl`. `build_contradictions.py` likewise resumes; its 8B editor builds
  all 67 in one day (70B would exhaust around item ~30 — pass
  `--model llama-3.3-70b-versatile` only if you have the budget).
- **The exclusion list `[2, 34, 45]`.** Hardcoded as `EXCLUDE` in `analyse_results.py`.
  Items **2** and **45** are *provenance mismatches* (claim matched to the wrong DOI,
  flagged during contradiction construction); item **34** is *non-assertional*. They are
  dropped from Condition D / B2 scoring (results are reported both filtered and
  unfiltered). **Recompute this list** for any new eval set from the
  `inspect_contradictions.py` review.

---

## 5. Running on curated questions

When the supervisor's curated questions arrive, swap them in like this. The corpus and
index are unaffected — **`chroma_db/` does NOT need rebuilding unless the underlying PDF
corpus changes.**

```powershell
# 1. Back up the pilot run
New-Item -ItemType Directory -Force archive\pilot_run | Out-Null
Rename-Item results.csv results_pilot.csv
Move-Item results_cache.jsonl, contradictions_cache.json archive\pilot_run\

# 2. Replace pilot_eval_set.json with the curated file. SAME SCHEMA per item:
#    {"question": ..., "claim_text": ..., "matched_dois": [...], "citations": [...]}

# 3. Rebuild Condition D (use 70B if budget allows, else the 8B default)
python core\build_contradictions.py            # or: --model llama-3.3-70b-versatile

# 4. Review provenance_mismatch / unverified items, then update EXCLUDE in analyse_results.py
python core\inspect_contradictions.py

# 5. Run it (resumes across days on token-cap); track progress
python core\run_experiment.py
python core\run_experiment.py --status

# 6. Export + analyse
python core\run_experiment.py --export results.csv
python core\analyse_results.py
```

---

## 6. Git safety checklist (before the first commit)

This folder is **not yet a git repo**. Before `git init` / first commit:

```powershell
git init
git status --short                                  # nothing secret/heavy should be staged
git check-ignore -v .env PDFs chroma_db chunks_metadata.json
```

- Confirm **`.gitignore` exists** at the repo root.
- `git check-ignore` must echo each of `.env`, `PDFs/`, `chroma_db/`,
  `chunks_metadata.json` (proving they are ignored, not tracked). Also confirm the 14 MB
  Eklipse PDF is ignored.
- **Rotate the Web of Science + Scopus API keys before any push.** They were stored in
  plaintext locally (now scrubbed from `archive/README_RUN_ORDER.md` to `<SET_IN_ENV>`),
  so treat them as compromised. `.env.example` lists the three keys the project uses
  (`GROQ_API_KEY`, `SCOPUS_API_KEY`, `WOS_API_KEY`); real values go in `.env`, which is
  ignored.

---

## 7. Environment

- **Python 3.11.5**, in the venv at `…\Desktop\Dissertation\venv` (one level above the
  repo root).
- Dependencies pinned in `requirements.txt` (12 direct packages: `groq`, the `langchain*`
  stack, `chromadb`, `sentence-transformers`, `pypdf`, `tqdm`, `requests`).
- Embedding model: `BAAI/bge-small-en-v1.5` (CPU). Subject + judge model:
  `llama-3.1-8b-instant` on Groq. Contradiction editor: 8B by default, 70B optional.
