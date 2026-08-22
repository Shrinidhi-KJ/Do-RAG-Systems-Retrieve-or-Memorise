# D3-03 provenance: which Raoux paper the eval set actually uses, and whether that choice was ever recorded

Read-only investigation, 2026-07-21. No experiment, judge or NLI was re-run; nothing was
edited except this file and one appended line in `project_log.md`. All paths are relative to
`data_pipeline/`.

---

## 1. D3-03 full record (verbatim from `d3_eval_set.json`, lines 24-34)

```json
{
  "id": "D3-03",
  "question": "In the ecosystem model's reef scenario after offshore wind farm construction, how did the modelled activity of top predators such as Atlantic cod change?",
  "claim_text": "In the ecosystem model's reef scenario after offshore wind farm construction, the modelled activity of top predators such as Atlantic cod increased.",
  "matched_dois": ["10.1016/j.ecolind.2018.07.014"],
  "citations": [{"first_author": "Raoux", "year": 2018}],
  "gold_answer": "It increased; top predators including Atlantic cod, whiting, pouting, sea bream and flatfish showed increased activity under the reef scenario.",
  "acceptable_answer": "An increase in top-predator or cod activity.",
  "counterfactual": "In the reef scenario, the modelled activity of top predators such as Atlantic cod decreased after offshore wind farm construction.",
  "tags": {"compartment": "fish", "answer_type": "directional", "popularity": "low"}
}
```

Per-field source lines: `d3_eval_set.json:25` (id), `:26` (question), `:27` (claim_text),
`:28` (matched_dois — the only DOI field the item has), `:29` (citations — author/year only,
no DOI), `:30` (gold_answer), `:31` (acceptable_answer), `:32` (counterfactual, i.e. the
Condition D claim), `:33` (tags).

The item stores **one** source DOI, `10.1016/j.ecolind.2018.07.014`, and separately an
author/year citation string `Raoux 2018`. There is no second DOI field, no
"oracle_paper" override, and no free-text note on the item.

---

## 2. Raoux papers and the four queried DOIs

**Canonicaliser used** — `core/conditions.py:93-108`, `canonicalise_doi(doi)`:

```python
def canonicalise_doi(doi):
    if not doi:
        return doi
    head, sep, tail = doi.partition("/")
    if not sep:
        return doi
    return head + "/" + tail.replace("/", "_")
```

Docstring, `core/conditions.py:97-100`: "the clean index stored multi-slash DOIs mangled:
every slash AFTER the first became an underscore … single-slash DOIs are stored unchanged."
**All four DOIs in question are single-slash `10.1016/…` DOIs, so canonical form == true
form for every one of them** — the mangling rule is inert here and cannot explain any
mismatch.

| True DOI | Canonicalised (`canonicalise_doi`) | Title as stored | In clean index `owf_clean_v1`? | Evidence |
|---|---|---|---|---|
| `10.1016/j.ecolind.2018.07.014` | identical | "Measuring sensitivity of two Ospar indicators for a coastal food web model under Offshore Wind Farm construction" | **YES**, 67 chunks, `status=included` | `corpus_dois.csv:100`; `owf_clean_v1_papers.csv:115` |
| `10.1016/j.ecolind.2016.07.037` | identical | "Benthic and fish aggregation inside an offshore wind farm: Which effects on the trophic web functioning?" | **YES**, 90 chunks, `status=included` | `corpus_dois.csv:99`; `owf_clean_v1_papers.csv:114` |
| `10.1016/j.marpol.2017.12.007` | identical | "Assessing cumulative socio-ecological impacts of offshore wind farm development in the Bay of Seine (English Channel)" | **NO** — absent from both files entirely | `paper_metadata.json:30711` (metadata only); no row in `corpus_dois.csv` or `owf_clean_v1_papers.csv` |
| `10.1016/j.jmarsys.2020.103434` | identical | "A spatial food web model to investigate potential spillover effects of a fishery closure in an offshore wind farm" | **YES**, 64 chunks, `status=included` | `corpus_dois.csv:132`; `owf_clean_v1_papers.csv:147` |

**Every paper in the corpus whose first author is Raoux** (first author read from
`paper_metadata.json`; `10.1016/j.jmarsys.2020.103434` is listed here only because it was
queried — its first author is Halouani, not Raoux):

