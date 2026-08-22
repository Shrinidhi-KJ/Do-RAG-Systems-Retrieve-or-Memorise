# Retrieval recall (Hit@k) of the gold source paper, D3 eval set

Computed 2026-07-19, read-only. Measures how often the retriever surfaces the known-correct source
paper for each of the 12 D3 eval-set items, over the clean index `owf_clean_v1`, using the exact
retriever, embedding model, and query construction the four-condition experiment used. No re-embedding,
no new collection, no re-run of generation/judge/NLI. The existing index was opened read-only.

## Method and reused code (file:line)

- **Retriever (reused, not reimplemented).** The query was embedded and searched through the same call
  the experiment's Condition B1 uses: `conditions.retrieve(question, k)` at
  `core/conditions.py:140-178`, which calls `store.similarity_search_with_score(question, k)` on the
  shared store from `conditions.get_store()` (`core/conditions.py:130-137`). The store is opened by
  `rag_pipeline.load_existing_vector_store()` (`core/rag_pipeline.py:281-306`). This measurement called
  `retrieve(question, k=10)`; nothing else about the path changed.
- **Collection (clean index, read-only).** Default retrieval profile `clean`
  (`core/conditions.py:66-89`): collection `owf_clean_v1` in `chroma_db_clean/`
  (`core/clean_index/config.py:75-76`). Loaded count at run time: 34,502 chunks. The frozen
  `wind_farm_papers` collection was not touched.
- **Embedding model and query-prefix handling.** `BAAI/bge-small-en-v1.5`, built by
  `conditions._clean_embeddings()` -> `build_embeddings(default_config())` (`core/conditions.py:62-64`).
  `build_embeddings` (`core/clean_index/embeddings.py:20-28`) constructs `HuggingFaceBgeEmbeddings` with
  `query_instruction` = "Represent this sentence for searching relevant passages:"
  (`core/clean_index/config.py:26,80`) and `embed_instruction` = "" (`config.py:81`), normalised
  (`config.py:82`). This is the BGE recipe where **the instruction prefix is applied to queries only**
  (via `embed_query`), passages embedded plain. Confirmed matched: this measurement uses `embed_query`
  through `similarity_search_with_score`, so the question carries the prefix and the passages do not,
  exactly as at index time.
- **Query construction.** The experiment feeds the raw item question to B1 at k=5:
  `run_experiment.py:96` (`DEFAULT_K = 5`), `:158` (`question = item["question"]`), `:165`
  (`prepare_B1(question, k=k)`) -> `core/conditions.py:228-234`. This measurement embeds the same raw
  question string. k=5 is the cutoff the experiment actually used for B1/C context, so **Hit@5 is the
  headline**.
- **DOI canonicalisation (both sides).** `conditions.canonicalise_doi()` (`core/conditions.py:93-108`):
  keep the first slash, replace every later slash with an underscore, matching how the clean index
  stored multi-slash (mostly OUP) DOIs. Each item's gold DOI from `d3_eval_set.json` `matched_dois` was
  canonicalised, and compared against the chunk metadata `doi` (already stored in that form). A "hit at
  rank r" = at least one of the top-r retrieved chunks has a canonicalised DOI in the item's gold set.

## Denominator (honesty check)

All 12 gold papers are present in `owf_clean_v1` (each gold DOI, canonicalised, returned at least one
chunk). No item was excluded, so recall is reported over a single denominator of 12. There is no
"indexed-only" subset to separate out.

## Hit@k summary (over all 12 items)

| k | hits | Hit@k |
|---|---|---|
| Hit@1 | 8/12 | 0.667 |
| Hit@3 | 8/12 | 0.667 |
| **Hit@5 (headline)** | **8/12** | **0.667** |
| Hit@10 | 11/12 | 0.917 |

Hit@1 = Hit@3 = Hit@5 because the four items that miss at k=5 all have their first gold chunk at rank
8 or deeper: no gold paper first appears between rank 2 and rank 7 in this set. The four k=5 misses are
D3-03 (first hit rank 8), D3-08 (rank 9), D3-11 (not in top 10), and D3-12 (rank 8). Extending to k=10
recovers three of them (D3-03, D3-08, D3-12); only D3-11 has no gold chunk anywhere in the top 10.

