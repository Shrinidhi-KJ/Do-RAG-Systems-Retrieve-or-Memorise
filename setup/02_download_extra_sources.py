#!/usr/bin/env python3
"""
Enhanced PDF downloader for DOIs that failed in the first round.

Adds three new sources beyond Unpaywall and OpenAlex:
  1. CORE API (https://core.ac.uk/api-v3) - aggregates institutional repositories worldwide
  2. Semantic Scholar API - often has open-access PDF URLs
  3. arXiv direct search by DOI

Usage:
  python 02_download_extra_sources.py \
      --email shk00318@students.stir.ac.uk \
      --dois_file dois_merged.txt \
      --output_dir PDFs

It automatically skips DOIs you already have, so it can be run after the main
download to recover additional papers.
"""

import argparse
import os
import re
import sys
import time
from random import uniform
from pathlib import Path
from typing import List, Optional, Dict
from urllib.parse import quote

# Repo root = parent of setup/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

try:
    from tqdm import tqdm
except ImportError:
    print("Installing tqdm...")
    os.system(f"{sys.executable} -m pip install tqdm")
    from tqdm import tqdm


# ============================================================
# Helpers
# ============================================================

def canonicalize_doi(doi: str) -> str:
    doi = (doi or "").strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = re.sub(r"/v\d+$", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def doi_to_filename(doi: str) -> str:
    return re.sub(r"[^\w\-_.]", "_", doi)


def read_dois(path: str) -> List[str]:
    seen = set()
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            doi = canonicalize_doi(line.strip())
            if doi and doi.lower() not in seen:
                seen.add(doi.lower())
                out.append(doi)
    return out


def already_downloaded(doi: str, output_dir: str) -> bool:
    path = os.path.join(output_dir, f"{doi_to_filename(doi)}.pdf")
    return os.path.exists(path)


# ============================================================
# Source 1: CORE API
# ============================================================

def get_core_pdf_url(doi: str, session: requests.Session) -> Optional[str]:
    """
    Query CORE API for open-access PDF URL.
    CORE has a free tier that does not require API key for basic search.
    """
    try:
        url = f"https://api.core.ac.uk/v3/search/works"
        params = {"q": f'doi:"{doi}"', "limit": 1}
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        results = data.get("results", [])
        if not results:
            return None
        work = results[0]
        # CORE returns downloadUrl for direct PDF
        download_url = work.get("downloadUrl")
        if download_url:
            return download_url
        # Sometimes the fullText link points to a PDF
        full_text = work.get("fullTextIdentifier")
        if full_text and ".pdf" in full_text.lower():
            return full_text
        return None
    except Exception:
        return None


# ============================================================
# Source 2: Semantic Scholar API
# ============================================================

def get_semantic_scholar_pdf_url(doi: str, session: requests.Session) -> Optional[str]:
    """Query Semantic Scholar for an open-access PDF URL."""
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        params = {"fields": "openAccessPdf,isOpenAccess,externalIds"}
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        pdf_info = data.get("openAccessPdf")
        if pdf_info and pdf_info.get("url"):
            return pdf_info["url"]
        return None
    except Exception:
        return None


# ============================================================
# Source 3: arXiv search by DOI
# ============================================================

def get_arxiv_pdf_url(doi: str, session: requests.Session) -> Optional[str]:
    """Search arXiv for a paper with this DOI."""
    try:
        # arXiv API uses Atom XML format
        url = "http://export.arxiv.org/api/query"
        params = {"search_query": f'doi:"{doi}"', "max_results": 1}
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        # Look for arXiv ID in the response
        match = re.search(r"<id>http://arxiv\.org/abs/([\w./-]+)</id>", r.text)
        if match:
            arxiv_id = match.group(1)
            return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        return None
    except Exception:
        return None


# ============================================================
# Download
# ============================================================

def download_pdf(url: str, output_path: str, session: requests.Session) -> bool:
    """Download a PDF from a URL. Returns True if successful."""
    try:
        r = session.get(url, timeout=35, allow_redirects=True)
        content_type = (r.headers.get("Content-Type") or "").lower()
        if r.status_code == 200 and ("pdf" in content_type or r.url.lower().endswith(".pdf")):
            # Quick sanity check: file should start with %PDF
            content = r.content
            if content[:4] == b"%PDF":
                with open(output_path, "wb") as f:
                    f.write(content)
                return True
        return False
    except Exception:
        return False


def try_all_sources(doi: str, email: str, session: requests.Session, output_dir: str) -> Optional[str]:
    """Try CORE, Semantic Scholar, and arXiv in order. Return source name on success."""
    output_path = os.path.join(output_dir, f"{doi_to_filename(doi)}.pdf")

    # Source 1: CORE
    url = get_core_pdf_url(doi, session)
    if url and download_pdf(url, output_path, session):
        return "CORE"

    # Source 2: Semantic Scholar
    url = get_semantic_scholar_pdf_url(doi, session)
    if url and download_pdf(url, output_path, session):
        return "Semantic Scholar"

    # Source 3: arXiv
    url = get_arxiv_pdf_url(doi, session)
    if url and download_pdf(url, output_path, session):
        return "arXiv"

    return None


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Download PDFs from additional sources (CORE, Semantic Scholar, arXiv)")
    parser.add_argument("--email", required=True, help="Email for API user agent")
    parser.add_argument("--dois_file", default=str(ROOT / "dois_merged.txt"))
    parser.add_argument("--output_dir", default=str(ROOT / "PDFs"))
    parser.add_argument("--min_delay", type=float, default=0.5)
    parser.add_argument("--max_delay", type=float, default=1.0)
    args = parser.parse_args()

    dois = read_dois(args.dois_file)
    if not dois:
        print(f"No DOIs found in {args.dois_file}")
        return

    os.makedirs(args.output_dir, exist_ok=True)

    # Filter out DOIs we already have
    to_try = [doi for doi in dois if not already_downloaded(doi, args.output_dir)]

    print("="*60)
    print("  Enhanced Download (CORE + Semantic Scholar + arXiv)")
    print("="*60)
    print(f"  Total DOIs in file:    {len(dois)}")
    print(f"  Already downloaded:    {len(dois) - len(to_try)}")
    print(f"  Will attempt:          {len(to_try)}")
    print("="*60)

    if not to_try:
        print("\nNothing to download. All DOIs already have PDFs.")
        return

    # Build session
    session = requests.Session()
    session.headers.update({"User-Agent": f"extra-downloader/1.0 (mailto:{args.email})"})

    # Log file
    log_path = os.path.join(args.output_dir, "extra_sources_log.tsv")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("doi\tsource\toutcome\n")

    success_by_source = {"CORE": 0, "Semantic Scholar": 0, "arXiv": 0}
    failed = 0

    for doi in tqdm(to_try, desc="Trying sources", unit="doi", ncols=80):
        source = try_all_sources(doi, args.email, session, args.output_dir)
        with open(log_path, "a", encoding="utf-8") as f:
            if source:
                success_by_source[source] += 1
                f.write(f"{doi}\t{source}\tsuccess\n")
            else:
                failed += 1
                f.write(f"{doi}\t-\tno_pdf_found\n")
        time.sleep(uniform(args.min_delay, args.max_delay))

    total_success = sum(success_by_source.values())
    total_pdfs_now = len([f for f in os.listdir(args.output_dir) if f.endswith(".pdf")])

    print()
    print("="*60)
    print("  DOWNLOAD COMPLETE")
    print("="*60)
    print(f"  CORE successes:           {success_by_source['CORE']}")
    print(f"  Semantic Scholar successes: {success_by_source['Semantic Scholar']}")
    print(f"  arXiv successes:          {success_by_source['arXiv']}")
    print(f"  Total new PDFs:           {total_success}")
    print(f"  Failed (no source):       {failed}")
    print(f"  Total PDFs in folder now: {total_pdfs_now}")
    print("="*60)
    print(f"\n  Log saved to: {log_path}")
    print(f"\n  Next step: Rebuild the index to include the new papers:")
    print(f"  python rag_pipeline.py --pdf_dir PDFs --rebuild")


if __name__ == "__main__":
    main()
