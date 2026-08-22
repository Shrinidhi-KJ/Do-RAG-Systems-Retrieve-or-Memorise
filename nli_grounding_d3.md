# H2b: independent-family NLI grounding cross-check

NLI model: `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli` revision `b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7` (labels {0: 'entailment', 1: 'neutral', 2: 'contradiction'}), CPU, eval mode, softmax over logits, no sampling.

> NLI entailment and the judge's 'grounded' are related but NOT identical definitions. This is convergent evidence that answers are context-driven, not a strict equivalence test.

Premise = context_docs actually shown (not re-retrieved); Condition A excluded. Hypothesis = model answer (full) plus main claim sentence (longest) if multi-sentence. Aggregation: max entailment across shown chunks and across full/main-sentence; max contradiction recorded. Primary grounding cut = entail >= 0.5.

## 1. NLI vs judge grounding (over the judge's grounding-decision cells)

Over the **25** cells where the judge recorded a grounding decision:
- **observed agreement: 0.8** (reported first)
- Cohen's kappa: 0.2331  |  PABAK: 0.6
- judge_grounded marginal: {'True': 24, 'False': 1}; nli_grounded marginal: {'False': 6, 'True': 19}
- Marginals are near-degenerate (24 of 25 cells share one judge class), so kappa is expected to be uninformative; the convergent signal is the OBSERVED AGREEMENT rate, not kappa.

## 2. Condition D double-check (independent of the same-family judge)

Rate entailed by the false (counterfactual) document: **0.7917** (24 cells). Rate contradicting the gold claim: **1.0**.

| item | model | entail(counterfactual->answer) | entailed>=0.5 | contra(answer,gold) | contradicts_gold>=0.5 |
|---|---|---|---|---|---|
| D3-01 | 70b | 0.9497 | True | 0.9995 | True |
| D3-01 | 8b | 0.3601 | False | 0.9995 | True |
| D3-02 | 70b | 0.002 | False | 0.9995 | True |
| D3-02 | 8b | 0.999 | True | 0.9912 | True |
| D3-03 | 70b | 0.999 | True | 0.998 | True |
| D3-03 | 8b | 0.2249 | False | 0.9751 | True |
| D3-04 | 70b | 0.9995 | True | 1.0 | True |
| D3-04 | 8b | 0.9995 | True | 1.0 | True |
| D3-05 | 70b | 0.9985 | True | 0.9985 | True |
| D3-05 | 8b | 0.9985 | True | 0.998 | True |
| D3-07 | 70b | 0.9995 | True | 0.999 | True |
| D3-07 | 8b | 0.9995 | True | 0.999 | True |
| D3-08 | 70b | 0.999 | True | 1.0 | True |
| D3-08 | 8b | 0.999 | True | 1.0 | True |
| D3-09 | 70b | 0.999 | True | 0.9985 | True |
| D3-09 | 8b | 0.0008 | False | 0.9971 | True |
| D3-10 | 70b | 0.999 | True | 0.998 | True |
| D3-10 | 8b | 0.999 | True | 0.998 | True |
| D3-11 | 70b | 0.9995 | True | 0.9995 | True |
| D3-11 | 8b | 0.9995 | True | 0.9995 | True |
| D3-12 | 70b | 0.9995 | True | 1.0 | True |
| D3-12 | 8b | 0.9995 | True | 1.0 | True |
| D3-16 | 70b | 0.2422 | False | 0.9995 | True |
| D3-16 | 8b | 0.999 | True | 1.0 | True |

## 3. Independent grounding rate per condition (non-abstained context cells)

| condition | subset | n | nli_grounded rate (entail>=0.5) |
|---|---|---|---|
| B1 | B1 (non-abstained) | 23 | 0.5652 |
| B2 | B2 (non-abstained) | 24 | 0.75 |
| C | C-correct | 4 | 0.25 |
| D | D (non-abstained) | 24 | 0.7917 |

## 4. Threshold sensitivity (grounding rate over the broader non-abstained set)

n = 75 cells (B1 non-abstained + B2 non-abstained + C-correct + D).

| threshold | overall | B1 | B2 | C | D |
|---|---|---|---|---|---|
| 0.5 | 0.68 | 0.5652 | 0.75 | 0.25 | 0.7917 |
| 0.7 | 0.64 | 0.5217 | 0.6667 | 0.25 | 0.7917 |
| 0.9 | 0.5867 | 0.4783 | 0.5833 | 0.0 | 0.7917 |

## 5. Three-way NLI vs judge vs human grounding

Skipped: human_grounded column not filled in human_label_sheet_d3.csv.

## Note on definitions

NLI entailment and the judge's 'grounded' are related but NOT identical definitions. This is convergent evidence that answers are context-driven, not a strict equivalence test.
