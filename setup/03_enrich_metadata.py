#!/usr/bin/env python3
"""
Enrich paper metadata from OpenAlex.

For each DOI in dois_merged.txt, queries OpenAlex to fetch:
  - Title
  - Authors
  - Publication year
  - Journal/venue name
  - Citation count
  - Abstract
  - Topics/concepts
  - Open access status

Saves to paper_metadata.json. This metadata can later be added to ChromaDB
chunks to enable filtering by year (key for memorisation analysis) and topic.

Usage:
  python 03_enrich_metadata.py \
      --dois_file dois_merged.txt \
      --output_file paper_metadata.json \
      --email shk00318@students.stir.ac.uk
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from random import uniform
from typing import Dict, List, Optional

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


def canonicalize_doi(doi: str) -> str:
    doi = (doi or "").strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return doi.strip()


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


def reconstruct_abstract(inverted_index: dict) -> str:
    """OpenAlex returns abstracts as inverted indexes for legal reasons. Rebuild as text."""
    if not inverted_index:
        return ""
    positions = []
    for word, pos_list in inverted_index.items():
        for pos in pos_list:
            positions.append((pos, word))
    positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in positions)


def fetch_openalex(doi: str, session: requests.Session) -> Optional[Dict]:
    """Fetch full metadata for a DOI from OpenAlex."""
    try:
        url = "https://api.openalex.org/works"
        params = {"filter": f"doi:https://doi.org/{doi}", "per-page": 1}
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None

        work = results[0]

        # Extract clean fields
        metadata = {
            "doi": doi,
            "openalex_id": work.get("id"),
            "title": work.get("title"),
            "year": work.get("publication_year"),
            "publication_date": work.get("publication_date"),
            "citation_count": work.get("cited_by_count"),
            "type": work.get("type"),
            "is_open_access": work.get("open_access", {}).get("is_oa"),
            "oa_status": work.get("open_access", {}).get("oa_status"),
            "language": work.get("language"),
        }

        # Authors
        authorships = work.get("authorships", [])
        metadata["authors"] = [
            a.get("author", {}).get("display_name")
            for a in authorships
            if a.get("author", {}).get("display_name")
        ]

        # Journal/venue
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        metadata["journal"] = source.get("display_name")
        metadata["publisher"] = source.get("host_organization_name")

        # Abstract (rebuild from inverted index)
        abstract_index = work.get("abstract_inverted_index")
        metadata["abstract"] = reconstruct_abstract(abstract_index)

        # Topics (OpenAlex's classification)
        concepts = work.get("concepts", [])
        metadata["concepts"] = [
            {"name": c.get("display_name"), "score": c.get("score"), "level": c.get("level")}
            for c in concepts[:5]  # top 5 concepts only
        ]

        topics = work.get("topics", [])
        metadata["topics"] = [
            {"name": t.get("display_name"), "score": t.get("score")}
            for t in topics[:3]  # top 3 topics
        ]

        return metadata

    except Exception as e:
        return None


def main():
    parser = argparse.ArgumentParser(description="Enrich paper metadata from OpenAlex")
    parser.add_argument("--dois_file", default=str(ROOT / "dois_merged.txt"))
    parser.add_argument("--output_file", default=str(ROOT / "paper_metadata.json"))
    parser.add_argument("--email", required=True, help="Email for OpenAlex polite pool")
    parser.add_argument("--min_delay", type=float, default=0.1)
    parser.add_argument("--max_delay", type=float, default=0.3)
    parser.add_argument("--resume", action="store_true", help="Resume from existing output file")
    args = parser.parse_args()

    dois = read_dois(args.dois_file)
    if not dois:
        print(f"No DOIs found in {args.dois_file}")
        return

    # Load existing metadata if resuming
    existing = {}
    if args.resume and os.path.exists(args.output_file):
        with open(args.output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        existing = {item["doi"]: item for item in data if item.get("doi")}
        print(f"Resuming from {len(existing)} existing entries")

    to_fetch = [doi for doi in dois if doi not in existing]

    print("="*60)
    print("  OpenAlex Metadata Enrichment")
    print("="*60)
    print(f"  Total DOIs:        {len(dois)}")
    print(f"  Already enriched:  {len(existing)}")
    print(f"  To fetch:          {len(to_fetch)}")
    print("="*60)

    if not to_fetch:
        print("\nAll DOIs already enriched.")
        return

    session = requests.Session()
    # OpenAlex prefers an email in the User-Agent for the "polite pool" (faster)
    session.headers.update({"User-Agent": f"metadata-enrichment/1.0 (mailto:{args.email})"})

    enriched = dict(existing)
    failed = []

    for doi in tqdm(to_fetch, desc="Fetching metadata", unit="doi", ncols=80):
        metadata = fetch_openalex(doi, session)
        if metadata:
            enriched[doi] = metadata
        else:
            failed.append(doi)

        # Save every 50 records in case of interruption
        if len(enriched) % 50 == 0:
            with open(args.output_file, "w", encoding="utf-8") as f:
                json.dump(list(enriched.values()), f, indent=2, ensure_ascii=False)

        time.sleep(uniform(args.min_delay, args.max_delay))

    # Final save
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(list(enriched.values()), f, indent=2, ensure_ascii=False)

    # Save failed DOIs
    if failed:
        with open(ROOT / "metadata_failed_dois.txt", "w", encoding="utf-8") as f:
            for doi in failed:
                f.write(doi + "\n")

    # Stats
    years = [e.get("year") for e in enriched.values() if e.get("year")]
    oa_count = sum(1 for e in enriched.values() if e.get("is_open_access"))
    journals = {}
    for e in enriched.values():
        j = e.get("journal")
        if j:
            journals[j] = journals.get(j, 0) + 1

    print()
    print("="*60)
    print("  ENRICHMENT COMPLETE")
    print("="*60)
    print(f"  Successfully enriched: {len(enriched)}")
    print(f"  Failed:                {len(failed)}")
    print()
    if years:
        print(f"  Publication year range: {min(years)} - {max(years)}")
        recent = sum(1 for y in years if y >= 2023)
        print(f"  Recent papers (2023+):  {recent}")
    print(f"  Open access papers:     {oa_count}")
    print()
    print(f"  Top 10 journals:")
    top_journals = sorted(journals.items(), key=lambda x: x[1], reverse=True)[:10]
    for journal, count in top_journals:
        print(f"    {count:4d}  {journal}")
    print()
    print(f"  Metadata saved to: {args.output_file}")
    if failed:
        print(f"  Failed DOIs saved to: metadata_failed_dois.txt")


if __name__ == "__main__":
    main()
