# Methodology capture (write-up feeder)

Prose-in-waiting for the dissertation, organised by chapter theme. Each item: what was done, why, and the honest limitation, with a STATUS. Only DONE items are safe to lift verbatim; IN PROGRESS and PLANNED items are placeholders that must not be written in the past tense until they are real.

Last updated: 10 July 2026.

---

## Study design

STATUS: DONE (settled).

The study is a controlled, black-box diagnostic of whether a retrieval-augmented generation system answers domain questions by reading the retrieved documents or by relying on parametric memory. The question and the model are held fixed and only the documents are varied, so any change in behaviour is attributable to the context. Five conditions: A (no documents, parametric baseline), B1 (standard retrieval), B2 (oracle, retrieval restricted to the known-correct paper), C (topically irrelevant documents), and D (a fluent passage asserting the opposite of the true finding). Answers are labelled with a six-class condition-aware taxonomy (correct, abstention, retrieval_failure, ungrounded_hallucination, grounded_but_wrong, parametric_error). Memorisation is defined behaviourally, read off the cross-condition pattern, since the model is closed-weight and its training data undisclosed.

Interpretive guardrail: corpus-wide retrieval recall and the B2-versus-B1 comparison are separate facts, since B2 bypasses corpus retrieval by construction. The defensible claim is that B2 shows no detectable advantage over B1, not that it is equal or worse.

## Corpus construction

STATUS: DONE.

Candidate papers on the environmental effects of offshore wind farms were discovered through database searches (1,732 deduplicated DOIs), of which 514 open-access PDFs were obtained. The corpus was built for a specific descriptor, commercial fish and shellfish (MSFD Descriptor 3), with the wider set retained as domain context and distractors.

Documents were parsed with GROBID (image lfoppiano/grobid:0.8.0), which structurally separates a scientific PDF into body, references, and front and back matter. Only the title, abstract, and body sections were kept, together with figure and table captions (which frequently carry the quantitative findings under test); bibliographies, running headers, footers, page numbers, author affiliations, and funding, acknowledgement, conflict-of-interest, data-availability, supplementary, appendix, and ethics sections were dropped. This replaced an earlier lighter cleaner that left reference lists and boilerplate in the index. Text was chunked at 1000 characters with 200 overlap, respecting section boundaries so no chunk straddles two sections, and each chunk carries metadata (DOI, title, section label, caption flag, chunk index).

A corpus-quality triage before indexing found and excluded 15 unusable files (12 wrong-content PDFs such as repository wrapper pages and mis-bound articles, and 3 wrong-granularity files including a whole-volume PDF); 7 further PDFs that GROBID could not parse were logged and skipped; and one PDF whose digits were encoded as named glyphs was re-extracted with a fallback parser. The clean index (owf_clean_v1) holds 501 papers and 34,502 chunks, a reduction from the earlier noisy index consistent with the removal of reference lists and boilerplate.

LIMITATION to state: the original download covered about 30 per cent of discovered DOIs, and GROBID extraction used the lightweight model; both are documented, and the coverage gap was addressed by the source rescue below.

## Corpus coverage rescue

STATUS: DONE.

Verifying the evaluation set revealed that most of the primary papers underlying the ground-truth findings were absent from the initial corpus, including several that are open access and were simply never downloaded. Because the retrieval conditions and the oracle require the source paper to be present, the missing primaries were added through the identical clean pipeline. Sources were resolved to DOIs and checked for membership by exact DOI; open-access copies were retrieved where licensing allowed, and the remainder obtained through institutional access. This brought every evaluation-set source into the corpus.

Two data-integrity issues were found and handled in the process: author-name matching failed on diacritics (resolved by matching on DOI), and DOIs with more than one slash were stored in a mangled form (the second slash rendered as an underscore), which was accommodated by canonicalising DOIs on both sides of every comparison rather than mutating stored data.

LIMITATION to state: adding the ground-truth sources to the corpus is legitimate curation (they are genuine domain papers), but it means the corpus was completed to guarantee retrievability of the tested facts; this is disclosed rather than hidden.

## Retrieval configuration

STATUS: DONE.

Embeddings use BAAI/bge-small-en-v1.5 with normalisation. The query-instruction prefix that this model expects on queries is applied to queries only, with passages embedded plain; an earlier configuration omitted the prefix, which understated retrieval quality. Retrieval returns the top k = 5 chunks for the document conditions. Distances are L2 on normalised vectors, which is order-equivalent to cosine similarity (the write-up should describe it as such rather than as cosine). The oracle condition (B2) filters retrieval to the known-correct paper by DOI, canonicalised to match the stored form.

