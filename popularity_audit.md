# Popularity tag audit (D3 eval set)

Read-only investigation into how the `tags.popularity` field on `d3_eval_set.json`
was assigned. Uses only what is in this repo. Nothing was re-tagged, re-run, or
inferred beyond what the evidence supports. Date: 2026-07-13.

---

## 1. Popularity values (from `d3_eval_set.json`)

| item_id | popularity | fact (short) |
|---------|-----------|--------------|
| D3-01 | medium | Temporary lobster-fishery closure raised lobster abundance/size |
| D3-02 | low | Blue mussels higher on pillars reach ~7-18x higher biomass |
| D3-03 | low | Ecosystem-model reef scenario: top-predator (cod) activity increased |
| D3-04 | high | Southern North Sea monopiles attract fish/crab (artificial reef) |
| D3-05 | low | Cod catch rates higher around rock-protected monopiles |
| D3-07 | low | Spatial overlap of wind farms and flatfish grounds |
| D3-08 | high | Atlantic cod strongly attracted to wind-farm artificial reefs |
| D3-09 | medium | Plaice ~4x more abundant on scour-protection sand patches |
| D3-10 | low | Belgian North Sea: real edge/spillover effects |
| D3-11 | medium | Reduced fishing in closed areas |
| D3-12 | low | New fish species appearing at wind-farm sites |
| D3-16 | low | Edible/velvet crab attracted to hard substrate |

**Counts: high 2, medium 3, low 7 (total 12).**
Confirmed: the "2 high / 3 medium / 7 low" description is correct.

---

## 2. Search for a written rule

Grep across the whole repo (code, JSON, markdown, logs, docstrings) for
`popularity`, `popular`, `well-established`, `long-tail`, `long tail`, `how widely`,
`citation`, `citation_count`, `cited_by`, `n_papers`, `source_count`, `prevalence`.

Every `popularity` hit is either the STORED tag or code that READS/REPORTS it. No hit
is code that COMPUTES it:

- `d3_eval_set.json` — the stored constant, e.g. line 11 `"tags": {... "popularity": "medium"}`.
- `analysis_d3.md:57,59,61,74,82` — the popularity slice REPORTS the tag; it does not create it.
- `analysis_d3.json:278-` — `popularity_by_item` block; a per-item copy of the stored tag for the slice.
- `project_log.md:18` — logs that the analysis wrote the slice.
- `methodology_capture.md:51` — the only DEFINITIONAL text (see below); a concept, not code.

There is **no function or script anywhere that reads a count and emits high/medium/low.**
The term-search for a mechanism (`well-established`, `long-tail`, `how widely`,
`prevalence`, `source_count`, `n_papers`, `cited_by`) returns no computing code; the
only prose match is `methodology_capture.md:51`:

> "Items are tagged by ecological compartment, answer type, and fact popularity
> (a well-established versus long-tail distinction), the last enabling a test of
> whether the retrieve-versus-memory balance shifts with how widely a fact is reported."

That states the CONCEPT (well-established vs long-tail / how widely reported). It does
NOT state an operational rule (no threshold, no counted input, no procedure).

---

## 3. Provenance of the tag

Every reference to `d3_eval_set.json` in the repo is a READER, never a writer:

- `core/build_contradictions.py:47` — reads it (`EVAL_SET = ... d3_eval_set.json`).
- `core/run_experiment.py:53` — reads it.
- `export_human_labels.py:48` — reads it.
- `nli_grounding_d3.py:47` — reads it.

No script writes `d3_eval_set.json`. The one eval-set BUILDER in the repo,
`setup/04_build_pilot_eval_set.py`, writes a DIFFERENT file (`pilot_eval_set.json`,
the 67-item pilot) and **never emits a `popularity` or `tags` field at all** (grep of
that file for `popularity`/`tags`: no match). The `citations` array present on each D3
item (author + year) is the same shape the pilot builder produced, but the `tags`
object (compartment / answer_type / popularity) is not something any builder in the
repo generates.

**Conclusion for this step: `popularity` is a manual constant, hand-written directly
in `d3_eval_set.json`. It is not computed from any recorded input, and no code
produces it.**

---

## 4. Available objective proxies (reported only, tags unchanged)

