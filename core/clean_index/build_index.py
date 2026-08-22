"""
build_index.py
--------------
Orchestrator/CLI for the clean GROBID extraction + indexing pipeline.

For each PDF: map filename -> DOI, extract with GROBID, parse the TEI under the
KEEP/DROP policy, section-bound chunk, embed with the BGE recipe, and write into a NEW
Chroma collection (default owf_clean_v1 in chroma_db_clean/). The frozen study's
chroma_db/ (collection wind_farm_papers) is never opened for writing.

Extraction failures are never silent: each is appended to a failure log and a skip list.

Usage:
    # 0. Start GROBID (see grobid_client.py), then confirm it is up:
    python -m core.clean_index.build_index --health

    # Inspect extraction without writing anything (parse + chunk only):
    python -m core.clean_index.build_index --pdf "PDFs\10.1016_j.marpolbul.2025.117915.pdf" --dry-run

    # Build the full canonical index (Phase 2 - run only after the sample is approved):
    python -m core.clean_index.build_index

    # Smoke test on the first few PDFs:
    python -m core.clean_index.build_index --limit 5
"""

import os
import re
import sys
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

from .config import default_config, Config
from .grobid_client import GrobidClient, GrobidError
from .tei_parser import parse_tei
from .chunking import build_documents


# ---- DOI <-> filename (identical convention to rag_pipeline.load_pdfs) ---------

def filename_to_doi(pdf_name: str) -> str:
    """`10.1016_j.apenergy.2024.124437.pdf` -> `10.1016/j.apenergy.2024.124437`."""
    return pdf_name[:-4].replace("_", "/", 1) if pdf_name.lower().endswith(".pdf") else pdf_name

def doi_to_filename(doi: str) -> str:
    """Reverse mapping used by the downloaders: DOI -> on-disk PDF name."""
    return re.sub(r"[^\w\-_.]", "_", doi) + ".pdf"


def _chunk_id(doi: str, idx: int) -> str:
    return hashlib.md5(f"{doi}_{idx}".encode()).hexdigest()[:12]


def _resolve_pdfs(config: Config):
    """Return the list of PDF paths to process, from pdf_dir or an explicit DOI list."""
    pdf_dir = Path(config.pdf_dir)
    if config.dois_file:
        pdfs = []
        for line in Path(config.dois_file).read_text(encoding="utf-8").splitlines():
            doi = line.strip().split("\t")[0]
            if not doi:
                continue
            p = pdf_dir / doi_to_filename(doi)
            pdfs.append(p)
        return pdfs
    return sorted(p for p in pdf_dir.iterdir() if p.suffix.lower() == ".pdf")


def _log_failure(config: Config, pdf_name: str, reason: str):
    with open(config.failure_log, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()}\t{pdf_name}\t{reason}\n")
    with open(config.skip_list, "a", encoding="utf-8") as f:
        f.write(pdf_name + "\n")


def extract_one(client: GrobidClient, pdf_path: Path, config: Config):
    """GROBID -> parse -> chunk for one PDF. Returns (docs, parsed). Raises GrobidError."""
    tei = client.process_fulltext(str(pdf_path))
    parsed = parse_tei(tei, config.drop_section_keywords, config.section_label_map)
    doi = filename_to_doi(pdf_path.name)
    docs = build_documents(parsed, doi=doi, source=pdf_path.name, config=config)
    return docs, parsed