## Evaluation set construction

STATUS: DONE.

The evaluation set is a set of atomic factual items derived from the Descriptor 3 findings of a synthesis report, each with a question phrased so as not to disclose its answer, a single gold answer (the specific finding), the primary paper the finding comes from (confirmed present in the corpus, serving as the oracle), and a counterfactual for Condition D. This replaces an earlier pilot set whose auto-generated questions restated their own answers, which inflated accuracy in every condition.

Each item was verified by hand against the primary paper rather than the synthesis report, because the report was found in several cases to round figures or mis-attribute a claim. Of an initial 15 candidates, 4 were dropped where the cited paper did not support the claim (for example a paper reporting lost fishing opportunities rather than a conservation effect, and a bioeconomic model with no reef effect), several were revised to match the primary exactly (for example a mussel-biomass item sharpened to the reported 7-to-18-times figure, and a lobster item corrected from a reef claim to the closure effect the paper actually reports), and two were added, giving 12 verified items. Items are tagged by ecological compartment, answer type, and fact popularity (a well-established versus long-tail distinction), the last enabling a test of whether the retrieve-versus-memory balance shifts with how widely a fact is reported.

A schema trace confirmed that the subject model is shown the question only and never the gold, so the answer does not leak, that the correctness judge scores against the gold, and that Condition D negates the gold to build its counterfactual.

STATUS note: expert verification of a subset of the gold answers by an external domain group (BioAgora) is PLANNED, not yet done.

## Experimental pipeline

STATUS: DONE.

Each condition is generated once per subject model. Two subject models are used, an 8-billion and a 70-billion parameter model of the same family, so that model size can be examined (RQ3) with everything else held fixed. The correctness judge and the Condition D counterfactual builder are a separate, fixed model.

Reproducibility is provided by a content-addressed result cache: each cell is keyed by a hash of every input that determines its output (model, condition, item, exact prompt, ordered context, k, temperature, and the counterfactual), so a change to any input produces a fresh generation rather than silently reusing a stale answer. Determinism is reported honestly: decoding is greedy at temperature 0, but this is not bit-deterministic without a fixed seed and the inference provider does not guarantee bitwise reproducibility, so results are reported as reproducible in distribution rather than bit-identical. Runs are configured so that the inference provider can be changed without code edits, which protects the study against provider-side model retirement.

## Judging and validation

STATUS: PLANNED / IN PROGRESS. Do not write in the past tense yet.

The correctness and grounding labels are produced by a language-model judge. Because the judge shares a family with the subject model, its labels will be validated against a stratified human-labelled sample (Cohen's kappa and a confusion matrix) and cross-checked by an independent-family natural-language-inference model on the grounding decision. These validations are not yet run.

## Statistics

STATUS: PLANNED.

Per-condition correctness will be reported with Wilson 95 per cent intervals; the reliance comparisons (A versus B1, B1 versus B2) with a paired McNemar test; and the results split by fact popularity and by model size. The small sample and the multiplicity of comparisons will be stated plainly.

## Limitations (running list)

- Single-family judge: the judge shares a family with the subject; mitigated by human and NLI validation (planned), disclosed regardless.
- Condition D presents a single counterfactual document while the other document conditions present up to five; inherent to the design, disclosed as a controlled difference.
- Corpus coverage was completed to guarantee retrievability of the tested facts; disclosed.
- GROBID used the lightweight model; a heavier model could improve reference and caption segmentation.
- Reproducibility is distributional, not bit-identical (temperature-0 greedy without a guaranteed seed, provider not bitwise-deterministic).
- Small evaluation set (12 items); a vertical slice for the dissertation, to be expanded for publication.
- The model-size comparison pairs an 8B and a 70B model of different point releases rather than the same release, so it is a size-and-version comparison; noted.

## Deviations from the approved proposal

STATUS: DONE (to reconcile in the text).

Four conditions became five (B split into standard and oracle); the domain was concretised to offshore wind and Descriptor 3; questions are drawn from a synthesis report and verified against primaries; the taxonomy expanded from three to six labels; the evaluation set is a small verified slice rather than the larger pilot; and a second model was added for the size question. Judge validation and the statistical treatment are as above.