**(a) Primary paper citation count — IS recoverable.** `paper_metadata.json` (a list
of 1,716 records) carries `citation_count` per DOI, sourced from OpenAlex
`cited_by_count` (`setup/03_enrich_metadata.py:103`). Joining each item's
`matched_dois[0]` to that metadata:

| item | hand popularity | citation_count | first author | DOI |
|------|-----------------|----------------|--------------|-----|
| D3-01 | medium | 42  | Roach | 10.1093/icesjms/fsy006 |
| D3-02 | low    | 163 | Maar | 10.1016/j.seares.2009.01.008 |
| D3-03 | low    | 60  | Raoux | 10.1016/j.ecolind.2018.07.014 |
| D3-04 | high   | 91  | Van Hal | 10.1016/j.marenvres.2017.01.009 |
| D3-05 | low    | 33  | Werner | 10.1016/j.fishres.2024.106937 |
| D3-07 | low    | 23  | Barbut | 10.1093/icesjms/fsz050 |
| D3-08 | high   | 5   | Berges | 10.1098/rsos.240339 |
| D3-09 | medium | 33  | Buyse | 10.1093/icesjms/fsac107 |
| D3-10 | low    | 53  | Vandendriessche | 10.1007/s10750-014-1997-z |
| D3-11 | medium | 55  | Puts | 10.1016/j.marpol.2023.105574 |
| D3-12 | low    | 91  | Van Hal | 10.1016/j.marenvres.2017.01.009 |
| D3-16 | low    | 91  | Van Hal | 10.1016/j.marenvres.2017.01.009 |

**The hand tag does NOT track citation count.** Evidence:

- The **most-cited** paper in the set, D3-02 (Maar 2009, **163** cites), is tagged **low**.
- A **high** item, D3-08 (Berges 2024, **5** cites), has the **fewest** citations of all 12.
- **Decisive:** the same paper Van Hal 2017 (91 cites) is the source for **three**
  items with **two different** popularity tags — D3-04 = **high**, D3-12 = **low**,
  D3-16 = **low**. Identical input (same DOI, same citation count) mapped to different
  outputs, so popularity cannot be a function of the primary paper's citation count.

So citation_count exists as a proxy, but the hand tag was clearly not derived from it.
(Popularity plausibly refers to how widely the FINDING is reported across the
literature, which is a different quantity from the source paper's citation count. That
quantity is not recorded anywhere in the repo.)

**(b) Corpus-internal count of how many indexed papers mention the fact — NOT recorded.**
No file stores a per-fact count of corpus papers asserting each claim. Producing one
would require a real retrieval run over the index, which this audit did NOT perform, as
instructed.

---

## 5. Conversation / log trace

`project_log.md` has exactly one line about the eval set's creation
(`project_log.md:12`):

> "2026-07: H1 eval set built and verified; run pointed at d3_eval_set.json - DONE"

It records THAT the set was built and verified, not HOW popularity was assigned. No
line in `project_log.md` (or any session note found in the repo) describes a popularity
labelling step, a rule, or an input for it. The log does not explain the assignment.

The only prose about popularity anywhere is the conceptual sentence in
`methodology_capture.md:51` quoted in step 2, which gives the intent
(well-established vs long-tail) but no operational procedure.

---

## 6. Verdict

**(B) Popularity is a MANUAL hand-assigned label with NO recorded rule or input.**

Supporting evidence:

1. It exists only as a literal constant in `d3_eval_set.json` (step 1).
2. No code in the repo computes it; every `popularity` reference is a reader or a
   reporter, never a producer (step 2).
3. No script writes `d3_eval_set.json`; the only eval-set builder writes a different
   file and never emits `popularity`/`tags` (step 3).
4. The one objective proxy that IS available (source-paper citation_count) does not
   track the tag, and the same paper at the same citation count carries two different
   popularity tags, which rules out a citation-count rule (step 4).
5. Neither the project log nor any session note records an assignment procedure; the
   methodology file states only the concept, not a rule (steps 2 and 5).

The tag reflects the author's considered judgement of how widely each finding is
reported ("well-established vs long-tail"), applied by hand. That is a legitimate
method, but it is undocumented as a procedure and is not reproducible from any recorded
input. If a defensible, reproducible popularity axis is needed, it would have to be
defined and computed anew (for example a corpus-internal mention count), not recovered
from what currently exists.
