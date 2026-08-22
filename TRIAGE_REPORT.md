# Corpus quality triage (measure only, no build)

Date: 2026-07-03. Purpose: quantify three data-quality problems across the whole
corpus before committing the canonical clean index. Nothing was built; the frozen
`chroma_db/` (collection `wind_farm_papers`) was not opened for writing; `owf_clean_v1`
was not created.

## Reference counts

- PDF files on disk (`PDFs/*.pdf`): **514** (the folder also holds 4 non-PDF log files).
- Frozen index: collection `wind_farm_papers`, **45,830** chunks (unchanged).
- Papers with OpenAlex metadata to check against (`paper_metadata.json`): 1,715 entries.
- PDFs whose DOI is NOT in `paper_metadata.json` (cannot title-check, but keepable): **55**.

## Method note

GROBID header extraction (`processHeaderDocument`) returns BibTeX; the extracted title
was fuzzy-matched to the OpenAlex title. Header matching alone is noisy: GROBID often
returns cover-sheet boilerplate, journal banners or repository UI instead of the title,
and the similarity score also punishes over-long titles. Every header-flagged PDF was
therefore re-checked against its own full body text (pypdf): a correct-but-mis-headered
paper contains its title somewhere in the body, a genuine wrong-file does not. The counts
below are after that full-text verification.

## Check 1: corpus integrity (wrong or misdownloaded PDFs)

**21 wrong-content PDFs** -> `wrong_pdf_candidates.csv` (columns: doi, expected_title,
extracted_header_title, header_sim, body_chars, classification). A further 70 PDFs were
flagged by the noisy header match but cleared by the full-text check (correct papers,
kept).

The 21 split by confidence:

- **Confirmed wrong-file (repository or publisher wrapper page saved instead of the
  article, or a different article bound in), ~12:** the body is a cover sheet or landing
  page, often identifiable by a boilerplate header and a tiny or duplicated body.
  Examples: `10.1016/j.coastaleng.2020.103790` and `10.1016/j.ecolmodel.2013.09.025`
  ("End User Agreement..."), `10.1016/j.renene.2016.10.035` and
  `10.1080/00207543.2017.1403661` (identical 7,221-char "Data Protection statement"),
  `10.2423/i22394303v6sp1` and `10.3390/jmse10122017` (identical 25,929-char "New OAR@UM
  Help" Malta repository page), `10.1007/s10236-025-01665-8` ("PUBLIER EN SCIENCES DE
  L'UNIVERS" HAL landing), `10.17736/ijope.2025.jc939` ("ISOPE MEMBERSHIP FORM"),
  `10.3391/ai.2016.11.4.08` and `10.1007/s11367-014-0709-2` (a different article's text),
  and `10.1016/j.apenergy.2009.05.031` (the Naxos/Cyprus case found in the sample).
- **Likely wrong or wrong-granularity, ~4:** e.g. `10.11646/zootaxa.5741.1.6` is a
  1,018,483-char whole Zootaxa volume rather than the single article;
  `10.1007/s10661-020-08603-9` (244k chars, 7% title overlap) and
  `10.1016/j.renene.2018.10.090` (52k chars, 0% overlap) do not contain their titles.
- **Borderline, needs a quick eyeball, ~5:** foreign-language papers where the title did
  not token-match but the paper may be correct, e.g. `10.1007/s00101-016-0154-7` (German),
  `10.1007/s13762-022-04577-y` (Turkish), `10.22449/2413-5577-2020-4-22-39` (overlap 0.58,
  just under threshold and probably fine).

## Check 2: glyph-encoded digits (unreadable numbers)

**1 paper** -> `glyph_affected.csv`. Only `10.3389/fclim.2024.1353939` (Frontiers Media)
shows the glyph-name symptom in pypdf text (611 hits, e.g. "PUBLISHED /two.tnum/six.tnum
February /two.tnum/zero.tnum/two.tnum/four.tnum" for a 2024 date). The problem is rare and
confined to a single Frontiers PDF, not systemic. Note the related "blank digit" variant
(digits silently dropped) is harder to detect automatically and was not separately
quantified; it appeared in this same paper under GROBID in the earlier sample.

## Check 3: extraction-failure preview

**6 at-risk PDFs** -> `extraction_risk.csv`. Fast header signal only; the definitive skip
list comes from the full-text build.

- 5 hard GROBID failures: 4 `NO_BLOCKS` (2 are book chapters:
  `10.1007/3-540-33291-x_15`, `10.1007/978-981-96-4569-5_48`; 2 are articles:
  `10.1016/j.enconman.2022.115742`, `10.22449/1573-160x-2019-3-185-201`) and 1 `HTTP 500`
  (`10.1049/cp.2019.0258`).
- 1 pypdf-unreadable body (`10.1016/j.enpol.2012.06.056`, 17 chars extracted).
- Book chapters are the main at-risk class: there are roughly 20 to 30 book-chapter or
  ISBN-style PDFs in the corpus (`/978-`, `/3-540-`), and GROBID rejects some of them
  outright. Expect a handful more failures at full-text build time.

## Estimated clean-and-usable corpus

**About 487 papers** = 514 minus the union of 21 wrong-content and 6 extraction-risk (27
distinct). This is a lower bound: roughly 5 of the 21 wrong-content flags are borderline
foreign-language papers that may be reinstated on inspection, nudging it towards ~490. The
55 PDFs with no OpenAlex metadata are included in "usable" but are unverified.

## Recommendations

- **Wrong-content (Check 1):** review the 21-row `wrong_pdf_candidates.csv` by eye (about
  10 minutes; body_chars and the extracted header make each obvious). Remove the confirmed
  repository-wrapper and different-article files and re-download them, or drop them and
  their eval items. The duplicated wrapper bodies (identical char counts) are the clearest.
- **Glyph (Check 2):** only 1 paper, so a glyph-name-to-digit normalisation map is overkill;
  simplest is to re-extract that single Frontiers PDF with pymupdf or pdfplumber (which
  usually map the glyphs to real digits) or exclude it. Add a small normalisation map only
  if more surface during the full build.
- **Extraction risk (Check 3):** accept the logged skip for the 2 book chapters; for the
  articles, a pymupdf fallback would likely recover `enconman` and `enpol`. Treat the full
  build's failure log as the authoritative skip list.

## Files created by this triage

- `TRIAGE_REPORT.md` (this file)
- `wrong_pdf_candidates.csv` (21 rows)
- `glyph_affected.csv` (1 row)
- `extraction_risk.csv` (6 rows)