| DOI | Year (stored) | First author (stored) | Title | In clean index? |
|---|---|---|---|---|
| `10.1016/j.ecolind.2016.07.037` | 2016 | Aurore Raoux | Benthic and fish aggregation inside an offshore wind farm… | YES (90 chunks) |
| `10.1016/j.ecolind.2018.07.014` | 2018 | Aurore Raoux | Measuring sensitivity of two OSPAR indicators… | YES (67 chunks) |
| `10.1016/j.ecolind.2020.106381` | 2020 | Aurore Raoux | Evaluating ecosystem functioning of a long-term dumping site in the Bay of Seine | YES (75 chunks) — `corpus_dois.csv:101`, `owf_clean_v1_papers.csv:116` |
| `10.1016/j.ecss.2020.106690` | 2020 | Aurore Raoux | Isotopic analyses, a good tool to validate models… | YES (49 chunks) — `corpus_dois.csv:108`, `owf_clean_v1_papers.csv:123` |
| `10.1016/j.marpol.2017.12.007` | **2017** | Aurore Raoux | Assessing cumulative socio-ecological impacts… | **NO** |

Metadata line refs: `paper_metadata.json:17766` (ecolind.2016), `:17838` (ecolind.2018),
`:17908` (ecolind.2020), `:18867` (ecss.2020), `:28010` (jmarsys.2020), `:30711` (marpol.2017).

Note the year field: the DOI Eklipse's reference list attaches to "Raoux et al. (2018)",
`marpol.2017.12.007`, is stored in this repo's metadata with **year 2017**, not 2018. That
matters for §4.

`d3_reachability_inputs.md:124` independently records marpol as "genuinely absent" from the
corpus. It is nevertheless present in the upstream DOI discovery lists (`dois.txt`,
`dois_merged_final.txt`, `dois_raw_wos.txt`, `debug_openalex_rescreen.tsv:284` = `kept`) and
in the *frozen* `chroma_db/chroma.sqlite3` string blob — i.e. it was discovered and screened
in, but its full text never made it into the clean index.

---

## 3. What Condition B2 actually used for D3-03

**Resolution path (code):**

- `core/run_experiment.py:159` — `gt_dois = item.get("matched_dois", [])`
- `core/run_experiment.py:168` — `public, gen_context = prepare_B2(question, gt_dois, k=k)`
- `core/conditions.py:288-291` — B2 canonicalises and builds a hard metadata filter:
  ```python
  if isinstance(gt_dois, str): gt_dois = [gt_dois]
  gt_dois = [canonicalise_doi(d) for d in gt_dois]
  flt = {"doi": gt_dois[0]} if len(gt_dois) == 1 else {"doi": {"$in": gt_dois}}
  ```
- `core/conditions.py:293` — `store.similarity_search_with_score(question, k=k, filter=flt)`

So B2's oracle is exactly `matched_dois`, with no other input. For D3-03 that is the single
DOI `10.1016/j.ecolind.2018.07.014` (`d3_eval_set.json:28`), unchanged by canonicalisation.

**Confirmed against the recorded run** (`results_d3.jsonl`, D3-03 / condition B2, both model
tags `8b` and `70b` — identical retrieval, as expected since B2 retrieval precedes generation):
`oracle_available = True`, and all five retrieved chunks carry
`doi = 10.1016/j.ecolind.2018.07.014` (chunk_index 0, 27, 14, 3, 9; scores 0.3887, 0.4390,
0.4491, 0.4590, 0.4842).

**Conclusion for step 3:** the pipeline is internally consistent. Eval set, B2 oracle,
Condition C exclusion (`core/conditions.py:251`, same `matched_dois`), retrieval-recall audit
(`retrieval_recall_d3.md:66`, `:129` — gold `ecolind.2018.07.014`, first hit rank 8) and the
popularity audit (`popularity_audit.md:94` — `D3-03 | low | 60 | Raoux |
10.1016/j.ecolind.2018.07.014`) all use `ecolind.2018.07.014` and nothing else. No component
ever saw `marpol.2017.12.007`.

---

## 4. Recorded justification: what exists, and what does not

