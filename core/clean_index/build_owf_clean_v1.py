"""
build_owf_clean_v1.py
---------------------
Study-specific driver for the canonical clean build. It applies the triage cleanup
policy on top of the reusable clean-index engine, builds the collection owf_clean_v1
into chroma_db_clean/, and writes a per-paper quality manifest.

Policy (from the triage; see TRIAGE_REPORT.md):
  * EXCLUDE 15 PDFs (12 confirmed wrong-content + 3 wrong-granularity), logged with reason.
  * GLYPH paper 10.3389/fclim.2024.1353939: pymupdf renders its digits correctly, so it is
    included via pymupdf full text (no GROBID section structure), logged as such.
  * Extraction-risk PDFs are attempted in the normal GROBID loop; the HTTP 500 case is
    retried once; the pypdf-unreadable enpol case is a "PDF not available" placeholder and
    is skipped. Anything GROBID still cannot parse goes to the authoritative skip list.
    NB deliberately NO blanket pymupdf fallback for GROBID failures (that would reintroduce
    the reference-laden, unsegmented text this rebuild removes).

Nothing here touches the frozen chroma_db/. Retrieval is NOT wired (that is Phase 2).

Run (GROBID must be up):
    python -m core.clean_index.build_owf_clean_v1
    python -m core.clean_index.build_owf_clean_v1 --limit 10   # smoke test
"""

import os
import re
import csv
import json
import argparse
from pathlib import Path
from datetime import datetime

import fitz  # pymupdf
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import default_config
from .grobid_client import GrobidClient, GrobidError
from .build_index import filename_to_doi, doi_to_filename, extract_one, _chunk_id
from .embeddings import build_embeddings

ROOT = Path(__file__).resolve().parent.parent.parent
META = ROOT / "paper_metadata.json"
MANIFEST_MD = ROOT / "owf_clean_v1_MANIFEST.md"
MANIFEST_CSV = ROOT / "owf_clean_v1_papers.csv"
CHECKPOINT = ROOT / "owf_clean_v1_build_checkpoint.jsonl"

# --- Triage exclusion policy -------------------------------------------------
EXCLUDE = {
    # confirmed wrong-content (wrapper/repository pages, duplicates, wrong-article bindings)
    "10.1016/j.coastaleng.2020.103790": "wrong_content: End User Agreement wrapper page",
    "10.1016/j.ecolmodel.2013.09.025": "wrong_content: End User Agreement wrapper (CentAUR)",
    "10.1016/j.renene.2016.10.035": "wrong_content: Data Protection statement wrapper",
    "10.1080/00207543.2017.1403661": "wrong_content: Data Protection statement wrapper (duplicate)",
    "10.2423/i22394303v6sp1": "wrong_content: OAR@UM repository landing page",
    "10.3390/jmse10122017": "wrong_content: OAR@UM repository landing page (duplicate)",
    "10.1007/s10236-025-01665-8": "wrong_content: HAL repository landing (PUBLIER EN SCIENCES)",
    "10.17736/ijope.2025.jc939": "wrong_content: ISOPE membership form",
    "10.17736/ijope.2017.cl03": "wrong_content: different ISOPE article bound in",
    "10.3391/ai.2016.11.4.08": "wrong_content: different article (Comments on Mediterranean...)",
    "10.1007/s11367-014-0709-2": "wrong_content: different document (NREAP projections)",
    "10.1016/j.apenergy.2009.05.031": "wrong_content: Cyprus Open Science policy, not the Naxos paper",
    # wrong-granularity (whole-volume or non-matching large docs)
    "10.11646/zootaxa.5741.1.6": "wrong_granularity: 1M-char whole Zootaxa volume, not the article",
    "10.1007/s10661-020-08603-9": "wrong_granularity: 244k chars, 7% title overlap",
    "10.1016/j.renene.2018.10.090": "wrong_granularity: 52k chars, 0% title overlap",
}

# Glyph paper: include via pymupdf (digits verified to render correctly).
GLYPH_DOI = "10.3389/fclim.2024.1353939"


def load_meta_titles():
    m = json.load(open(META, encoding="utf-8"))
    return {(it.get("doi") or "").strip(): (it.get("title") or "") for it in m}


def _splitter(cfg):
    return RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap,
        length_function=len, separators=["\n\n", "\n", ". ", " ", ""],
    )


def pymupdf_fulltext(pdf_path):
    doc = fitz.open(str(pdf_path))
    text = "\n".join(p.get_text() for p in doc)
    doc.close()
    # light clean + drop a trailing reference list if a clear heading is present
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)           # dehyphenate line breaks
    m = list(re.finditer(r"\n\s*(references|bibliography)\s*\n", text, re.I))
    if m:
        text = text[: m[-1].start()]
    return re.sub(r"[ \t]+", " ", text).strip()