## Per-item table

| item_id | gold DOI (canonicalised) | first-hit rank | Hit@5 |
|---|---|---|---|
| D3-01 | `10.1093/icesjms_fsy006` | 1 | Y |
| D3-02 | `10.1016/j.seares.2009.01.008` | 1 | Y |
| D3-03 | `10.1016/j.ecolind.2018.07.014` | 8 | N |
| D3-04 | `10.1016/j.marenvres.2017.01.009` | 1 | Y |
| D3-05 | `10.1016/j.fishres.2024.106937` | 1 | Y |
| D3-07 | `10.1093/icesjms_fsz050` | 1 | Y |
| D3-08 | `10.1098/rsos.240339` | 9 | N |
| D3-09 | `10.1093/icesjms_fsac107` | 1 | Y |
| D3-10 | `10.1007/s10750-014-1997-z` | 1 | Y |
| D3-11 | `10.1016/j.marpol.2023.105574` | not in top 10 | N |
| D3-12 | `10.1016/j.marenvres.2017.01.009` | 8 | N |
| D3-16 | `10.1016/j.marenvres.2017.01.009` | 1 | Y |

## Sanity check against the B1 retrieval_failure

The experiment's 24 B1 cells (12 items x 2 models) contained exactly one `retrieval_failure`: item
D3-12 (8b). **That is consistent with this Hit@k picture: D3-12 is one of the missed items, with its
first gold chunk only at rank 8, so at the experiment's k=5 the gold paper was not in B1 context.** The
query construction here matches the experiment's, so there is no inconsistency to flag.

Note on why the miss set is larger than the retrieval_failure count. Hit@5 misses four items
(D3-03, D3-08, D3-11, D3-12), but only D3-12/8b was judged `retrieval_failure`. These are different
measurements and the gap is expected, not a contradiction: Hit@k is a pure retrieval metric (was the
gold paper in the top k), whereas `retrieval_failure` is an answer-level judge label conditioned on what
the model then did. For D3-03, D3-08 and D3-11 the gold paper was likewise absent from the top 5, but
the model's answer on those cells was labelled otherwise (for example abstention, or an answer drawn
from parametric memory / topically-near chunks), so they did not surface as `retrieval_failure`. The
one item where the retrieval miss actually produced a diagnosed retrieval failure, D3-12, is captured
by both. Because k=5 recall is only 0.667, retrieval quality (not just generation) is a real constraint
on the RAG conditions, and this is the intended reading of the section.

## Appendix: retrieved DOIs per item (rank. DOI  distance; lower distance = closer)

Chroma returns L2 distance (lower = more similar), matching the note at `core/conditions.py:174`.

**D3-01** gold `10.1093/icesjms_fsy006` first-hit rank 1

```
 1. 10.1093/icesjms_fsy006                     0.4272   <== GOLD
 2. 10.3389/fmars.2026.1748431                 0.4341
 3. 10.3389/fmars.2026.1748431                 0.4781
 4. 10.1093/icesjms_fsy006                     0.4844   <== GOLD
 5. 10.1093/icesjms_fsy006                     0.5185   <== GOLD
 6. 10.1093/icesjms_fsy006                     0.5255   <== GOLD
 7. 10.5670/oceanog.2020.404                   0.5318
 8. 10.1016/j.marpol.2023.105574               0.5413
 9. 10.1093/icesjms_fsy006                     0.5641   <== GOLD
10. 10.1093/icesjms_fsy006                     0.5674   <== GOLD
```

**D3-02** gold `10.1016/j.seares.2009.01.008` first-hit rank 1

```
 1. 10.1016/j.seares.2009.01.008               0.3255   <== GOLD
 2. 10.1093/icesjms_fsz018                     0.3816
 3. 10.1016/j.seares.2009.01.008               0.3833   <== GOLD
 4. 10.1016/j.ecolind.2016.07.037              0.3887
 5. 10.1080/17451000801947043                  0.3890
 6. 10.1016/j.rsma.2023.103100                 0.3907
 7. 10.1016/j.seares.2009.01.008               0.4075   <== GOLD
 8. 10.1016/j.seares.2009.01.008               0.4077   <== GOLD
 9. 10.1016/j.seares.2009.01.008               0.4087   <== GOLD
10. 10.1080/17451000801947043                  0.4092
```

