# Section 8 — Fifteen questions the implementation makes awkward

Read-only audit, 29 July 2026. Each question is one the code *invites*. The answers below
are what the repo actually supports — no spin. Point at the file:line.

---

### Q1. Your README says A ≈ B1 ≥ B2 and concludes the system answers from memory. Your results table says A = 33%, B1 = 92%, B2 = 100%. Which is it?

**Honest answer.** The current result, and the conclusion is the *opposite* of the README's.
`README.md` (and all of `docs/`) documents the superseded 67-item pilot on a noisier index
with auto-generated questions that restated their own answers; it was last touched
2026-06-17 and never revised after the July re-run. On the current data retrieval clearly
helps: A vs B1 is significant in both models separately (p = 0.0078 for 8b, p = 0.0312 for
70b), and B2 ≥ B1. The memorisation signal in this study is **not** "A ≈ B1"; it is
Condition A's popularity gradient and Condition C's small residual.

**Get ahead of it:** say the README and `docs/` are stale before they're opened.

- `README.md:60-80` (stale numbers) · `docs/CUE_CARD.md:22-27` · `docs/WALKTHROUGH.md:164-170`
- Current: `analysis_d3.md:9-13`, reproducible via `core/analyse_results.py`

---

### Q2. Show me the script that computed your McNemar p-values.

**Honest answer.** There isn't one. A grep for `mcnemar`/`binomtest` across every `.py` in
the repo returns zero hits. The p-values in `analysis_d3.md` were computed read-only over
`results_d3.jsonl` in an analysis session and written directly to markdown; the analysis code
was never committed. The inputs are frozen and the arithmetic is hand-checkable — I verified
it: A correct = 8, B1 correct = 22, discordant b(A-only) = 0 / c(B1-only) = 14, exact
two-sided binomial = 2 × 2⁻¹⁴ = 0.00012, continuity-corrected χ² = 13²/14 = 12.0714. All six
rows check out exactly. But I cannot regenerate them with a command.

Same gap for the per-model splits, the clean-index Hit@k, the inter-annotator kappas, and
`judge_outlier_cells.md`.

- `analysis_d3.md:26-33` (the results) · `project_log.md:18` (records that it was done)
- `core/analyse_results.py` computes **no** significance test — only Wilson intervals

---

### Q3. Your `analyse_results.py` prints "all 67 items" and excludes items 2, 34 and 45. You ran 12 items. What is it excluding?

**Honest answer.** That script is pilot-era and I should not have left it pointed at D3.
`EXCLUDE = {2, 34, 45}` are **pilot** indices. On the D3 set, 34 and 45 don't exist but
**index 2 does — it is D3-03**, a perfectly valid item. So the script prints Condition D as
22/22 rather than the correct 24/24. My published figure (`analysis_d3.md:13`) is 0/24, which
is right; the committed script disagrees with my thesis.

Three further defects in the same file: the "67" is hard-coded; 8b and 70b are pooled with
no model split; and the "paired" B1-vs-B2 block keys a dict on `item_idx` alone, so the two
models collide and the 8b half is silently discarded — the printed `Paired (n=12)` is
**70b-only**.

- `core/analyse_results.py:50` (EXCLUDE) · `:98`, `:159` (hard-coded 67) · `:84-88` (no model split) · `:182-188` (the collapse bug)

---

### Q4. You call Condition C "irrelevant documents". Show me what prevents the distractor from being about the same thing as the question.

**Honest answer.** Only one thing does: the item's own gold DOI(s) are excluded from
retrieval (`conditions.py:260` → chunk-level drop at `:167-168`). **There is no topic-level
guard at all** — no distance floor between the distractor query and the question, no tag
exclusion, no check that the retrieved chunks fail to support the claim. And it did not
fully hold:

- The distractor is `random.choice` over a fixed 10-item list seeded by item index
  (`conditions.py:257-259`). That gives only **6 distinct queries across 12 items** — items
  3/4/8, 5/6/10 and 9/11 received **byte-identical** distractor contexts. The 24 C cells span
  6 contexts, not 12.
- **D3-11** asks about fish biomass in closed OWF areas and drew *"commercial fish stock
  displacement by wind farm exclusion zones"* — the same subject. Its context contains
  **D3-10's** gold paper (×2) and **D3-09's** gold paper, because the exclusion removes only
  *this* item's gold. D3-11 (8b) is one of the four cells counted as "correct despite
  irrelevant context".