### 4a. What exists — the H1 verification workbook

`H1_gold_verification_workbook.md:51-79` is the only place in the repo where D3-03's source
paper is assigned by a human. Quoted verbatim:

```
### D3-03  (shellfish, lobster; popularity low)
- Question: How does restricting fishing within offshore wind farms affect predator species such as European lobster in the area?
- Draft gold: It increases them; predators such as cod and lobster increase around OWFs where fishing is restricted.
- Source: Raoux et al. 2018, 10.1016/j.ecolind.2018.07.014
- Draft counterfactual: It decreases predator species such as lobster around OWFs.
```

with, at `:56-76`, a long VERIFIED GOLD block transcribed out of the source PDF (page/line
numbers 164-171 and 258-269 preserved), including:

> "The BOWF model compared to the REEF scenario showed: 1) an increase in top predators
> activity (except for diving seabirds), elasmobranchs, Atlantic cod, whiting, pouting,
> European sprat, sea bream, flatfish, benthic invertebrate predators, filter feeders and
> bivalves"

and, at `:77-79`:

```
- WHERE IN PAPER: 2 different paras, first in line 166 and then in 262
- ACCEPTABLE ANSWER:  questiable
- QUESTION OK? / COUNTERFACTUAL OK? / VERDICT: the paper only has mention of cod and lobster is never mentioned but there are other sea creatures mentioned
```

Two things follow from this, without inference beyond the text:

