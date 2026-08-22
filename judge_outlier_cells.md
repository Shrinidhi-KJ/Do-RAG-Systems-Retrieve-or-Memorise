# Judge-outlier cells (H2a): where the judge stands apart from the humans

Computed 2026-07-19, read-only, from the three already-scored sources: `KJ_full_labels_d3_20260718.csv`,
`AneeshaGunaratne_full_labels_d3_20260717.csv`, and the judge key `human_label_key_d3.json`. Labels
normalised with `score_judge_validation.py`'s `norm_label`. All 120 row_uids common to the three.
No re-runs; no writes elsewhere.

## (a) Both humans gave the same label, judge differs (n=6)

These are the cleanest judge-outlier cells: two independent raters (one technical, one non-technical)
landed on the same label and only the automatic judge dissents.

| row_uid | item | condition | humans (shared) | judge | direction |
|---|---|---|---|---|---|
| 5d7b7d4d9b | D3-08 | B1 | grounded_but_wrong | correct | judge lenient (crosses correct boundary) |
| aeaa32691f | D3-08 | B1 | grounded_but_wrong | correct | judge lenient (crosses correct boundary) |
| bfe7d86c5f | D3-01 | C | abstention | correct | judge lenient (crosses correct boundary) |
| 17646c8f4b | D3-12 | C | abstention | correct | judge lenient (crosses correct boundary) |
| e44720af36 | D3-02 | A | parametric_error | abstention | within not-correct (label flavour) |
| 889876ce9e | D3-12 | B1 | abstention | retrieval_failure | within not-correct (label flavour) |

**4 of these 6 cross the correct/not-correct boundary, all the same way: both humans say not-correct,
the judge says `correct`.** The judge is the lenient outlier on the correctness decision itself in
D3-08 (B1, x2), D3-01 (C), and D3-12 (C). The other 2 are label-flavour splits within "not correct"
and do not affect the binary correctness call.

## (b) All three differ (n=2)

Cells where KJ, Aneesha, and the judge each picked a different label.

| row_uid | item | condition | KJ | Aneesha | judge |
|---|---|---|---|---|---|
| e2d849426f | D3-04 | A | abstention | parametric_error | correct |
| 0e1561c293 | D3-16 | C | correct | grounded_but_wrong | abstention |

In `e2d849426f` the judge is again the lenient one (`correct` while both humans call it not-correct,
though the humans disagree on which not-correct label). In `0e1561c293` there is no shared human view
and no consistent direction: KJ says correct, Aneesha says grounded_but_wrong, judge says abstention.