So of the four C-correct cells: one (D3-11) had topically relevant context, and two
(D3-01/8b, D3-12/8b) were called *abstention* by both human raters. **The defensible
statement is that C ≈ 17% is an upper bound on memorisation-under-noise, not a measurement of
it.**

- `conditions.py:114-125` (the 10 queries) · `:245-264` (prepare_C) · `discrepancies.md` D19

---

### Q5. Your judge, your counterfactual writer, your provenance checker and your smaller subject model are all `llama-3.1-8b-instant`. Isn't the whole thing circular?

**Honest answer.** Yes for the 8b arm, and the docstring makes it worse by claiming a
"STRONGER editor model (Llama 3.3 70B)" that the code does not use. It is 8B — the comment
six lines below explains why (free-tier token caps). What breaks the circle:

1. Two independent human raters labelled **all 120 cells** blind. Binary correct-vs-not
   agreement: KJ 0.9417 / κ 0.883, Aneesha 0.95 / κ 0.900, and the two humans agree with each
   other more (0.975 / κ 0.949) than either agrees with the judge.
2. An independent-family NLI model (DeBERTa-v3-large-mnli, revision pinned) re-checks
   grounding: 0.80 observed agreement, and Condition D's contradicts-gold rate is **1.0**.
3. The 70b arm's answers were judged by a *different* model from the one that produced them —
   and 70b's results match 8b's on every condition except C.

What I cannot claim: independence for the 8b arm's grounding judgments.

- `build_contradictions.py:9-10` (the wrong claim) vs `:65` (`EDITOR_MODEL`) · `classifier.py:39-44`
- `run_config_d3.json:12-19` (correctly records all three roles as 8b)

---

### Q6. Your judge is more lenient than your humans. How much do your headline numbers move?

**Honest answer.** They move down, but the pattern doesn't. Recomputed from both rater CSVs:

| condition | judge (published) | KJ | Aneesha |
|---|---|---|---|
| A | 33.3% | 25.0% | 29.2% |
| B1 | 91.7% | 83.3% | 83.3% |
| B2 | 100% | 100% | 95.8% |
| C | 16.7% | 12.5% | **8.3%** |
| D | 0% | 0% | 0% |

Condition C nearly halves under Aneesha's labels. The direction of judge error is
systematic: of the 6 cells where both humans agreed and only the judge dissented, **4 cross
the correctness boundary and all 4 run the same way — humans say not-correct, judge says
correct.** So the judge inflates every level, and **C is the most affected because it has the
smallest numerator.** D = 0/24 is invariant across all three raters — it is the one number
that does not move.

- `judge_outlier_cells.md` · `judge_validation_kj.md:75-96` · `judge_validation_aneesha.md:99-127`

---

### Q7. Your pooled McNemar treats 24 observations as independent, but they're 12 items measured twice. Is p = 0.0001 real?

**Honest answer.** The pooled test is anti-conservative — the two models' errors on the same
item are correlated (they agree on 10 of 12 items in Condition A), so the effective n is
closer to 12 than 24. I should lead with the **per-model** tests, which do not have this
problem: A vs B1 is p = 0.0078 for 8b and p = 0.0312 for 70b, both under 0.05 on their own.
The finding survives without the pooling. The report already flags that six p-values are
uncorrected for multiplicity — though it miscounts them as "four".

- `analysis_d3.md:28-33`, `:43` (the miscount) · `discrepancies.md` D14, D30

---

### Q8. Hit@5 is 0.667 but B1 is 92%. How is standard RAG correct on items where the retriever never found the right paper?

**Honest answer.** This is the most interesting tension in the study and the answer is
*neither* judge error *nor* pure memorisation. Of the four items whose gold paper is absent
from the top 5 (D3-03, D3-08, D3-11, D3-12), B1 was judged correct on **three, for both
models**. Reading those answers: the retrieved chunks come from **different papers in the
corpus that report the same finding**. D3-03's B1 answer cites Document 3 (a different
`ecolind` paper) saying top-predator activity "strongly increased" — the true claim. D3-11's
context includes two papers describing OWF closures functioning as MPAs.

So **gold-DOI Hit@k understates context adequacy** in a corpus where findings are replicated.
The corollary is the honest one: **Hit@5 = 0.667 and B1 = 92% measure different things, and
the 92% is not evidence that the retriever found the right paper.** A per-answer "is the
supporting fact present in the shown context" metric would be the right measurement, and I
did not build one — the judge's `retrieval_hit` field fired on exactly **one** cell in 120.

