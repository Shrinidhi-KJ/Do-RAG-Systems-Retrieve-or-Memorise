#!/usr/bin/env python3
"""
Wrapper around doi_download_only.py logic with real-time progress tracking.
Shows a progress bar for both URL discovery and PDF download phases.
"""

import os
import sys
import time
from pathlib import Path
from random import uniform

# Repo root = parent of setup/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent

# Reuse functions from the original script
from doi_download_only import (
    read_dois,
    build_session,
    build_candidate_pdf_urls,
    download_pdf_from_candidates,
    write_lines,
    append_line,
)

try:
    from tqdm import tqdm
except ImportError:
    print("Installing tqdm for progress bars...")
    os.system(f"{sys.executable} -m pip install tqdm")
    from tqdm import tqdm


def main():
    import argparse

    p = argparse.ArgumentParser(description="Download PDFs with progress tracking")
    p.add_argument("--email", required=True)
    p.add_argument("--dois_file", default=str(ROOT / "dois_merged.txt"))
    p.add_argument("--output_dir", default=str(ROOT / "PDFs"))
    p.add_argument("--min_delay", type=float, default=0.5)
    p.add_argument("--max_delay", type=float, default=1.0)
    p.add_argument("--cookies_file", default="")
    args = p.parse_args()

    dois = read_dois(args.dois_file)
    if not dois:
        print(f"No DOIs found in {args.dois_file}")
        return

    print(f"\n{'='*60}")
    print(f"  PDF Download Pipeline")
    print(f"  Total DOIs: {len(dois)}")
    print(f"  Output folder: {args.output_dir}")
    print(f"{'='*60}\n")

    ua = f"doi-download-progress/1.0 (mailto:{args.email})"
    session = build_session(ua, args.cookies_file)

    # Phase 1: Discover candidate PDF URLs
    print("Phase 1: Discovering PDF URLs for each DOI...\n")
    candidate_map = {}
    no_url_count = 0
    skipped_count = 0

    os.makedirs(args.output_dir, exist_ok=True)

    for doi in tqdm(dois, desc="Finding URLs", unit="doi", ncols=80):
        # Skip if already downloaded
        from doi_download_only import doi_to_filename
        pdf_path = os.path.join(args.output_dir, f"{doi_to_filename(doi)}.pdf")
        if os.path.exists(pdf_path):
            skipped_count += 1
            continue

        urls = build_candidate_pdf_urls(doi, args.email, session)
        if urls:
            candidate_map[doi] = urls
        else:
            no_url_count += 1
        time.sleep(uniform(0.2, 0.5))

    print(f"\n  Found URLs for: {len(candidate_map)} DOIs")
    print(f"  No URLs found: {no_url_count} DOIs")
    print(f"  Already downloaded: {skipped_count} DOIs")

    if not candidate_map:
        print("\nNo new PDFs to download.")
        return

    # Phase 2: Download PDFs
    print(f"\nPhase 2: Downloading {len(candidate_map)} PDFs...\n")

    attempted_file = os.path.join(args.output_dir, "attempted_urls.tsv")
    write_lines(attempted_file, ["doi\turl\tstatus\tcontent_type\toutcome"])

    downloaded = []
    failed = []

    for doi in tqdm(candidate_map, desc="Downloading", unit="pdf", ncols=80):
        ok = download_pdf_from_candidates(
            doi,
            candidate_map[doi],
            args.output_dir,
            session,
            attempted_file,
        )
        if ok:
            downloaded.append(doi)
        else:
            failed.append(doi)
        time.sleep(uniform(args.min_delay, args.max_delay))

    # Summary
    total_pdfs = len([f for f in os.listdir(args.output_dir) if f.endswith(".pdf")])

    print(f"\n{'='*60}")
    print(f"  DOWNLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"  Total DOIs processed: {len(dois)}")
    print(f"  Already had:          {skipped_count}")
    print(f"  No URL found:         {no_url_count}")
    print(f"  Download attempted:   {len(candidate_map)}")
    print(f"  Successfully downloaded: {len(downloaded)}")
    print(f"  Failed:               {len(failed)}")
    print(f"  Total PDFs in folder: {total_pdfs}")
    print(f"{'='*60}")

    # Save results
    write_lines(os.path.join(args.output_dir, "downloaded_dois.txt"), downloaded)
    write_lines(os.path.join(args.output_dir, "failed_dois.txt"), failed)


if __name__ == "__main__":
    main()