def pymupdf_documents(text, doi, source, title, cfg):
    docs = []
    for i, piece in enumerate(_splitter(cfg).split_text(text)):
        piece = piece.strip()
        if not piece:
            continue
        docs.append(Document(page_content=piece, metadata={
            "doi": doi, "title": title, "source": source,
            "section": "fulltext_pymupdf", "section_head": "",
            "is_caption": False, "caption_kind": "", "chunk_index": len(docs),
        }))
    for d in docs:
        d.metadata["total_chunks"] = len(docs)
    return docs


def grobid_with_retry(client, pdf, cfg, retries=1):
    """extract_one, retrying once on a transient GROBID error (e.g. HTTP 500)."""
    last = None
    for _ in range(retries + 1):
        try:
            return extract_one(client, pdf, cfg)
        except GrobidError as e:
            last = e
    raise last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--resume", action="store_true", help="Skip DOIs already in the checkpoint.")
    ap.add_argument("--collection", default=None, help="Override collection (smoke tests).")
    ap.add_argument("--db_dir", default=None, help="Override persist dir (smoke tests).")
    args = ap.parse_args()

    cfg = default_config()   # owf_clean_v1 in chroma_db_clean/, BGE recipe, 1000/200
    if args.collection:
        cfg.collection_name = args.collection
    if args.db_dir:
        cfg.db_dir = args.db_dir
    client = GrobidClient(cfg.grobid_url, cfg.grobid_timeout)
    if not client.is_alive():
        print(f"GROBID not reachable at {cfg.grobid_url}. Start the container first.")
        raise SystemExit(2)

    titles = load_meta_titles()
    pdfs = sorted(p for p in Path(cfg.pdf_dir).iterdir() if p.suffix.lower() == ".pdf")
    if args.limit:
        pdfs = pdfs[: args.limit]

    done = set()
    if args.resume and CHECKPOINT.exists():
        for line in open(CHECKPOINT, encoding="utf-8"):
            line = line.strip()
            if line:
                done.add(json.loads(line)["doi"])

    print(cfg.describe())
    print(f"\nPDFs on disk: {len(pdfs)} | excluded policy: {len(EXCLUDE)} | resume-skip: {len(done)}\n")

    embeddings = build_embeddings(cfg)
    from langchain_chroma import Chroma
    store = Chroma(collection_name=cfg.collection_name, embedding_function=embeddings,
                   persist_directory=cfg.db_dir)

    ck = open(CHECKPOINT, "a", encoding="utf-8")
    rows = []
    batch_docs, batch_ids = [], []

    def flush():
        if batch_docs:
            store.add_documents(documents=batch_docs, ids=batch_ids)
            batch_docs.clear(); batch_ids.clear()

    n_inc = n_exc = n_skip = n_chunks = 0
    for i, pdf in enumerate(pdfs, 1):
        doi = filename_to_doi(pdf.name)
        if doi in done:
            continue
        status = reason = None
        nchunks = 0
        try:
            if doi in EXCLUDE:
                status, reason = "excluded", EXCLUDE[doi]
                n_exc += 1
            elif doi == GLYPH_DOI:
                text = pymupdf_fulltext(pdf)
                if re.search(r"/(?:zero|one|two|three|four|five)\.(?:tnum|oldstyle|lf|osf)", text):
                    status, reason = "skipped", "glyph: digits still glyph-encoded after pymupdf"
                    n_skip += 1
                else:
                    docs = pymupdf_documents(text, doi, pdf.name, titles.get(doi, ""), cfg)
                    for d in docs:
                        batch_docs.append(d); batch_ids.append(_chunk_id(doi, d.metadata["chunk_index"]))
                    nchunks = len(docs); n_chunks += nchunks; n_inc += 1
                    status, reason = "included", "glyph-fixed via pymupdf full text (no section structure)"
            else:
                docs, parsed = grobid_with_retry(client, pdf, cfg, retries=1)
                if not docs:
                    status, reason = "skipped", "grobid: parsed but produced no usable content"
                    n_skip += 1
                else:
                    for d in docs:
                        batch_docs.append(d); batch_ids.append(_chunk_id(doi, d.metadata["chunk_index"]))
                    nchunks = len(docs); n_chunks += nchunks; n_inc += 1
                    status, reason = "included", f"grobid: {len(parsed.sections)} sections, {len(parsed.captions)} captions"
        except GrobidError as e:
            status, reason = "skipped", f"grobid_fail: {str(e).splitlines()[0][:120]}"
            n_skip += 1
        except Exception as e:
            status, reason = "skipped", f"error: {type(e).__name__}: {str(e)[:120]}"
            n_skip += 1

        if len(batch_docs) >= cfg.batch_size:
            flush()
        rec = {"doi": doi, "pdf": pdf.name, "status": status, "reason": reason, "n_chunks": nchunks}
        rows.append(rec)
        ck.write(json.dumps(rec, ensure_ascii=False) + "\n"); ck.flush()
        if i % 20 == 0 or status != "included":
            print(f"[{i}/{len(pdfs)}] {status:8s} {doi}  ({reason[:60]})", flush=True)

    flush()
    ck.close()

    # merge any resumed rows from checkpoint for a complete manifest
    all_rows = {}
    for line in open(CHECKPOINT, encoding="utf-8"):
        line = line.strip()
        if line:
            r = json.loads(line); all_rows[r["doi"]] = r
    all_rows = list(all_rows.values())
    write_manifest(all_rows, cfg, store)
    print(f"\nDONE. included={n_inc} excluded={n_exc} skipped={n_skip} chunks={n_chunks}")


