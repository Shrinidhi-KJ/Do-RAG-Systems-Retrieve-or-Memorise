# Inter-annotator agreement (H2a): KJ vs Aneesha, plus three-way summary

Computed 2026-07-18. Sheets: `KJ_full_labels_d3_20260718.csv` (primary rater, technical) and
`AneeshaGunaratne_full_labels_d3_20260717.csv` (second rater, non-technical). Both 120 rows.

The judge is **not** involved in this comparison. The metrics use the identical label definitions
from `score_judge_validation.py` (its `norm_label`, `parse_bool`, `cohen_kappa`, `pabak`,
`observed_agreement` functions were imported, not reimplemented), computed inline because the scorer
only supports human-vs-key joins, not human-vs-human.

## Coverage check

- KJ rows: 120. Aneesha rows: 120. Common row_uids: **120**.
- Rows in KJ but not Aneesha: **0**. Rows in Aneesha but not KJ: **0**.

Both sheets cover the same 120 row_uids. Comparison run on all 120.

## 3. KJ vs Aneesha (human-vs-human)

### Agreement

| metric | n | raw agreement | Cohen's kappa | PABAK |
|---|---|---|---|---|
| six-way label | 120 | 0.9583 | 0.9369 | 0.9444 |
| **correct vs not (binary)** | **120** | **0.975** | **0.9492** | **0.95** |
| grounding decision | 72 | 1.0 | undefined (see flag) | 1.0 |

### Class marginals

Six-way:
- KJ: correct 53, abstention 39, grounded_but_wrong 26, parametric_error 2
- Aneesha: correct 52, abstention 36, grounded_but_wrong 28, parametric_error 4

Binary: KJ correct 53 / not 67 · Aneesha correct 52 / not 68

Grounding (72 scored): KJ True 72 / False 0 · Aneesha True 72 / False 0

### Degenerate-marginal flag

- **Grounding decision: DEGENERATE.** Both humans made a positive grounding call (True) on every one
  of the 72 cells where both filled it in, so Cohen's kappa is undefined. **Read PABAK (1.0) and raw
  agreement (1.0), not kappa.** The two humans never disagreed on a grounding call. (Grounding here
  covers 72 cells, far more than the 24 the judge scored, because both raters filled human_grounded
  on all document conditions, whereas the judge recorded a grounding call on only 25.)
- Six-way and binary marginals are skewed but not degenerate; their kappas (0.94, 0.95) read directly.

### Six-way confusion matrix (rows = KJ, cols = Aneesha)

| KJ \ Aneesha | correct | abstention | grounded_but_wrong | parametric_error |
|---|---|---|---|---|
| correct | 51 | 0 | 2 | 0 |
| abstention | 1 | 36 | 0 | 2 |
| grounded_but_wrong | 0 | 0 | 26 | 0 |
| parametric_error | 0 | 0 | 0 | 2 |

### Disagreement list (5 of 120 six-way labels differ)

3 of the 5 cross the binary correct/not-correct boundary, in no consistent direction (KJ stricter on
1, Aneesha stricter on 2). All 5 sit in condition A/B2/C. KJ recorded no notes on these cells;
Aneesha's notes are shown where present.

**KJ = abstention / Aneesha = correct (n=1)** - crosses binary boundary
- `acf1ba29cb` | D3-08 | A. KJ note: (none). Aneesha note: (none).

**KJ = correct / Aneesha = grounded_but_wrong (n=2)** - crosses binary boundary
- `0e1561c293` | D3-16 | C. KJ note: (none). Aneesha note: model is partially correct about one crab species but incorrectly states it is the only one found and adds irrelevant info about lobster and cod.
- `cc02d91e3c` | D3-12 | B2. KJ note: (none). Aneesha note: model correctly identifies the two species but also includes incorrect additional species.

**KJ = abstention / Aneesha = parametric_error (n=2)** - within not-correct
- `be39fa8cb8` | D3-05 | A. KJ note: (none). Aneesha note: model says it couldn't find any specific studies then gives irrelevant information, one of which contradicts the claim.
- `e2d849426f` | D3-04 | A. KJ note: (none). Aneesha note: model attempts to answer the question in a general manner providing both negative and positive impacts which doesn't align with the straightforward answer provided in the claim.

## 4. Three-way summary: binary correct-vs-not

| pairing | n | raw agreement | Cohen's kappa |
|---|---|---|---|
| KJ vs judge | 120 | 0.9417 | 0.8829 |
| Aneesha vs judge | 120 | 0.95 | 0.8996 |
| **KJ vs Aneesha (human-vs-human)** | **120** | **0.975** | **0.9492** |

### Plain-language reading (from the numbers, no spin)

The primary (technical) rater does **not** agree with the judge more than the non-technical rater
did. On the binary correct-vs-not decision, Aneesha-vs-judge is 0.95 raw / 0.90 kappa, and
KJ-vs-judge is slightly lower at 0.9417 raw / 0.8829 kappa. KJ disagreed with the judge on 7 of 120
correctness calls, Aneesha on 6; the technical rater was, if anything, marginally further from the
judge, not closer. In both cases the disagreements at the correctness boundary run mostly one way:
the judge is more lenient (marks `correct` where the human marks abstention or grounded_but_wrong).

The two humans agree with each other more than either agrees with the judge: KJ-vs-Aneesha is 0.975
raw / 0.9492 kappa, above both human-vs-judge pairings. So the gap is between the humans as a group
and the automatic judge, not between the technical and non-technical rater. Rater technicality did
not measurably improve alignment with the judge here.
