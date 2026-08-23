# Judge validation (H2a): primary human rater (KJ) vs 8b judge

Scored 2026-07-18. Rater sheet: `KJ_full_labels_d3_20260718.csv` (primary rater, technical;
120 rows, all human_label cells filled). Key: `human_label_key_d3.json`. Scorer:
`score_judge_validation.py`, run unchanged with
`--sheet KJ_full_labels_d3_20260718.csv --key human_label_key_d3.json`.

## Scope note

This compares **one human rater (KJ) against the automatic 8b judge**. It measures **judge
validity against a human**, not inter-annotator agreement. Human-vs-human agreement is reported
separately in `interannotator_kj_aneesha.md`.

## 1. Join integrity (checked before scoring)

- Sheet rows: 120. Key rows: 120.
- Sheet row_uids matching a key entry: **120 / 120**. Unmatched: **0**.
- Key row_uids not covered by the sheet: **0**. Duplicates: none. Blank human_label: none.

Scoring proceeded on the full 120.

## 2. KJ vs judge

### Headline agreement

| metric | n | raw agreement | Cohen's kappa | PABAK |
|---|---|---|---|---|
| six-way label | 120 | 0.925 | 0.8838 | 0.9062 |
| **correct vs not (binary)** | **120** | **0.9417** | **0.8829** | **0.8833** |
| grounding decision | 24 | 1.0 | undefined (see flag) | 1.0 |

Headline binary correct-vs-not: **raw agreement 0.9417, kappa 0.8829, PABAK 0.8833.**

### Class marginals

Six-way:
- KJ: correct 53, abstention 39, grounded_but_wrong 26, parametric_error 2
- judge: correct 58, abstention 36, grounded_but_wrong 24, parametric_error 1, retrieval_failure 1

Binary: KJ correct 53 / not 67 · judge correct 58 / not 62

Grounding (24 scored): KJ True 24 / False 0 · judge True 24 / False 0

### Degenerate-marginal flag

- **Grounding decision: DEGENERATE.** Only one class present (both KJ and judge marked True on all
  24 scored cells), so Cohen's kappa is undefined. **Read PABAK (1.0) and raw agreement (1.0), not
  kappa.** Agreement is perfect, not poor. 25 judge grounding-calls exist; 1 dropped because KJ left
  human_grounded blank on `889876ce9e` (D3-12, B1, the retrieval-failure/abstention cell), leaving 24.
- Six-way and binary marginals are skewed toward `correct`/`abstention` but not degenerate; their
  kappas (0.88, 0.88) read directly. Raw agreement and PABAK reported alongside regardless.

### Six-way confusion matrix (rows = KJ, cols = judge)

| KJ \ judge | correct | abstention | retrieval_failure | grounded_but_wrong | parametric_error |
|---|---|---|---|---|---|
| correct | 52 | 1 | 0 | 0 | 0 |
| abstention | 4 | 34 | 1 | 0 | 0 |
| retrieval_failure | 0 | 0 | 0 | 0 | 0 |
| grounded_but_wrong | 2 | 0 | 0 | 24 | 0 |
| parametric_error | 0 | 1 | 0 | 0 | 1 |

### Per-condition raw agreement (six-way)

| condition | n | raw agreement |
|---|---|---|
| A | 24 | 0.875 |
| B1 | 24 | 0.875 |
| B2 | 24 | 1.0 |
| C | 24 | 0.875 |
| D | 24 | 1.0 |

## Disagreement list (9 of 120 six-way labels differ)

Of the 9, **7 cross the binary correct/not-correct boundary: 6 run judge=correct / KJ=not-correct
(judge more lenient) and 1 runs judge=not-correct / KJ=correct.** Net, the judge is more lenient at
the correctness boundary. KJ (technical rater) recorded no notes on the disagreeing cells.

**judge = correct / KJ = abstention (n=4)** - judge lenient, crosses binary boundary
- `acf1ba29cb` | D3-08 | A
- `bfe7d86c5f` | D3-01 | C
- `e2d849426f` | D3-04 | A
- `17646c8f4b` | D3-12 | C

**judge = correct / KJ = grounded_but_wrong (n=2)** - judge lenient, crosses binary boundary
- `5d7b7d4d9b` | D3-08 | B1
- `aeaa32691f` | D3-08 | B1

**judge = abstention / KJ = correct (n=1)** - KJ lenient, crosses binary boundary
- `0e1561c293` | D3-16 | C

**judge = abstention / KJ = parametric_error (n=1)** - within not-correct
- `e44720af36` | D3-02 | A

**judge = retrieval_failure / KJ = abstention (n=1)** - within not-correct
- `889876ce9e` | D3-12 | B1 (also the blank-grounding cell)
