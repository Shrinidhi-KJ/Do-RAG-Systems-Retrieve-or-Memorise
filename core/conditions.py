"""
conditions.py
-------------
The experimental conditions for the four-condition diagnostic study.

Each condition is a function that takes a question and returns a result dict:
    {
        "condition":   "A" | "B1" | "B2" | "C" | "D",
        "question":    str,
        "context_docs": list[str],          # what was fed to the model (may be [])
        "retrieved_meta": list[dict],       # doi/chunk/score per context doc
        "answer":      str,                 # the model's answer
    }

This keeps everything the item-3 failure classifier will need (what was retrieved,
what the model said) in one structured object you can dump straight to JSON.

Built on the EXACT retriever from rag_pipeline.py, so retrieval is identical to
the pipeline that produced your Hit@k numbers. No reimplementation, no drift.

Requires: rag_pipeline.py and llm_generation.py in the same folder, (venv) active,
GROQ_API_KEY set, and the chroma_db/ index present.

Demo (runs A, B1, C on one real question):
    python conditions.py
"""

import random
from pathlib import Path

from rag_pipeline import load_existing_vector_store
from llm_generation import generate_answer

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent
DB_DIR = str(ROOT / "chroma_db")
COLLECTION = "wind_farm_papers"
EMB_MODEL = "BAAI/bge-small-en-v1.5"

# Distractor queries spanning your D1-D11 descriptors, used to build Condition C.
# For an "irrelevant" context we retrieve real, fluent, on-corpus chunks that are
# about a DIFFERENT topic than the question -- a harder, more honest test than
# random chunks, because the docs look superficially like plausible context.
DISTRACTOR_QUERIES = [
    "non-indigenous species colonising offshore wind turbine foundations",
    "marine litter accumulation around offshore installations",
    "eutrophication and nutrient enrichment in coastal seas",
    "seabed sediment disturbance during foundation installation",
    "contaminant release from anti-corrosion coatings on turbines",
    "food web changes from artificial reef effects",
    "hydrological regime and current patterns near wind farms",
    "commercial fish stock displacement by wind farm exclusion zones",
    "seabird collision risk with turbine rotors",
    "electromagnetic fields from subsea cables and elasmobranchs",
]

_store = None


def get_store():
    """Load the ChromaDB vector store once and reuse it."""
    global _store
    if _store is None:
        _store = load_existing_vector_store(DB_DIR, COLLECTION, EMB_MODEL)
    return _store


def retrieve(question, k=5, exclude_doi=None):
    """
    Top-k retrieval via the pipeline's retriever.

    exclude_doi: if given, drops any chunk from that DOI before returning. Used to
    guarantee Condition C never accidentally includes the ground-truth paper.
    Over-fetches a little so exclusion still leaves k chunks.
    """
    store = get_store()
    fetch_k = k + 5 if exclude_doi else k
    docs_scores = store.similarity_search_with_score(question, k=fetch_k)

    out = []
    for doc, score in docs_scores:
        doi = doc.metadata.get("doi")
        if exclude_doi and doi == exclude_doi:
            continue
        out.append({
            "text": doc.page_content,
            "doi": doi,
            "chunk_index": doc.metadata.get("chunk_index"),
            "score": float(score),  # Chroma distance: lower = more similar
        })
        if len(out) == k:
            break
    return out


# ------------------------------------------------------------------
# CONDITION A -- parametric memory, no retrieval
# ------------------------------------------------------------------
def condition_A(question):
    answer = generate_answer(question, context=None)
    return {
        "condition": "A",
        "question": question,
        "context_docs": [],
        "retrieved_meta": [],
        "answer": answer,
    }


# ------------------------------------------------------------------
# CONDITION B1 -- standard RAG, retrieved documents as-is
# ------------------------------------------------------------------
def condition_B1(question, k=5):
    retrieved = retrieve(question, k=k)
    context = [r["text"] for r in retrieved]
    answer = generate_answer(question, context=context)
    return {
        "condition": "B1",
        "question": question,
        "context_docs": context,
        "retrieved_meta": [{kk: r[kk] for kk in ("doi", "chunk_index", "score")} for r in retrieved],
        "answer": answer,
    }