def build(config: Config, limit=None, dry_run=False, single_pdf=None):
    client = GrobidClient(config.grobid_url, config.grobid_timeout)
    if not client.is_alive():
        print(f"GROBID is not reachable at {config.grobid_url}.")
        print("Start it with:  docker run --rm --init -p 8070:8070 lfoppiano/grobid:0.8.0")
        sys.exit(2)

    if single_pdf:
        pdfs = [Path(single_pdf)]
    else:
        pdfs = _resolve_pdfs(config)
        if limit:
            pdfs = pdfs[:limit]

    print(config.describe())
    print(f"\nPDFs to process: {len(pdfs)}   dry_run={dry_run}\n")

    vectorstore = None
    embeddings = None
    if not dry_run:
        # Import here so --dry-run and --health need neither torch nor chromadb.
        from langchain_chroma import Chroma
        from .embeddings import build_embeddings
        embeddings = build_embeddings(config)

    n_ok = n_fail = n_chunks = 0
    batch_docs, batch_ids = [], []

    def flush():
        nonlocal vectorstore, batch_docs, batch_ids
        if not batch_docs:
            return
        from langchain_chroma import Chroma
        if vectorstore is None:
            vectorstore = Chroma.from_documents(
                documents=batch_docs, embedding=embeddings, ids=batch_ids,
                collection_name=config.collection_name, persist_directory=config.db_dir,
            )
        else:
            vectorstore.add_documents(documents=batch_docs, ids=batch_ids)
        batch_docs, batch_ids = [], []

    for i, pdf in enumerate(pdfs, 1):
        try:
            docs, parsed = extract_one(client, pdf, config)
        except GrobidError as e:
            n_fail += 1
            _log_failure(config, pdf.name, str(e).replace("\n", " ")[:300])
            print(f"[{i}/{len(pdfs)}] FAIL {pdf.name}: {e}")
            continue
        except Exception as e:  # malformed TEI etc: log, never silently drop
            n_fail += 1
            _log_failure(config, pdf.name, f"{type(e).__name__}: {e}")
            print(f"[{i}/{len(pdfs)}] FAIL {pdf.name}: {type(e).__name__}: {e}")
            continue

        n_ok += 1
        n_chunks += len(docs)
        print(f"[{i}/{len(pdfs)}] ok   {pdf.name}: {len(parsed.sections)} sections, "
              f"{len(parsed.captions)} captions -> {len(docs)} chunks"
              + (f"  (dropped heads: {parsed.dropped_heads})" if parsed.dropped_heads else ""))

        if not dry_run:
            doi = filename_to_doi(pdf.name)
            for d in docs:
                batch_docs.append(d)
                batch_ids.append(_chunk_id(doi, d.metadata["chunk_index"]))
                if len(batch_docs) >= config.batch_size:
                    flush()

    if not dry_run:
        flush()

    print("\n" + "=" * 60)
    print(f"  Processed OK : {n_ok}")
    print(f"  Failed       : {n_fail}  (see {config.failure_log})")
    print(f"  Chunks       : {n_chunks}")
    if not dry_run:
        print(f"  Collection   : {config.collection_name}  in  {config.db_dir}")
    else:
        print("  DRY RUN: nothing was written to Chroma.")
    print("=" * 60)


def main():
    ap = argparse.ArgumentParser(description="Clean GROBID extraction + indexing.")
    ap.add_argument("--pdf_dir", default=None)
    ap.add_argument("--dois_file", default=None)
    ap.add_argument("--db_dir", default=None)
    ap.add_argument("--collection", default=None)
    ap.add_argument("--grobid_url", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pdf", default=None, help="Process a single PDF (path).")
    ap.add_argument("--dry-run", action="store_true", help="Parse + chunk only; no writes.")
    ap.add_argument("--health", action="store_true", help="Check GROBID is up, then exit.")
    args = ap.parse_args()

    config = default_config()
    if args.pdf_dir: config.pdf_dir = args.pdf_dir
    if args.dois_file: config.dois_file = args.dois_file
    if args.db_dir: config.db_dir = args.db_dir
    if args.collection: config.collection_name = args.collection
    if args.grobid_url: config.grobid_url = args.grobid_url

    if args.health:
        client = GrobidClient(config.grobid_url, config.grobid_timeout)
        alive = client.is_alive()
        print(f"GROBID at {config.grobid_url}: {'ALIVE' if alive else 'NOT REACHABLE'}")
        sys.exit(0 if alive else 2)

    build(config, limit=args.limit, dry_run=args.dry_run, single_pdf=args.pdf)


if __name__ == "__main__":
    main()