**D3-03** gold `10.1016/j.ecolind.2018.07.014` first-hit rank 8

```
 1. 10.1016/j.ecolind.2016.07.037              0.3488
 2. 10.1016/j.ecolind.2016.07.037              0.3572
 3. 10.1016/j.ecolind.2016.07.037              0.3677
 4. 10.3389/fmars.2024.1379331                 0.3760
 5. 10.1016/j.jmarsys.2020.103434              0.3818
 6. 10.1016/j.ecolind.2016.07.037              0.3844
 7. 10.1016/j.ecolind.2016.07.037              0.3884
 8. 10.1016/j.ecolind.2018.07.014              0.3887   <== GOLD
 9. 10.1016/j.rsma.2025.104218                 0.3912
10. 10.1016/j.marenvres.2013.05.013            0.3938
```

**D3-04** gold `10.1016/j.marenvres.2017.01.009` first-hit rank 1

```
 1. 10.1016/j.marenvres.2017.01.009            0.2957   <== GOLD
 2. 10.1016/j.marenvres.2017.01.009            0.3387   <== GOLD
 3. 10.1016/j.seares.2024.102502               0.3475
 4. 10.1016/j.seares.2024.102502               0.3538
 5. 10.1016/j.seares.2024.102502               0.3638
 6. 10.1007/s10750-014-1997-z                  0.3820
 7. 10.1051/alr_2023001                        0.3938
 8. 10.3389/fmars.2024.1358851                 0.3978
 9. 10.1007/s10750-021-04553-6                 0.3979
10. 10.1007/s10750-014-1997-z                  0.3997
```

**D3-05** gold `10.1016/j.fishres.2024.106937` first-hit rank 1

```
 1. 10.1016/j.fishres.2024.106937              0.2904   <== GOLD
 2. 10.1016/j.fishres.2024.106937              0.4084   <== GOLD
 3. 10.1016/j.marenvres.2017.01.009            0.4392
 4. 10.1016/j.fishres.2024.106937              0.4607   <== GOLD
 5. 10.1016/j.fishres.2024.106937              0.4763   <== GOLD
 6. 10.1016/j.jenvman.2023.119022              0.5037
 7. 10.1016/j.seares.2024.102502               0.5068
 8. 10.1016/j.marenvres.2017.01.009            0.5175
 9. 10.1098/rsos.240339                        0.5204
10. 10.1088/1742-6596_2626_1_012039            0.5304
```

**D3-07** gold `10.1093/icesjms_fsz050` first-hit rank 1

```
 1. 10.1093/icesjms_fsz050                     0.3550   <== GOLD
 2. 10.1093/icesjms_fsz050                     0.3661   <== GOLD
 3. 10.1093/icesjms_fsz050                     0.3817   <== GOLD
 4. 10.1093/icesjms_fsz050                     0.4017   <== GOLD
 5. 10.1093/icesjms_fsz050                     0.4240   <== GOLD
 6. 10.1093/icesjms_fsz050                     0.4272   <== GOLD
 7. 10.1093/icesjms_fsz050                     0.4373   <== GOLD
 8. 10.1093/icesjms_fsz050                     0.4409   <== GOLD
 9. 10.1093/icesjms_fsz050                     0.4472   <== GOLD
10. 10.1093/icesjms_fsz050                     0.4546   <== GOLD
```

**D3-08** gold `10.1098/rsos.240339` first-hit rank 9

```
 1. 10.1016/j.fishres.2024.106937              0.3595
 2. 10.3389/fmars.2026.1743207                 0.3809
 3. 10.1016/j.marenvres.2013.05.013            0.3882
 4. 10.1016/j.fishres.2024.106937              0.3895
 5. 10.2495/cp130121                           0.3931
 6. 10.1016/j.seares.2009.01.008               0.4068
 7. 10.1016/j.marpolbul.2013.07.027            0.4070
 8. 10.1016/j.fishres.2024.106937              0.4074
 9. 10.1098/rsos.240339                        0.4105   <== GOLD
10. 10.1016/j.ecoleng.2024.107189              0.4148
```

