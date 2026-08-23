# Judge validation (H2a): second human rater (Aneesha Gunaratne) vs 8b judge

Scored 2026-07-18. Rater sheet: `AneeshaGunaratne_full_labels_d3_20260717.csv` (120 rows,
all human_label cells filled). Key: `human_label_key_d3.json`. Scorer:
`score_judge_validation.py`, run unchanged with
`--sheet AneeshaGunaratne_full_labels_d3_20260717.csv --key human_label_key_d3.json`.

## Scope note (read first)

This compares **one human rater (Aneesha) against the automatic 8b judge**. It measures
**judge validity against a human**, not inter-annotator (human-vs-human) agreement. Human-vs-human
agreement would need a second independent human label set (the researcher's own), which is not yet
done. Do not cite the numbers below as inter-annotator agreement.

## 1. Locate

- Scorer: `score_judge_validation.py`
  (a second copy exists at `handoff_bioagora\score_judge_validation.py`; the repo-root copy was used).
- Key: `human_label_key_d3.json`
  (row_uid -> {cell_key, model_tag, judge_label, judge_grounded}).
- Neither file was modified. The scorer writes `judge_validation_d3.md` / `judge_validation_d3.json`;
  this report (`judge_validation_aneesha.md`) reproduces those numbers plus the marginals, the
  degenerate-marginal flag, and the disagreement list, which the scorer does not emit.

## 2. Join integrity (checked before scoring)

- Sheet rows: 120. Key rows: 120.
- Sheet row_uids matching a key entry: **120 / 120**.
- Sheet row_uids not matching: **0**.
- Key row_uids not covered by the sheet: **0** (every key row is present).
- Duplicate row_uids in the sheet: none. Blank human_label cells: none.

The blind app and the key did not drift. Scoring proceeded on the full 120.

## 3. Scored set

120 / 120 rows scored, 0 skipped.

## 4. Human (Aneesha) vs judge

### Headline agreement

| metric | n | raw agreement | Cohen's kappa | PABAK |
|---|---|---|---|---|
| six-way label | 120 | 0.9167 | 0.8725 | 0.8958 |
| **correct vs not (binary)** | **120** | **0.95** | **0.8996** | **0.90** |
| grounding decision | 24 | 1.0 | undefined (see flag) | 1.0 |

Binary correct-vs-not is the headline: **raw agreement 0.95, kappa 0.90, PABAK 0.90.**

### Class marginals (for each kappa)

Six-way:
- human: correct 52, abstention 36, grounded_but_wrong 28, parametric_error 4
- judge: correct 58, abstention 36, grounded_but_wrong 24, parametric_error 1, retrieval_failure 1

Binary (correct vs not_correct):
- human: correct 52, not_correct 68
- judge: correct 58, not_correct 62

Grounding decision (over the 24 cells scored):
- human: True 24, False 0
- judge: True 24, False 0

### Degenerate-marginal flag

- **Grounding decision: DEGENERATE.** Only one class is present. Both the human and the judge
  recorded a positive grounding call (True) on all 24 scored cells, so Cohen's kappa is undefined
  (expected agreement = 1, division by zero). **Read PABAK (1.0) and raw agreement (1.0), not
  kappa, for this row.** Agreement here is perfect, not poor. Grounding is scored only where the
  judge recorded a grounding call: 25 such cells exist; 1 was dropped because the human left
  human_grounded blank (row `889876ce9e`, D3-12, B1), leaving 24 scored.
- Six-way and binary marginals are skewed toward `correct` but are not degenerate (multiple classes
  populated); their kappas (0.87, 0.90) are healthy and can be read directly. As the scorer notes,
  raw agreement and PABAK are reported alongside kappa regardless, not kappa alone.

### Six-way confusion matrix (rows = human, cols = judge)

| human \ judge | correct | abstention | retrieval_failure | grounded_but_wrong | parametric_error |
|---|---|---|---|---|---|
| correct | 52 | 0 | 0 | 0 | 0 |
| abstention | 2 | 33 | 1 | 0 | 0 |
| retrieval_failure | 0 | 0 | 0 | 0 | 0 |
| grounded_but_wrong | 3 | 1 | 0 | 24 | 0 |
| parametric_error | 1 | 2 | 0 | 0 | 1 |

### Per-condition raw agreement (six-way)

| condition | n | raw agreement |
|---|---|---|
| A | 24 | 0.875 |
| B1 | 24 | 0.875 |
| B2 | 24 | 0.9583 |
| C | 24 | 0.875 |
| D | 24 | 1.0 |

## 5. Disagreement list (every cell where Aneesha's label differs from the judge's)

10 of 120 six-way labels differ. Grouped by kind of disagreement. Of these 10, **6 cross the
binary correct/not-correct boundary, and all 6 run the same way: judge = correct, human = not
correct.** The judge is systematically more lenient than Aneesha at the correctness boundary; the
remaining 4 disagreements are label-flavour differences within "not correct" and do not affect the
headline binary number.

**judge = correct / human = grounded_but_wrong (n=3)** - judge lenient, crosses binary boundary
- `5d7b7d4d9b` | D3-08 | B1 - note: model does not abstain and provides a response based on the context even though it lacks the findings the claim provides
- `aeaa32691f` | D3-08 | B1 - note: model is partially correct but omits certain info the claim provides
- `cc02d91e3c` | D3-12 | B2 - note: model correctly identifies the two species but also includes incorrect additional species

**judge = correct / human = abstention (n=2)** - judge lenient, crosses binary boundary
- `bfe7d86c5f` | D3-01 | C - (no note)
- `17646c8f4b` | D3-12 | C - (no note)

**judge = correct / human = parametric_error (n=1)** - judge lenient, crosses binary boundary
- `e2d849426f` | D3-04 | A - note: model attempts to answer the question in a general manner providing both negative and positive impacts which doesn't align with the straightforward answer provided in the claim

**judge = abstention / human = parametric_error (n=2)** - within not-correct
- `be39fa8cb8` | D3-05 | A - note: model says it couldn't find any specific studies then gives irrelevant information, one of which contradicts the claim
- `e44720af36` | D3-02 | A - (no note)

**judge = abstention / human = grounded_but_wrong (n=1)** - within not-correct
- `0e1561c293` | D3-16 | C - note: model is partially correct about one crab species but incorrectly states it is the only one found and adds irrelevant info about lobster and cod

**judge = retrieval_failure / human = abstention (n=1)** - within not-correct
- `889876ce9e` | D3-12 | B1 - (no note). This is also the cell where human_grounded was left blank.

Grounding-decision disagreements: 0 (all 24 scored cells agree).

Aneesha left 14 of 120 rows with a note; the notes above cover the systematic pattern - where she
downgrades a judge "correct" it is for partial answers that omit or contradict claim detail, or that
add incorrect extra species/information.