- `retrieval_recall_d3.md:57-58, 84-93` · `classifier.py:136-140` (why `retrieval_hit` is near-empty)

---

### Q9. Your `grounded` field is null on 95 of 120 cells. What exactly is your grounding statistic over?

**Honest answer.** Over **25 cells**: the 24 Condition D cells plus the single B1
`retrieval_failure`. The classifier short-circuits — abstentions return at
`classifier.py:120-121` and correct answers at `:125-126`, both *before* the grounding call
at `:135`, and Condition A never reaches it. **The convention is that abstentions carry
`grounded = null`, never `false`.** Nothing was measured for them.

Consequences I should state: (a) every grounding number, including the NLI agreement of 0.80,
is over that 25 and its marginals are near-degenerate (24 of 25 share one class, which is why
κ = 0.23 is uninformative and PABAK/observed agreement is the reported signal); (b) `correct`
is likewise `null` on abstentions — counting abstention as not-correct is a downstream
convention stated at `analysis_d3.md:3`, not a judge output; (c) my two human raters filled
`human_grounded` on **72** cells, far more than the judge's 25.

- `classifier.py:96-143` · verified field-by-field table in `project_reference.md` §4.6

---

### Q10. Your three-way NLI-vs-judge-vs-human grounding comparison says "skipped". Why?

**Honest answer.** Timing, not data. The NLI script ran 2026-07-11; the human labels came
back 2026-07-17 and 07-18. `nli_grounding_d3.md:69` reports it as skipped because
`human_grounded` was empty in `human_label_sheet_d3.csv` **at that time**. Both completed
rater CSVs do carry `human_grounded`, on 72 cells. The code at
`nli_grounding_d3.py:324-351` would compute it correctly if pointed at a rater CSV. I did not
re-run it. That is the strongest validation available to this study and it is currently
unrun — an honest gap, not a limitation of the data.

- `nli_grounding_d3.md:69` · `nli_grounding_d3.py:324-351` · `interannotator_kj_aneesha.md:36`

---

### Q11. How was `popularity` assigned? Your A-condition popularity gradient is your memorisation evidence.

**Honest answer.** By hand, with no recorded rule — and I audited this myself before you
asked (`popularity_audit.md`, 2026-07-13). It exists only as a literal constant in
`d3_eval_set.json`; **no code computes it and no script writes that file.** The one objective
proxy available (`citation_count` from OpenAlex) does not track it: the most-cited paper in
the set (Maar 2009, 163 cites) is tagged `low`, and a `high` item (Berges 2024) has the
fewest citations of all 12. Decisively, **the same paper — Van Hal 2017 — is the source for
three items carrying two different tags** (D3-04 `high`, D3-12 `low`, D3-16 `low`), which
rules out any function of the source paper.

With 2 `high` items and 3 `medium` across 12, the slice "A high 3/4, low 0/14" cannot bear
weight. The intended construct — how widely the *finding* is reported across the literature —
is defensible but was applied by judgement and is not reproducible from any recorded input.
A corpus-internal mention count would fix it; I did not build one.

- `popularity_audit.md` §4, §6 · `analysis_d3.md:57-82` · `methodology_capture.md:51`

---

### Q12. Every item in `d3_eval_set.json` has a `counterfactual` field. Is that what Condition D injects?

**Honest answer.** No — and that is a trap in my own data file. Condition D loads from
`contradictions_cache_d3.json`, generated by the 8B editor at temperature 0.4
(`build_contradictions.py:155`) and looked up by item index at `run_experiment.py:176`. The
eval set's `counterfactual` field is **never read by any code on the result path**. Worse,
the two differ in kind: D3-01's stored field is a *null* counterfactual ("The temporary
closure had no effect on lobster abundance or size"), while the injected passage is a
*directional reversal* ("a significant decline in lobster abundance"). Nothing in the repo
documents the field's purpose or why it is unused.

The design reason D is built by a separate one-time script is sound and stated at
`build_contradictions.py:14-20`: freezing the passages makes D reproducible and
human-auditable. All 12 entries are `source: oracle`, `provenance_supported: true`,
`verified: true`.

- `d3_eval_set.json` (`counterfactual` key on every item) · `conditions.py:322-333`

---

