# Judge validation (H2a): human vs 8b judge

Scored 120 of 120 sheet rows (0 rows had no human_label and were skipped). Read-only join on row_uid.

> Label marginals are heavily skewed (mostly correct and grounded_but_wrong); skewed marginals can depress Cohen's kappa despite high observed agreement, so observed agreement and PABAK are reported alongside kappa, never kappa alone.

## Headline agreement

| metric | n | observed agreement | Cohen's kappa | PABAK |
|---|---|---|---|---|
| six-way label | 120 | 0.925 | 0.8838 | 0.9062 |
| correct vs not (binary) | 120 | 0.9417 | 0.8829 | 0.8833 |
| grounding decision | 24 | 1.0 | None | 1.0 |

PABAK for the six-way row uses the multi-category form (k*po - 1)/(k - 1) with k = 5 categories observed; the two binary rows use 2*po - 1. Grounding is scored only over cells whose judge_grounded is not null (25 present; 1 lacked a human_grounded value).

## Six-way confusion matrix (rows = human, cols = judge)

| human \\ judge | correct | abstention | retrieval_failure | grounded_but_wrong | parametric_error |
|---|---|---|---|---|---|
| correct | 52 | 1 | 0 | 0 | 0 |
| abstention | 4 | 34 | 1 | 0 | 0 |
| retrieval_failure | 0 | 0 | 0 | 0 | 0 |
| grounded_but_wrong | 2 | 0 | 0 | 24 | 0 |
| parametric_error | 0 | 1 | 0 | 0 | 1 |

## Per-condition observed agreement (six-way)

| condition | n | observed agreement |
|---|---|---|
| A | 24 | 0.875 |
| B1 | 24 | 0.875 |
| B2 | 24 | 1.0 |
| C | 24 | 0.875 |
| D | 24 | 1.0 |