# ------------------------------------------------------------------
# CONDITION C -- irrelevant documents (topic mismatch)
# ------------------------------------------------------------------
def condition_C(question, k=5, gt_doi=None, distractor_query=None, seed=None):
    """
    Feed the model real chunks about an UNRELATED topic. If it still answers
    correctly -> it is leaning on parametric memory, not the context.

    gt_doi: the question's ground-truth paper. If known, it is excluded so the
            answer can't leak in. (Comes from pilot_eval_set.json once wired.)
    distractor_query: force a specific off-topic query; otherwise picked at random.
    """
    if seed is not None:
        random.seed(seed)
    dq = distractor_query or random.choice(DISTRACTOR_QUERIES)
    retrieved = retrieve(dq, k=k, exclude_doi=gt_doi)
    context = [r["text"] for r in retrieved]
    answer = generate_answer(question, context=context)
    return {
        "condition": "C",
        "question": question,
        "distractor_query": dq,
        "context_docs": context,
        "retrieved_meta": [{kk: r[kk] for kk in ("doi", "chunk_index", "score")} for r in retrieved],
        "answer": answer,
    }


# ------------------------------------------------------------------
# CONDITION B2 -- oracle retrieval (best chunks of the KNOWN-correct paper)
# ------------------------------------------------------------------
def condition_B2(question, gt_dois, k=5):
    """
    Retrieve ONLY from the ground-truth paper(s). This is the same generation
    path as B1, but with retrieval quality removed as a confound: B1 vs B2 tells
    you how much of B1's behaviour is the retriever missing the right paper
    (your Hit@5=43%) versus the model's grounding behaviour itself.

    gt_dois: str or list[str] from pilot_eval_set.json["matched_dois"].
    Returns "oracle_available": False if the ground-truth paper isn't in the
    index (e.g. one of the 4 PDFs that failed to load) -- which is itself data.
    """
    store = get_store()
    if isinstance(gt_dois, str):
        gt_dois = [gt_dois]
    flt = {"doi": gt_dois[0]} if len(gt_dois) == 1 else {"doi": {"$in": gt_dois}}

    docs_scores = store.similarity_search_with_score(question, k=k, filter=flt)
    if not docs_scores:
        return {
            "condition": "B2",
            "question": question,
            "oracle_available": False,
            "context_docs": [],
            "retrieved_meta": [],
            "answer": None,
        }

    context = [d.page_content for d, _ in docs_scores]
    answer = generate_answer(question, context=context)
    return {
        "condition": "B2",
        "question": question,
        "oracle_available": True,
        "context_docs": context,
        "retrieved_meta": [
            {"doi": d.metadata.get("doi"), "chunk_index": d.metadata.get("chunk_index"), "score": float(s)}
            for d, s in docs_scores
        ],
        "answer": answer,
    }


# ------------------------------------------------------------------
# CONDITION D -- contradictory documents
# ------------------------------------------------------------------
def condition_D(question, contradiction_text):
    """
    Feed a PRE-GENERATED, frozen counterfactual passage that asserts the wrong
    answer. If the model follows it (answers wrongly) -> it is reading context.
    If it overrides the false context with the truth -> parametric memory wins.

    contradiction_text is built once by build_contradictions.py and loaded from
    the cache by the runner -- never generated on the fly, so D is reproducible.
    """
    context = [contradiction_text]
    answer = generate_answer(question, context=context)
    return {
        "condition": "D",
        "question": question,
        "context_docs": context,
        "retrieved_meta": [{"doi": "SYNTHETIC_COUNTERFACTUAL", "chunk_index": None, "score": None}],
        "answer": answer,
    }


if __name__ == "__main__":
    q = "What are the main effects of offshore wind farm pile-driving noise on harbour porpoises?"

    print("=" * 70, "\nCONDITION A  (no retrieval)\n", "=" * 70, sep="")
    print(condition_A(q)["answer"])

    print("\n" + "=" * 70, "\nCONDITION B1  (real RAG on your corpus)\n", "=" * 70, sep="")
    b1 = condition_B1(q)
    print(b1["answer"])
    print("\n  Retrieved DOIs:", [m["doi"] for m in b1["retrieved_meta"]])

    print("\n" + "=" * 70, "\nCONDITION C  (irrelevant docs)\n", "=" * 70, sep="")
    c = condition_C(q, seed=42)
    print(c["answer"])
    print("\n  Distractor topic:", c["distractor_query"])
    print("  Irrelevant DOIs fed:", [m["doi"] for m in c["retrieved_meta"]])