def write_manifest(rows, cfg, store):
    inc = [r for r in rows if r["status"] == "included"]
    exc = [r for r in rows if r["status"] == "excluded"]
    skip = [r for r in rows if r["status"] == "skipped"]
    total_chunks = sum(r["n_chunks"] for r in rows)
    try:
        coll_count = store._collection.count()
    except Exception:
        coll_count = total_chunks

    with open(MANIFEST_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["doi", "pdf", "status", "reason", "n_chunks"])
        for r in sorted(rows, key=lambda r: (r["status"], r["doi"])):
            w.writerow([r["doi"], r["pdf"], r["status"], r["reason"], r["n_chunks"]])

    def cat(prefix):
        return sorted([r for r in exc if r["reason"].startswith(prefix)], key=lambda r: r["doi"])
    with open(MANIFEST_MD, "w", encoding="utf-8") as f:
        f.write(f"# owf_clean_v1 build manifest\n\n")
        f.write(f"Date: {datetime.now().date().isoformat()}. Collection `{cfg.collection_name}` "
                f"in `{cfg.db_dir}` (the frozen `chroma_db/` was not opened for writing).\n\n")
        f.write("## Totals\n\n")
        f.write(f"- PDFs on disk considered : {len(rows)}\n")
        f.write(f"- Included                : {len(inc)}\n")
        f.write(f"- Excluded (triage policy): {len(exc)}\n")
        f.write(f"- Skipped (build failures): {len(skip)}\n")
        f.write(f"- Final papers in index   : {len(inc)}\n")
        f.write(f"- Total chunks (rows)     : {total_chunks}\n")
        f.write(f"- Chroma collection count : {coll_count}\n\n")
        f.write("## Extractor / recipe\n\n")
        f.write(f"- GROBID lightweight CRF image (lfoppiano/grobid:0.8.0), processFulltextDocument.\n")
        f.write(f"- KEEP title(meta)/abstract/body sections + captions; DROP TEI back + drop-list headings.\n")
        f.write(f"- Chunk {cfg.chunk_size}/{cfg.chunk_overlap}, section-bounded.\n")
        f.write(f"- BGE recipe: query prefix on queries, passages plain, normalised.\n")
        f.write(f"- Glyph paper {GLYPH_DOI}: included via pymupdf (digits render correctly).\n\n")
        f.write("## Excluded (by category, with reason)\n\n")
        for label, pref in [("Confirmed wrong-content", "wrong_content"), ("Wrong-granularity", "wrong_granularity")]:
            f.write(f"### {label}\n\n")
            for r in cat(pref):
                f.write(f"- `{r['doi']}` - {r['reason']}\n")
            f.write("\n")
        f.write("## Skipped (authoritative build skip list)\n\n")
        for r in sorted(skip, key=lambda r: r["doi"]):
            f.write(f"- `{r['doi']}` - {r['reason']}\n")
        f.write("\n")
        f.write("## Glyph paper outcome\n\n")
        g = [r for r in rows if r["doi"] == GLYPH_DOI]
        if g:
            f.write(f"- `{GLYPH_DOI}`: {g[0]['status']} - {g[0]['reason']} ({g[0]['n_chunks']} chunks)\n")
    print(f"wrote {MANIFEST_MD} and {MANIFEST_CSV}")


if __name__ == "__main__":
    main()