1. **The question was rewritten.** The workbook's D3-03 question is about *restricting
   fishing* and *European lobster*; the shipped `d3_eval_set.json` D3-03 question is about
   the *reef scenario* and *top predators such as Atlantic cod*. The shipped gold answer
   ("top predators including Atlantic cod, whiting, pouting, sea bream and flatfish showed
   increased activity under the reef scenario") is a paraphrase of the REEF-scenario sentence
   quoted at `H1_gold_verification_workbook.md:67-70`. The recorded reason for the rewrite is
   the verdict line: lobster is never mentioned in the paper.
2. **The source DOI was never revisited during that rewrite.** The workbook line "Source:
   Raoux et al. 2018, 10.1016/j.ecolind.2018.07.014" is stated, not argued; there is no note
   comparing it to `marpol.2017.12.007` or to any other Raoux paper, and no note that a swap
   was considered.

The same DOI is assigned again at `H1_gold_verification_workbook.md:128` for workbook item
**D3-06** ("In the ecosystem model, how were OWF structures predicted to affect benthos
biomass…"), whose VERIFIED GOLD (`:130-141`) is the *same* REEF-scenario paragraph. D3-06 does
not appear in `d3_eval_set.json` (ids run …D3-05, D3-07…).

### 4b. Where the DOI originally came from — automated author/year matching

The `Raoux 2018 → ecolind.2018.07.014` pairing originates in the pilot builder, not in a human
decision. `pilot_eval_set.json:458-467` holds the Eklipse sentence that became workbook D3-03:

```json
"claim_text": "The restriction of areas for fishing may increase predator species (e.g., cod, lobster) around OWFs, altering prey populations (Raoux et al., 2018), and changing fish communities on a small scale.",
"citations": [{"first_author": "Raoux", "year": 2018}],
"matched_dois": ["10.1016/j.ecolind.2018.07.014"]
```

(three further Eklipse claims citing "Raoux et al., 2018" get the same DOI:
`pilot_eval_set.json:420`, `:432`, `:469`.)

The matcher is `setup/04_build_pilot_eval_set.py`:

- `:269-296` `match_citation_to_dois()` — looks up `(surname, year)`, falling back to year ±1,
  then to the last word of the surname.
- `:213-255` `build_author_year_index()` — keys the corpus by `(first_author_surname, year)`
  from stored metadata.
- `:419-424` — before indexing, the corpus is **filtered to papers whose PDF was actually
  downloaded**: `corpus = [p for p in corpus if p.get("doi", "").lower() in downloaded_dois]`.

Mechanically, then: `("raoux", 2018)` matched `ecolind.2018.07.014` (stored year **2018**) as an
exact hit, while `marpol.2017.12.007` (stored year **2017**) was excluded from the index
altogether at `:423` because no PDF for it exists. No tie-break was needed and none was logged
— the builder writes only `claim_text`, `question`, `citations`, `matched_dois`
(`:457-462`); it has no field for a rationale.

### 4c. What does not exist — stated plainly

Searched: `project_log.md` (all 27 lines), `owf_clean_v1_MANIFEST.md`, `docs/*.md`
(ARCHITECTURE, CUE_CARD, PROJECT, WALKTHROUGH), `taxonomy_rubric.md`, `TRIAGE_REPORT.md`,
`README.md`, `popularity_audit.md`, `retrieval_recall_d3.md`, `analysis_d3.md`, and all
`setup/` and `core/` scripts, for `D3-03`, `Raoux`, and `ecolind.2018.07.014`.

**No file anywhere in the repo explains or defends the choice of
`10.1016/j.ecolind.2018.07.014` as D3-03's source paper.** Specifically:

- `project_log.md` contains **zero** hits for "Raoux", "ecolind", or "gold verification"
  detail. The only relevant line is `project_log.md:12`, "H1 eval set built and verified; run
  pointed at d3_eval_set.json - DONE" — a one-line status with no per-item content. The two
  D3-03 mentions in the log (`:16`) concern regenerating its Condition D contradiction, not
  its source.
- `owf_clean_v1_MANIFEST.md` has **no Raoux entry at all** — contrast
  `owf_clean_v1_MANIFEST.md:76`, which for D3-02 explicitly records the analogous decision:
  "`10.1016/j.seares.2009.01.008` (Maar et al. 2009, blue mussels around turbine foundations)
  - included, 96 chunks. Feeds D3-02 (replaces the mis-cited Kotta)." **The Kotta→Maar swap
  is documented; nothing equivalent exists for D3-03.**
- No script writes `d3_eval_set.json` — consistent with `project_log.md:22`, "popularity is a
  manual hand-assigned label with no recorded rule or input (no computing code, no builder
  writes d3_eval_set.json…)". The file is hand-maintained, so the DOI carried forward from
  the pilot builder by hand.

**Bottom line for §4:** the assignment is *traceable* (pilot author/year match → H1 workbook →
eval set) but it is **not justified anywhere**. The only human note attached to D3-03 flags a
different problem (lobster absent from the paper) and led to the question being rewritten; it
says nothing about which Raoux paper is correct. There is no record that
`marpol.2017.12.007` was ever considered and rejected for D3-03.

---

## 5. Content of `10.1016/j.ecolind.2018.07.014`, for your own reading

Title as stored: **"Measuring sensitivity of two Ospar indicators for a coastal food web model
under Offshore Wind Farm construction"** (`corpus_dois.csv:100`), Aurore Raoux, 2018
(`paper_metadata.json:17838`), 67 chunks indexed (`owf_clean_v1_papers.csv:115`).

Below are the five chunks B2 actually put in front of the model for D3-03, verbatim from the
recorded run (`results_d3.jsonl`, D3-03/B2 `context_docs`), in retrieved order. No judgement
of sufficiency is offered here — that is yours to make.

**chunk_index 0 (score 0.3887)**
> A combination of modelling tools was applied to simulate the impacts of the future
> Courseulles-sur-mer offshore wind farm construction (OWF) (Bay of Seine, English Channel) on
> the ecosystem structure and functioning. To do so, food-web models of the ecosystem under
> three scenarios were constructed to investigate the effect of added substrate (reef effect),
> fishing restriction (reserve effect), and their combined effect caused by the OWF. Further,
> Ecological Network Analysis indices and Mean Trophic Level (MTL) were derived to investigate
> their suitability for detecting changes in the ecosystem state. Our analyses suggest changes
> in the ecosystem structure and functioning after the OWF construction, the ecosystem maturity
> was predicted to increase, but no alterations in its overall resilience capacity.

**chunk_index 27 (score 0.4390)** — the chunk carrying the gold claim
> . The REEF and COMBINED scenarios exhibited also a higher biomass of benthic invertebrates
> compared to the BOWF model and the OPTIM scenario. A comparison between the compartmental
> throughflows (the amount of energy going through a compartment in terms of carbon) between the
> BOWF model and the three simulated scenarios were done to understand how the system changed
> after the OWF construction. The BOWF model compared to the REEF scenario showed: 1) an
> increase in top predators activity (except for diving seabirds), elasmobranchs, Atlantic cod,
> whiting, pouting, European sprat, sea bream, flatfish, benthic invertebrate predators, filter
> feeders and bivalves; 2) a decrease in benthic invertebrate deposit feeders, suprabenthos and
> King Scallop (Fig. 2). The comparison between the BOWF model and the COMBINED scenario
> differed from the previous comparison for the following compartments: mackerel, sea bass and
> King Scallop which showed an increase in their activity (Fig. 2)

