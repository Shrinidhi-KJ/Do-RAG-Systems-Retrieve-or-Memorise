#!/usr/bin/env python3
"""
Build a pilot evaluation set from the Eklipse report.

The Eklipse report is a 157-page EU scientific synthesis containing hundreds of
factual claims with citations. Each claim has the form:
  "X has Y effect on Z (Smith et al., 2020; Jones et al., 2022)."

This script:
  1. Extracts the report text
  2. Finds factual claims (sentences with inline citations)
  3. Identifies the DOIs of cited papers (matching against our corpus)
  4. Builds a ground-truth evaluation set: (question, expected_source_dois)

The resulting eval set lets us measure retrieval recall (does the RAG system
fetch the right papers?) BEFORE we get the official questions from Buglalilar.

Usage:
  python 04_build_pilot_eval_set.py \
      --report_pdf "2025-10-27-Eklipse_Report_WindFarm_Final.pdf" \
      --corpus_metadata paper_metadata.json \
      --output_file pilot_eval_set.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set

# Repo root = parent of setup/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent

# Dependency check
try:
    from pypdf import PdfReader
except ImportError:
    print("Installing pypdf...")
    os.system(f"{sys.executable} -m pip install pypdf")
    from pypdf import PdfReader

try:
    from tqdm import tqdm
except ImportError:
    print("Installing tqdm...")
    os.system(f"{sys.executable} -m pip install tqdm")
    from tqdm import tqdm


# ============================================================
# Step 1: Extract text from Eklipse report
# ============================================================

def extract_pdf_text(pdf_path: str) -> str:
    """Extract all text from the Eklipse report."""
    print(f"Reading {pdf_path}...")
    reader = PdfReader(pdf_path)
    print(f"  Pages: {len(reader.pages)}")

    parts = []
    for page in tqdm(reader.pages, desc="Extracting", unit="page", ncols=80):
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)


# ============================================================
# Step 2: Find factual claims with citations
# ============================================================

# Surname part: capital word, optionally with European particles (de, van, der, etc.)
SURNAME_PART = r"[A-Z][a-zA-ZÀ-ÿ'\-]+(?:\s+(?:de|van|der|den|del|della|di|du|le|la|von|zu|el)\s+[A-Z][a-zA-ZÀ-ÿ'\-]+)?"

# Universal citation extractor: catches "(Smith, 2020)", "(Smith et al., 2020)",
# "(Smith & Jones, 2020)", "Smith et al. (2020)", "Smith & Jones (2020)", etc.
# Returns tuples of (surname, year).
ALL_CITATIONS = re.compile(
    rf"({SURNAME_PART})(?:\s+et\s+al\.?|\s*(?:&|and)\s*{SURNAME_PART})?\s*[,\(\s]\s*(\d{{4}})[a-z]?"
)

# For removing citations from text when building questions
CITATION_PAREN_FOR_REMOVAL = re.compile(
    rf"\(\s*{SURNAME_PART}(?:\s+et\s+al\.?|\s*(?:&|and)\s*{SURNAME_PART})?\s*,?\s*\d{{4}}[a-z]?(?:\s*;\s*{SURNAME_PART}(?:\s+et\s+al\.?|\s*(?:&|and)\s*{SURNAME_PART})?\s*,?\s*\d{{4}}[a-z]?)*\s*\)"
)
CITATION_NARRATIVE_FOR_REMOVAL = re.compile(
    rf"{SURNAME_PART}(?:\s+et\s+al\.?|\s*(?:&|and)\s*{SURNAME_PART})?\s*\(\s*\d{{4}}[a-z]?\s*\)"
)


def parse_individual_citation(text: str) -> Optional[Dict]:
    """Parse one 'Author, Year' or 'Author et al., Year' string."""
    text = text.strip()
    m = re.match(
        rf"({SURNAME_PART})(?:\s+et\s+al\.?|\s*(?:&|and)\s*{SURNAME_PART})?\s*,?\s*(\d{{4}})[a-z]?$",
        text,
    )
    if m:
        return {"first_author": m.group(1).strip(), "year": int(m.group(2))}
    return None


def find_claims_with_citations(text: str) -> List[Dict]:
    """Find sentences containing inline citations."""
    # Normalize text: collapse newlines, fix common PDF extraction artifacts
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)  # rejoin hyphenated words
    text = re.sub(r"\n+", " ", text)  # collapse newlines
    text = re.sub(r"\s+", " ", text)  # normalize whitespace

    # Mask abbreviations and decimals BEFORE splitting on sentence endings
    # This prevents splitting at "et al." or "0.5"
    text_masked = text
    text_masked = re.sub(r"et\s+al\.", "et_al_MARKER", text_masked)
    text_masked = re.sub(r"i\.e\.", "ie_MARKER", text_masked)
    text_masked = re.sub(r"e\.g\.", "eg_MARKER", text_masked)
    text_masked = re.sub(r"cf\.", "cf_MARKER", text_masked)
    text_masked = re.sub(r"vs\.", "vs_MARKER", text_masked)
    text_masked = re.sub(r"Fig\.", "Fig_MARKER", text_masked)
    text_masked = re.sub(r"approx\.", "approx_MARKER", text_masked)
    text_masked = re.sub(r"ca\.", "ca_MARKER", text_masked)
    text_masked = re.sub(r"(\d)\.(\d)", r"\1_DOT_\2", text_masked)

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text_masked)

    def unmask(s: str) -> str:
        s = s.replace("et_al_MARKER", "et al.")
        s = s.replace("ie_MARKER", "i.e.")
        s = s.replace("eg_MARKER", "e.g.")
        s = s.replace("cf_MARKER", "cf.")
        s = s.replace("vs_MARKER", "vs.")
        s = s.replace("Fig_MARKER", "Fig.")
        s = s.replace("approx_MARKER", "approx.")
        s = s.replace("ca_MARKER", "ca.")
        s = re.sub(r"(\d)_DOT_(\d)", r"\1.\2", s)
        return s

    sentences = [unmask(s) for s in sentences]

    claims = []
    for i, sent in enumerate(sentences):
        sent = sent.strip()
        if len(sent) < 40 or len(sent) > 1500:
            continue
        if sent.count(".") > 20:
            continue
        alpha_ratio = sum(c.isalpha() for c in sent) / max(len(sent), 1)
        if alpha_ratio < 0.5:
            continue
        if sent.startswith(("Figure ", "Table ", "Fig. ", "Fig ")):
            continue

        # Filter out non-claim text (bullet points, methodology fragments, etc.)
        if not is_valid_claim(sent):
            continue

        # Extract ALL citations from this sentence using the universal extractor
        matches = ALL_CITATIONS.findall(sent)

        if matches:
            # Filter out matches that are obviously not citations (e.g., section refs)
            parsed_citations = []
            for surname, year_str in matches:
                try:
                    year = int(year_str)
                    # Sanity check: must be reasonable publication year
                    if year < 1900 or year > 2030:
                        continue
                    # Skip very common false-positive surnames
                    if surname.lower() in {"figure", "table", "section", "chapter", "annex", "appendix"}:
                        continue
                    parsed_citations.append({"first_author": surname.strip(), "year": year})
                except ValueError:
                    continue

            if not parsed_citations:
                continue

            # Deduplicate
            seen = set()
            unique_citations = []
            for c in parsed_citations:
                key = (c["first_author"].lower(), c["year"])
                if key not in seen:
                    seen.add(key)
                    unique_citations.append(c)

            claims.append({
                "claim_text": sent,
                "citations": unique_citations,
                "sentence_index": i,
            })

    return claims


# ============================================================
# Step 3: Match citations to our corpus
# ============================================================

def load_corpus_metadata(path: str) -> List[Dict]:
    """Load paper metadata to enable matching citations to DOIs."""
    if not os.path.exists(path):
        print(f"Warning: {path} not found. Cannot match citations to DOIs.")
        print("Run 03_enrich_metadata.py first to fetch paper metadata.")
        return []

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_author_year_index(corpus: List[Dict]) -> Dict[Tuple[str, int], List[str]]:
    """
    Build an index mapping (first_author_surname, year) -> list of matching DOIs.
    Indexes by multiple surname forms to handle particles like "de", "van", etc.
    """
    index = {}
    for paper in corpus:
        doi = paper.get("doi")
        year = paper.get("year")
        authors = paper.get("authors", [])
        if not doi or not year or not authors:
            continue

        first_author = authors[0]
        if not first_author:
            continue

        # Get surname (handle "Smith, John" or "John Smith" formats)
        if "," in first_author:
            surname = first_author.split(",")[0].strip()
        else:
            # For "John de Mesel" we want "de Mesel" (everything after first name)
            parts = first_author.split()
            if len(parts) <= 1:
                surname = first_author.strip()
            else:
                # Try to detect particles like "de", "van", "der" and include them
                particles = {"de", "van", "der", "den", "del", "della", "di", "du", "le", "la", "von", "zu", "el"}
                # If second-to-last word is a particle, include from there
                if len(parts) >= 3 and parts[-2].lower() in particles:
                    surname = " ".join(parts[-2:])
                elif len(parts) >= 4 and parts[-3].lower() in particles:
                    surname = " ".join(parts[-3:])
                else:
                    surname = parts[-1].strip()

        surname_norm = surname.lower().strip()

        # Index by full surname (e.g., "de mesel")
        key = (surname_norm, year)
        if key not in index:
            index[key] = []
        index[key].append(doi)

        # Also index by just the last word (e.g., "mesel") to catch cases where
        # Eklipse drops the particle
        last_word = surname_norm.split()[-1] if " " in surname_norm else surname_norm
        if last_word != surname_norm:
            alt_key = (last_word, year)
            if alt_key not in index:
                index[alt_key] = []
            index[alt_key].append(doi)

    return index


def match_citation_to_dois(citation: Dict, index: Dict) -> List[str]:
    """Look up a citation (author surname + year) in our corpus index."""
    surname = citation["first_author"].lower().strip()
    year = citation["year"]

    # Try exact match first
    key = (surname, year)
    if key in index:
        return index[key]

    # Try year +/- 1 (publication date vs. year of acceptance)
    for offset in [-1, 1]:
        alt_key = (surname, year + offset)
        if alt_key in index:
            return index[alt_key]

    # Try just last word of surname (drops particles)
    if " " in surname:
        last_word = surname.split()[-1]
        key = (last_word, year)
        if key in index:
            return index[key]
        for offset in [-1, 1]:
            alt_key = (last_word, year + offset)
            if alt_key in index:
                return index[alt_key]

    return []


# ============================================================
# Step 4: Generate evaluation questions from claims
# ============================================================

def claim_to_question(claim_text: str) -> str:
    """
    Convert a factual claim sentence into a question.
    Handles narrative citations carefully so the resulting question still makes sense.
    """
    cleaned = claim_text

    # Replace narrative citations like "Smith et al. (2020) showed X" with "Research has shown X"
    # This avoids ending up with a fragment like "showed X" that starts mid-sentence
    cleaned = re.sub(
        rf"^{SURNAME_PART}(?:\s+et\s+al\.?|\s*(?:&|and)\s*{SURNAME_PART})?\s*\(\s*\d{{4}}[a-z]?\s*\)\s*(showed|reported|found|demonstrated|observed|noted|suggested|argued|claimed|indicated)\b",
        r"Research \1",
        cleaned,
    )
    # For mid-sentence narrative citations, just replace the citation with "research"
    cleaned = re.sub(
        rf"{SURNAME_PART}(?:\s+et\s+al\.?|\s*(?:&|and)\s*{SURNAME_PART})?\s*\(\s*\d{{4}}[a-z]?\s*\)",
        "research",
        cleaned,
    )

    # Remove parenthetical citations entirely - sentence remains intact
    cleaned = CITATION_PAREN_FOR_REMOVAL.sub("", cleaned)

    # Clean up
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = cleaned.rstrip(".").strip()

    return f"According to the scientific literature: {cleaned}?"


def is_valid_claim(text: str) -> bool:
    """Filter out bullet points, methodology fragments, and other non-claim text."""
    # Reject bullet point indicators
    if any(marker in text for marker in ["›", "◊", "•", "·"]):
        return False
    # Reject anything with too many colons (likely a list)
    if text.count(":") > 2:
        return False
    # Reject if starts with lowercase (likely a sentence fragment)
    first_alpha = next((c for c in text if c.isalpha()), None)
    if first_alpha and not first_alpha.isupper():
        return False
    # Reject if too short to be a real claim
    word_count = len(text.split())
    if word_count < 8:
        return False
    # Reject lines that look like section headings or labels
    if text.endswith(":"):
        return False
    # Reject if contains too many abbreviations / acronyms (usually methodology)
    abbrev_count = len(re.findall(r"\b[A-Z]{2,}\b", text))
    if abbrev_count > 4:
        return False
    return True


# ============================================================
# Main
# ============================================================

def get_downloaded_dois(pdf_dir: str) -> Set[str]:
    """Get the set of DOIs we actually have PDFs for."""
    dois = set()
    if not os.path.exists(pdf_dir):
        return dois
    for filename in os.listdir(pdf_dir):
        if filename.endswith(".pdf"):
            # Convert filename back to DOI: 10.1016_j.foo.bar.pdf -> 10.1016/j.foo.bar
            doi = filename.replace(".pdf", "").replace("_", "/", 1)
            dois.add(doi.lower())
    return dois


def main():
    parser = argparse.ArgumentParser(description="Build pilot evaluation set from Eklipse report")
    parser.add_argument("--report_pdf", required=True, help="Path to the Eklipse report PDF")
    parser.add_argument("--corpus_metadata", default=str(ROOT / "paper_metadata.json"), help="Path to paper_metadata.json from step 03")
    parser.add_argument("--output_file", default=str(ROOT / "pilot_eval_set.json"))
    parser.add_argument("--max_claims", type=int, default=100, help="Limit to first N matched claims")
    parser.add_argument("--pdf_dir", default=str(ROOT / "PDFs"), help="Only match against DOIs we have PDFs for")
    parser.add_argument("--include_paywalled", action="store_true", help="Match against all DOIs, not just downloaded ones")
    args = parser.parse_args()

    # Resolve a relative report path against the repo root (CWD-independent).
    _rp = Path(args.report_pdf)
    if not _rp.is_absolute():
        args.report_pdf = str(ROOT / _rp)

    print("="*60)
    print("  Pilot Evaluation Set Builder")
    print("="*60)
    print()

    # Step 1: Extract Eklipse text
    if not os.path.exists(args.report_pdf):
        print(f"Error: {args.report_pdf} not found")
        sys.exit(1)

    text = extract_pdf_text(args.report_pdf)
    print(f"  Extracted {len(text):,} characters")
    print()

    # Step 2: Find claims with citations
    print("Finding factual claims with citations...")
    claims = find_claims_with_citations(text)
    print(f"  Found {len(claims)} claims with inline citations")
    print()

    # Step 3: Load corpus metadata and downloaded DOIs
    print("Loading corpus metadata...")
    corpus = load_corpus_metadata(args.corpus_metadata)
    print(f"  Loaded metadata for {len(corpus)} papers")

    # Get downloaded DOIs unless --include_paywalled
    downloaded_dois = set()
    if not args.include_paywalled:
        downloaded_dois = get_downloaded_dois(args.pdf_dir)
        print(f"  Downloaded PDFs available: {len(downloaded_dois)}")
        # Filter corpus to only downloaded papers
        corpus = [p for p in corpus if p.get("doi", "").lower() in downloaded_dois]
        print(f"  Filtered corpus to: {len(corpus)} papers we actually have PDFs for")
    else:
        print(f"  Including ALL papers (paywalled too)")

    if not corpus:
        print()
        print("WARNING: No corpus metadata available.")
        print("Saving claims without DOI matching.")
        eval_set = [
            {
                "claim_text": c["claim_text"],
                "question": claim_to_question(c["claim_text"]),
                "citations": c["citations"],
                "matched_dois": [],
            }
            for c in claims[:args.max_claims]
        ]
    else:
        index = build_author_year_index(corpus)
        print(f"  Built index with {len(index)} (author, year) keys")
        print()

        # Match each claim
        print("Matching citations to corpus DOIs...")
        eval_set = []
        for claim in claims:
            matched_dois = []
            for citation in claim["citations"]:
                dois = match_citation_to_dois(citation, index)
                matched_dois.extend(dois)

            # Only keep claims where at least one citation matches our corpus
            if matched_dois:
                eval_set.append({
                    "claim_text": claim["claim_text"],
                    "question": claim_to_question(claim["claim_text"]),
                    "citations": claim["citations"],
                    "matched_dois": list(set(matched_dois)),
                })

            if len(eval_set) >= args.max_claims:
                break

    # Save
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(eval_set, f, indent=2, ensure_ascii=False)

    # Stats
    print()
    print("="*60)
    print("  EVALUATION SET BUILT")
    print("="*60)
    print(f"  Total claims extracted:    {len(claims)}")
    print(f"  Claims with matched DOIs:  {len(eval_set)}")
    if eval_set:
        avg_matches = sum(len(e["matched_dois"]) for e in eval_set) / len(eval_set)
        print(f"  Average DOIs per claim:    {avg_matches:.1f}")
    print(f"  Saved to:                  {args.output_file}")
    print()
    print("  Example entry:")
    if eval_set:
        example = eval_set[0]
        print(f"  Claim: {example['claim_text'][:150]}...")
        print(f"  Question: {example['question'][:150]}...")
        print(f"  Matched DOIs: {example['matched_dois'][:3]}")
    print()
    print("  Next step: Use this eval set to measure retrieval recall.")
    print("  For each question, ask the RAG system to retrieve top-k chunks,")
    print("  then check if any of those chunks come from the matched_dois.")


if __name__ == "__main__":
    main()
