# Judge taxonomy rubric (H2a human labelling)

Label each cell under the SAME rules the 8b judge used, so human and judge labels
are comparable. Assign exactly one `human_label` from the six below. Also record
`human_grounded` (TRUE or FALSE: is the model answer supported by the documents
shown?) for every cell that HAS documents (conditions B1, B2, C, D); leave it blank
for Condition A (no documents).

The six labels:

- **correct** - the answer matches the gold claim on its key fact (direction,
  magnitude, or conclusion). Applies to ALL conditions (A, B1, B2, C, D).
- **abstention** - the answer declines to give a substantive answer (says it cannot
  tell, does not know, or the information is not in the documents). Applies to ALL
  conditions.
- **retrieval_failure** - wrong (not correct, not abstained) because the documents
  shown did NOT contain the information needed to answer. Applies ONLY to the helpful
  retrieval conditions B1 and B2.
- **ungrounded_hallucination** - wrong, and the answer asserts things NOT supported by
  the documents shown (had context, ignored it, fabricated). Applies to the context
  conditions B1, B2, C, D.
- **grounded_but_wrong** - wrong, but the answer FAITHFULLY follows the documents shown
  (e.g. it followed a counterfactual in D, or followed irrelevant docs in C). Applies to
  the context conditions B1, B2, C, D.
- **parametric_error** - wrong, with NO documents given: a pure parametric-memory miss.
  Applies ONLY to Condition A.

Decision order (mirrors the judge): abstention first, then correctness; if wrong and
Condition A -> parametric_error; if wrong with context in B1/B2 and the documents lack
the answer -> retrieval_failure; otherwise grounded_but_wrong if the answer follows the
documents, else ungrounded_hallucination.