**D3-09** gold `10.1093/icesjms_fsac107` first-hit rank 1

```
 1. 10.1093/icesjms_fsac107                    0.3826   <== GOLD
 2. 10.1093/icesjms_fsac107                    0.3830   <== GOLD
 3. 10.1093/icesjms_fsac107                    0.4014   <== GOLD
 4. 10.1016/j.marenvres.2017.01.009            0.4051
 5. 10.1093/icesjms_fsac107                    0.4160   <== GOLD
 6. 10.1016/j.seares.2024.102502               0.4229
 7. 10.1093/icesjms_fsac107                    0.4324   <== GOLD
 8. 10.1016/j.seares.2024.102502               0.4380
 9. 10.1093/icesjms_fsac107                    0.4425   <== GOLD
10. 10.1093/icesjms_fsac107                    0.4425   <== GOLD
```

**D3-10** gold `10.1007/s10750-014-1997-z` first-hit rank 1

```
 1. 10.1007/s10750-014-1997-z                  0.2749   <== GOLD
 2. 10.1007/s10750-014-1997-z                  0.2797   <== GOLD
 3. 10.1007/s10750-014-1997-z                  0.2918   <== GOLD
 4. 10.1007/s10750-014-1997-z                  0.3354   <== GOLD
 5. 10.3389/fmars.2026.1748431                 0.3454
 6. 10.1007/s10750-014-1997-z                  0.3514   <== GOLD
 7. 10.1007/s10750-014-1997-z                  0.3579   <== GOLD
 8. 10.1016/j.jmarsys.2020.103434              0.3605
 9. 10.1007/s10750-014-1997-z                  0.3607   <== GOLD
10. 10.1002/edn3.575                           0.3680
```

**D3-11** gold `10.1016/j.marpol.2023.105574` first-hit rank not in top 10

```
 1. 10.3389/fmars.2025.1561347                 0.3203
 2. 10.1093/icesjms_fsad179                    0.3469
 3. 10.1016/j.rser.2016.11.248                 0.3487
 4. 10.1016/j.marpol.2023.105941               0.3539
 5. 10.1016/j.jmarsys.2020.103434              0.3563
 6. 10.1016/j.jmarsys.2020.103434              0.3612
 7. 10.1093/icesjms_fsy006                     0.3618
 8. 10.1007/s10750-014-1997-z                  0.3633
 9. 10.1007/s10750-014-1997-z                  0.3641
10. 10.3389/fmars.2021.629230                  0.3661
```

**D3-12** gold `10.1016/j.marenvres.2017.01.009` first-hit rank 8

```
 1. 10.1007/s10750-014-1997-z                  0.4157
 2. 10.5194/wes-7-801-2022                     0.4204
 3. 10.1007/s10750-014-1997-z                  0.4230
 4. 10.5194/wes-7-801-2022                     0.4270
 5. 10.1007/s10750-014-1997-z                  0.4284
 6. 10.1007/s10750-014-1997-z                  0.4298
 7. 10.1016/j.rser.2016.11.248                 0.4312
 8. 10.1016/j.marenvres.2017.01.009            0.4323   <== GOLD
 9. 10.1016/j.marenvres.2017.01.009            0.4387   <== GOLD
10. 10.3390/d15020288                          0.4408
```

**D3-16** gold `10.1016/j.marenvres.2017.01.009` first-hit rank 1

```
 1. 10.1016/j.marenvres.2017.01.009            0.4959   <== GOLD
 2. 10.1007/s10750-014-1997-z                  0.5217
 3. 10.1016/j.marenvres.2017.01.009            0.5292   <== GOLD
 4. 10.1007/s10750-014-1997-z                  0.5297
 5. 10.1093/icesjms_fsac107                    0.5339
 6. 10.1007/s10750-014-1997-z                  0.5388
 7. 10.3389/fmars.2020.00379                   0.5478
 8. 10.5670/oceanog.2020.403                   0.5517
 9. 10.1016/j.marpolbul.2013.07.027            0.5594
10. 10.1016/j.ecss.2013.03.012                 0.5664
```