### Q13. Condition D shows one document; B1 and C show five. And D gets the same "use ONLY the documents" instruction. Isn't 0/24 predetermined?

**Honest answer.** Partly, and I should be precise about what D measures. The system prompt
is byte-identical across B1, B2, C and D (`llm_generation.py:57-62`) and instructs the model
to answer using **only** the provided documents. So **D = 0/24 measures instruction-following
under conflict, not unprompted credulity.** A softer prompt ("you may use these documents")
would be the natural ablation, and the code comment at `llm_generation.py:54-56` already
identifies it as the knob to vary. I did not run it.

The 1-vs-5 asymmetry is a genuine controlled difference, disclosed at
`methodology_capture.md:80`: D presents a single passage because a mixture of true and false
documents would confound *conflict* with *aggregation*.

What the result does establish, robustly: with a strong grounding instruction and an
uncontested false document, neither model ever overrode it — **0/24 across both model sizes,
both human raters, and the NLI check (contradicts-gold 1.0)**. That is not predetermined; a
model with strong parametric commitment to the fact could have overridden it, and in
Condition A the 70b model *did* answer 5 of these 12 questions correctly from memory.

- `llm_generation.py:52-62` · `conditions.py:322-333` · `nli_grounding_d3.md:19`

---

### Q14. NLI says only 79% of your D answers are entailed by the false document, but your judge labelled 24/24 grounded. Which is right?

**Honest answer.** Both, on different definitions — and I should quote the two halves
separately. The independent NLI model corroborates the **"wrong"** half at **1.0** (all 24
answers contradict the gold claim, flat across thresholds 0.5/0.7/0.9) and the **"grounded"**
half at **0.79** (19/24 above the 0.5 entailment cut). Five cells fall below: D3-01/8b,
D3-02/70b, D3-03/8b, D3-09/8b, D3-16/70b.

That is expected rather than contradictory: NLI entailment (does this passage logically
entail this sentence?) is stricter than the judge's "is the answer's key assertion derivable
from the passages?", and the script says so explicitly at `nli_grounding_d3.py:24-26`. But
the correct phrasing in the write-up is *"all 24 answers contradicted the truth; 79% were
independently confirmed as entailed by the injected passage"* — not "24/24 grounded".

- `nli_grounding_d3.md:19-46` · `nli_explained.md`

---

### Q15. Your live index has 501 papers, and 9 of your 12 gold papers were added to it specifically because they were missing. Is Hit@5 = 0.667 recall, or recall in a corpus you built to contain the answers?

**Honest answer.** The latter, and it is disclosed. `owf_clean_v1_MANIFEST.md`'s "D3 source
rescue" section records 9 gold papers appended in two runs on 2026-07-08 through the identical
clean pipeline, precisely because verification found the primaries absent.
`methodology_capture.md:33-37` states this as a limitation: *"the corpus was completed to
guarantee retrievability of the tested facts; this is disclosed rather than hidden."*

The consequence for the number: `retrieval_recall_d3.md:42-44` reports Hit@k over a single
denominator of 12 *because* every gold paper is now present. So **0.667 is
retrieval-quality-given-the-paper-is-there**, not end-to-end corpus recall. It is the right
metric for isolating retrieval from coverage — which is the study's purpose — but it is not a
statement about how a real deployment would perform.

The papers themselves are genuine domain literature that the discovery queries should have
caught (`methodology_capture.md:33`), so this is curation, not cherry-picking. Say it in that
order.

- `owf_clean_v1_MANIFEST.md` "D3 source rescue" · `methodology_capture.md:29-37` · `retrieval_recall_d3.md:40-44`

---

## Two things to do before the demo, in priority order

1. **Write one `analyse_d3.py`** that regenerates the McNemar tests, the per-model splits and
   the Hit@k from `results_d3.jsonl` + `owf_clean_v1`. This converts your five weakest
   provenance answers (Q2) into one strong one and is maybe an hour's work. The arithmetic is
   already verified correct — you are committing code, not changing results.
2. **Put a two-line "SUPERSEDED — see `analysis_d3.md`" banner at the top of `README.md`,
   `docs/CUE_CARD.md`, `docs/PROJECT.md`, `docs/WALKTHROUGH.md` and `docs/ARCHITECTURE.md`.**
   Costs nothing, removes the worst failure mode (an examiner reading `CUE_CARD.md:22-27` and
   quoting your old numbers back at you).

Neither was done as part of this read-only audit.
