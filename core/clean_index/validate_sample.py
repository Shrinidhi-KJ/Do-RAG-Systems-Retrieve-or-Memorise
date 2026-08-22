"""
validate_sample.py
------------------
Step-3 validation tool: for ~5 PDFs spanning different publishers, put the OLD chunks
(from the frozen chroma_db / wind_farm_papers collection) next to the NEW chunks
(freshly extracted via GROBID, NOT written anywhere) so the cleaning can be judged by eye.

It also runs automatic checks: are reference lists gone, are page-number/header artefacts
gone, are section labels sensible, are captions retained. Extraction failures among the
sample are reported, not hidden.

Read-only on the frozen study: the old collection is opened with a chromadb client and
only `.get()` is called (metadata fetch, no writes, no embedding).

Usage (needs GROBID running):
    python -m core.clean_index.validate_sample                 # auto-pick 5 by publisher
    python -m core.clean_index.validate_sample --pdfs a.pdf b.pdf ...
    python -m core.clean_index.validate_sample --previews 3    # chunk previews per paper
"""

import re
import sys
import sqlite3
import argparse
from pathlib import Path
from collections import Counter, OrderedDict

from .config import default_config
from .grobid_client import GrobidClient, GrobidError
from .tei_parser import parse_tei
from .chunking import build_documents
from .build_index import filename_to_doi, extract_one

OLD_DB = str((Path(__file__).resolve().parent.parent.parent / "chroma_db"))
OLD_SQLITE = str(Path(OLD_DB) / "chroma.sqlite3")
OLD_COLLECTION = "wind_farm_papers"

# Signals that a chunk is a reference list / bibliography (should be ~absent in NEW).
_REF_HINTS = re.compile(r"(doi\.org|doi:\s*10\.|\bet al\.,?\s*\(?\d{4}|^\s*\[\d+\]|References\b)", re.I)
# Standalone page-number / short running-header artefacts (should be absent in NEW).
_PAGENUM = re.compile(r"^\s*\d{1,4}\s*$|^\s*page\s+\d+", re.I)


def old_chunks_for(doi: str, sqlite_path: str = OLD_SQLITE):
    """
    Fetch the frozen collection's chunks for a DOI directly from the Chroma sqlite,
    STRICTLY read-only (mode=ro, immutable=1 -> no writes, no -wal/-shm side files),
    so the frozen index and its archive checksums are never touched. No embeddings loaded.

    Chroma stores each chunk's text under metadata key 'chroma:document' and our DOI under
    key 'doi', both keyed by the embedding row id. We join on id and order by chunk_index.
    """
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro&immutable=1", uri=True)
    try:
        cur = con.cursor()
        rows = cur.execute(
            """
            SELECT doc.string_value
            FROM embedding_metadata AS d
            JOIN embedding_metadata AS doc
              ON doc.id = d.id AND doc.key = 'chroma:document'
            LEFT JOIN embedding_metadata AS ci
              ON ci.id = d.id AND ci.key = 'chunk_index'
            WHERE d.key = 'doi' AND d.string_value = ?
            ORDER BY ci.int_value
            """,
            (doi,),
        ).fetchall()
        return [r[0] for r in rows if r[0] is not None]
    finally:
        con.close()


def pick_sample(config, n=5):
    """Pick n PDFs from distinct DOI registrant prefixes (publisher spread)."""
    pdfs = sorted(p for p in Path(config.pdf_dir).iterdir() if p.suffix.lower() == ".pdf")
    buckets = OrderedDict()
    for p in pdfs:
        doi = filename_to_doi(p.name)
        m = re.match(r"(10\.\d+)", doi)
        prefix = m.group(1) if m else "other"
        buckets.setdefault(prefix, p)
    chosen = list(buckets.values())[:n]
    return chosen


def ref_ratio(chunks):
    if not chunks:
        return 0.0
    return sum(1 for c in chunks if _REF_HINTS.search(c or "")) / len(chunks)


def pagenum_count(chunks):
    return sum(1 for c in chunks if _PAGENUM.search((c or "").strip()))


def main():
    # Windows consoles default to cp1252; TEI text carries unicode (em-spaces, dashes).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", nargs="+", default=None, help="Explicit PDF paths.")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--previews", type=int, default=2, help="Chunk previews per paper.")
    args = ap.parse_args()

    config = default_config()
    client = GrobidClient(config.grobid_url, config.grobid_timeout)
    if not client.is_alive():
        print(f"GROBID not reachable at {config.grobid_url}. Start the container first.")
        raise SystemExit(2)

    if args.pdfs:
        sample = [Path(p) for p in args.pdfs]
    else:
        sample = pick_sample(config, args.n)

    print(f"Validation sample ({len(sample)} papers):")
    for p in sample:
        print(f"  - {p.name}  (DOI {filename_to_doi(p.name)})")
    print()

    for p in sample:
        doi = filename_to_doi(p.name)
        print("=" * 84)
        print(f"PAPER  {p.name}\n       DOI {doi}")
        print("-" * 84)

        # OLD
        try:
            old = old_chunks_for(doi)
        except Exception as e:
            old = []
            print(f"  OLD: could not fetch from frozen collection: {e}")

        # NEW
        try:
            new_docs, parsed = extract_one(client, p, config)
            new = [d.page_content for d in new_docs]
            failed = None
        except GrobidError as e:
            new, parsed, failed = [], None, str(e)
        except Exception as e:
            new, parsed, failed = [], None, f"{type(e).__name__}: {e}"

        if failed:
            print(f"  NEW: EXTRACTION FAILED -> {failed}")
            continue

        labels = Counter(d.metadata["section"] for d in new_docs)
        caps = sum(1 for d in new_docs if d.metadata["is_caption"])
        print(f"  OLD chunks: {len(old):4d} | ref-like {ref_ratio(old):5.1%} | "
              f"pagenum/header artefacts {pagenum_count(old)}")
        print(f"  NEW chunks: {len(new):4d} | ref-like {ref_ratio(new):5.1%} | "
              f"pagenum/header artefacts {pagenum_count(new)}")
        print(f"  NEW title  : {parsed.title[:100]!r}")
        print(f"  NEW sections labels: {dict(labels)}   captions kept: {caps}")
        if parsed.dropped_heads:
            print(f"  NEW dropped body headings: {parsed.dropped_heads}")

        for tag, chunks in (("OLD", old), ("NEW", new)):
            print(f"\n  --- {tag} sample chunks ---")
            for c in chunks[: args.previews]:
                print(f"    | {c[:240].strip()} ...")
        print()

    print("=" * 84)
    print("Check by eye: references gone, headers/footers/page-numbers gone, hyphenation")
    print("and spacing fixed, body intact, section labels sensible, captions retained.")


if __name__ == "__main__":
    main()
