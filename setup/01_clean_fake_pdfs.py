#!/usr/bin/env python3
"""
Cleanup script: Identify and remove fake PDF files.
These are HTML paywall pages that were saved with .pdf extension during download.
"""

import os
import sys
from pathlib import Path

# Repo root = parent of setup/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent


def is_fake_pdf(filepath: str) -> tuple[bool, str]:
    """Check if a file is actually a PDF or HTML disguised as PDF."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(200).lower()

        # Valid PDFs start with %PDF
        if header.startswith(b"%pdf"):
            return False, "valid_pdf"

        # Common HTML indicators
        if b"<!doc" in header:
            return True, "html_doctype"
        if b"<html" in header:
            return True, "html_tag"
        if b"<head" in header and b"<title" in header:
            return True, "html_head"

        # Sometimes it's an XML page or error response
        if b"<?xml" in header:
            return True, "xml_page"

        # If we can't tell from the header, flag for manual review
        return True, "unknown_format"

    except Exception as e:
        return True, f"read_error: {e}"


def main():
    pdf_dir = ROOT / "PDFs"

    if not pdf_dir.exists():
        print(f"Error: {pdf_dir} folder not found.")
        print("Run this script from the data_pipeline folder.")
        sys.exit(1)

    print("="*60)
    print("  Fake PDF Cleanup")
    print("="*60)
    print()

    pdf_files = list(pdf_dir.glob("*.pdf"))
    print(f"Total files in PDFs folder: {len(pdf_files)}")
    print()

    fake_files = []
    valid_files = []

    for pdf_path in pdf_files:
        is_fake, reason = is_fake_pdf(str(pdf_path))
        if is_fake:
            fake_files.append((pdf_path, reason))
        else:
            valid_files.append(pdf_path)

    print(f"Valid PDFs:    {len(valid_files)}")
    print(f"Fake/HTML:     {len(fake_files)}")
    print()

    if not fake_files:
        print("No fake PDFs detected. Nothing to clean.")
        return

    print("Fake files found:")
    print("-" * 60)
    for path, reason in fake_files:
        print(f"  [{reason}] {path.name}")
    print()

    # Save list to file before deleting
    with open(ROOT / "fake_pdfs_removed.txt", "w", encoding="utf-8") as f:
        f.write("filename\treason\n")
        for path, reason in fake_files:
            f.write(f"{path.name}\t{reason}\n")
    print(f"List saved to: fake_pdfs_removed.txt")
    print()

    # Confirm before deleting
    response = input(f"Delete {len(fake_files)} fake files? (yes/no): ").strip().lower()
    if response != "yes":
        print("Aborted. No files deleted.")
        return

    removed = 0
    for path, reason in fake_files:
        try:
            path.unlink()
            removed += 1
        except Exception as e:
            print(f"  Could not delete {path.name}: {e}")

    print()
    print(f"Removed {removed} fake files.")
    print(f"Remaining PDFs: {len(pdf_files) - removed}")
    print()
    print("Next step: Rebuild the index with:")
    print("  python rag_pipeline.py --pdf_dir PDFs --rebuild")


if __name__ == "__main__":
    main()