**chunk_index 14 (score 0.4491)**
> . In this study we analysed three different scenarios using EwE. For the first scenario, we
> used the work by Raoux et al. (2017), who ran the Ecosim module to analyse the potential
> impacts on the ecosystem of benthic and fish aggregations inside the OWF ecosystem (REEF
> scenario). In the REEF scenario, expected biomasses were calculated for species that would
> presumably profit from the "reef effect" (Koller et al., 2006; Reubens et al., 2011; Krone et
> al., 2013; Reubens et al., 2013) by multiplying the average biomass per m² found in the
> literature for the respective species by the surface area represented by the turbine
> foundations and scour protections, and divided by the total OWF area. A temporal simulation
> was then run over 30 years while forcing the biomasses to increase for the targeted species
> compartments, and while keeping the original biomass values for the other functional groups

**chunk_index 3 (score 0.4590)**
> . Previous studies made in the Baltic and North seas showed that filter feeders such as
> mussels and amphipods tended to dominate on the turbine vertical structures, while benthic
> predators such as crabs dominate on the foundation base and the score protections (Wilhelmsson
> et al., 2006; Krone et al., 2017). This aggregation of epibenthic and benthic organisms on the
> turbine foundations is known as the "reef effect" and is considered as one of the most
> important effects on the ecosystem generated by OWF construction (Petersen and Malm, 2006;
> Langhamer, 2012). Besides the "reef effect", spatial restrictions in form of fisheries
> exclusion zones (e.g. bottom trawl and dredge) are likely to be implemented around turbines and
> cables for navigation safety…

**chunk_index 9 (score 0.4842)**
> . Following the modelling procedure in Raoux et al. (2017), the present study is intended to
> further deepen our understanding of the OWF construction effect on the ecosystem by: the
> increase in number of plausible scenarios: simulations of both the "reef effect" and the
> "reserve effect" on the ecosystem will be performed, as well as their combined effect; the
> comparison of ENA indices to "traditional" indicators such as MTL; the quantification of the
> uncertainty in the ENA indices…

The same REEF-scenario sentence was independently transcribed by hand from the PDF into
`H1_gold_verification_workbook.md:67-70` and `:132-135`, i.e. the indexed chunk text and the
human transcription of the paper agree.

---

## Summary of findings

| Question | Answer |
|---|---|
| What DOI does D3-03 store? | `10.1016/j.ecolind.2018.07.014` only (`d3_eval_set.json:28`) |
| Did the whole pipeline use it consistently? | Yes — eval set, B2 oracle, Condition C exclusion, recall audit, popularity audit. `marpol.2017.12.007` never entered any stage |
| Is `marpol.2017.12.007` in the corpus? | No — discovered and screened in, but no PDF and no index entry |
| How did the DOI get attached? | Automated `(surname, year)` match in `setup/04_build_pilot_eval_set.py`; `marpol` was ineligible (stored year 2017, and filtered out for having no PDF) |
| Was the choice ever explained? | **No.** Only `H1_gold_verification_workbook.md:51-79` records it, as a bare "Source:" line; its verdict note concerns lobster being absent, not which Raoux paper is right. Nothing in `project_log.md`, the manifest, or `docs/` — in explicit contrast to the documented Kotta→Maar swap for D3-02 (`owf_clean_v1_MANIFEST.md:76`) |
| Does the stored paper contain the gold claim text? | The REEF-scenario sentence naming increased top-predator and Atlantic cod activity is present in the indexed chunk 27 and in the hand transcription. Whether that suffices for the claim as posed is left for you to judge |
