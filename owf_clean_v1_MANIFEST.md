# owf_clean_v1 build manifest

Date: 2026-07-08. Collection `owf_clean_v1` in `chroma_db_clean` (the frozen `chroma_db/` was not opened for writing).

## Totals

- PDFs on disk considered : 523
- Included                : 501
- Excluded (triage policy): 15
- Skipped (build failures): 7
- Final papers in index   : 501
- Total chunks (rows)     : 34502
- Chroma collection count : 34502

## Extractor / recipe

- GROBID lightweight CRF image (lfoppiano/grobid:0.8.0), processFulltextDocument.
- KEEP title(meta)/abstract/body sections + captions; DROP TEI back + drop-list headings.
- Chunk 1000/200, section-bounded.
- BGE recipe: query prefix on queries, passages plain, normalised.
- Glyph paper 10.3389/fclim.2024.1353939: included via pymupdf (digits render correctly).

## Excluded (by category, with reason)

### Confirmed wrong-content

- `10.1007/s10236-025-01665-8` - wrong_content: HAL repository landing (PUBLIER EN SCIENCES)
- `10.1007/s11367-014-0709-2` - wrong_content: different document (NREAP projections)
- `10.1016/j.apenergy.2009.05.031` - wrong_content: Cyprus Open Science policy, not the Naxos paper
- `10.1016/j.coastaleng.2020.103790` - wrong_content: End User Agreement wrapper page
- `10.1016/j.ecolmodel.2013.09.025` - wrong_content: End User Agreement wrapper (CentAUR)
- `10.1016/j.renene.2016.10.035` - wrong_content: Data Protection statement wrapper
- `10.1080/00207543.2017.1403661` - wrong_content: Data Protection statement wrapper (duplicate)
- `10.17736/ijope.2017.cl03` - wrong_content: different ISOPE article bound in
- `10.17736/ijope.2025.jc939` - wrong_content: ISOPE membership form
- `10.2423/i22394303v6sp1` - wrong_content: OAR@UM repository landing page
- `10.3390/jmse10122017` - wrong_content: OAR@UM repository landing page (duplicate)
- `10.3391/ai.2016.11.4.08` - wrong_content: different article (Comments on Mediterranean...)

### Wrong-granularity

- `10.1007/s10661-020-08603-9` - wrong_granularity: 244k chars, 7% title overlap
- `10.1016/j.renene.2018.10.090` - wrong_granularity: 52k chars, 0% title overlap
- `10.11646/zootaxa.5741.1.6` - wrong_granularity: 1M-char whole Zootaxa volume, not the article

## Skipped (authoritative build skip list)

- `10.1007/3-540-33291-x_15` - grobid_fail: GROBID returned 500 for PDFs\10.1007_3-540-33291-x_15.pdf: [NO_
- `10.1007/978-981-96-4569-5_48` - grobid_fail: GROBID returned 500 for PDFs\10.1007_978-981-96-4569-5_48.pdf: 
- `10.1007/s00227-016-2918-7` - grobid: parsed but produced no usable content
- `10.1016/j.enpol.2012.06.056` - grobid: parsed but produced no usable content
- `10.1049/cp.2019.0258` - grobid_fail: GROBID returned 500 for PDFs\10.1049_cp.2019.0258.pdf: [BAD_INP
- `10.1051/e3sconf_202020702014` - grobid: parsed but produced no usable content
- `10.22449/1573-160x-2019-3-185-201` - grobid_fail: GROBID returned 500 for PDFs\10.22449_1573-160x-2019-3-185-201.

## Glyph paper outcome

- `10.3389/fclim.2024.1353939`: included - glyph-fixed via pymupdf full text (no section structure) (100 chunks)

## D3 source rescue (provenance)

Reason: D3 source rescue. Missing D3 eval-set source papers brought into owf_clean_v1
through the identical clean pipeline (GROBID recipe, KEEP/DROP rules, section-bounded
1000/200 chunks, metadata, BGE recipe) and APPENDED to the collection across two runs.
The frozen chroma_db/ was never opened for writing (checksum verified unchanged each run).
No experiment was run.

Appended 2026-07-08 (run 1, 3 papers, 207 chunks):

- `10.1093/icesjms_fsy006` (Roach et al. 2018, European lobster catch rates) - included, 55 chunks. Feeds D3-01. Stored DOI mangled from true 10.1093/icesjms/fsy006 (multi-slash).
- `10.1093/icesjms_fsu215` (Bastardie et al. 2015, effort displacement under spatial restrictions) - included, 82 chunks. Feeds D3-15. True 10.1093/icesjms/fsu215.
- `10.1007/s10750-021-04553-6` (Mavraki et al. 2021, attraction-production hypothesis) - included, 70 chunks. Feeds D3-14. Provenance completed: entry added to paper_metadata.json and chunk titles aligned to the canonical CrossRef title.

Appended 2026-07-08 (run 2, 6 papers, 339 chunks):

- `10.1016/j.seares.2009.01.008` (Maar et al. 2009, blue mussels around turbine foundations) - included, 96 chunks. Feeds D3-02 (replaces the mis-cited Kotta).
- `10.1007/s10750-014-1997-z` (Vandendriessche et al. 2015, Belgian OWF epibenthos and fish) - included, 52 chunks. Feeds D3-10.
- `10.1016/j.marenvres.2017.01.009` (Van Hal et al. 2017, fish community change) - included, 62 chunks. Feeds D3-04, D3-12.
- `10.1016/j.marpol.2009.12.004` (Berkenhagen et al. 2010, MSP decision bias) - included, 22 chunks. Feeds D3-13.
- `10.1016/j.marpol.2023.105574` (Puts et al. 2023, Ecopath fisheries/OWF/MPA trade-offs) - included, 84 chunks. Feeds D3-11.
- `10.1016/j.fishres.2024.106937` (Werner et al. 2024, OWF foundations as artificial reefs) - included, 23 chunks (5-page short note). Feeds D3-04, D3-05, D3-15.

Free rescues (already present under mangled DOIs, no action needed):

- `10.1093/icesjms_fsz050` (Barbut et al. 2020) - included, 55 chunks. Feeds D3-07. True 10.1093/icesjms/fsz050.
- `10.1093/icesjms_fsac107` (Buyse et al. 2022) - included, 50 chunks. Feeds D3-09. True 10.1093/icesjms/fsac107.

No extraction failures in either run; skip list unchanged.
