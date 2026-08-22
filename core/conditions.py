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

import os
import random
from pathlib import Path

from rag_pipeline import load_existing_vector_store
from llm_generation import generate_answer

# The clean-index recipe (correct BGE builder: query-instruction prefix on queries,
# passages plain, normalised). Dual import so this resolves whether the module is run
# flat from core/ (python conditions.py) or as part of the core package.
try:
    from core.clean_index.config import default_config
    from core.clean_index.embeddings import build_embeddings
except ModuleNotFoundError:
    from clean_index.config import default_config
    from clean_index.embeddings import build_embeddings

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# RETRIEVAL CONFIG  (switch collections without editing code)
# ------------------------------------------------------------------
# Two profiles. The DEFAULT is the clean rebuild: collection owf_clean_v1 in
# chroma_db_clean/, embedded with the BGE query-instruction recipe -- the SAME recipe
# used at index time, so the query embedding carries the prefix the passages were
# indexed against (passages were embedded plain). The frozen study's collection stays
# selectable for read-only comparison and is embedded with the old no-prefix recipe.
#
# Switch profile without touching code via the RAG_RETRIEVAL_PROFILE env var:
#     RAG_RETRIEVAL_PROFILE=frozen  python run_experiment.py ...
# (default is "clean"). Individual fields can be overridden with RAG_DB_DIR and
# RAG_COLLECTION if you need an ad-hoc collection.

def _clean_embeddings():
    """BGE query-prefix builder, from the single clean-index source of truth."""
    return build_embeddings(default_config())

RETRIEVAL_PROFILES = {
    "clean": {
        "db_dir": str(ROOT / "chroma_db_clean"),
        "collection": "owf_clean_v1",
        "embeddings": _clean_embeddings,   # BGE, query prefix on queries, normalised
        "embedding_model": "BAAI/bge-small-en-v1.5",
    },
    "frozen": {
        "db_dir": str(ROOT / "chroma_db"),
        "collection": "wind_farm_papers",
        "embeddings": None,                # old plain HuggingFaceEmbeddings, no prefix
        "embedding_model": "BAAI/bge-small-en-v1.5",
    },
}

PROFILE = os.environ.get("RAG_RETRIEVAL_PROFILE", "clean").strip().lower()
if PROFILE not in RETRIEVAL_PROFILES:
    raise ValueError(
        f"Unknown RAG_RETRIEVAL_PROFILE={PROFILE!r}; choose from {list(RETRIEVAL_PROFILES)}"
    )
_CFG = RETRIEVAL_PROFILES[PROFILE]

DB_DIR = os.environ.get("RAG_DB_DIR", _CFG["db_dir"])
COLLECTION = os.environ.get("RAG_COLLECTION", _CFG["collection"])
EMB_MODEL = _CFG["embedding_model"]


def canonicalise_doi(doi):
    """
    Map a true DOI to the form stored in the corpus so a filter/exclude can match it.

    The clean index stored multi-slash DOIs mangled: every slash AFTER the first became
    an underscore (for example true 10.1093/icesjms/fsy006 is stored as
    10.1093/icesjms_fsy006). 15 OUP (10.1093/icesjms) sources are affected, out of 68
    stored DOIs that contain an underscore after the first slash; single-slash DOIs are
    stored unchanged. Rule: keep the first slash, replace every later slash with an
    underscore. (Of those 68, not all are mangled slashes: some Springer book-chapter
    DOIs genuinely contain an underscore, e.g. 10.1007/978-3-031-50256-9_13. Those are
    unaffected -- having no slash after the first, the rule below leaves them untouched.)
    This never mutates stored data -- it only canonicalises the query side before matching.
    """
    if not doi:
        return doi
    head, sep, tail = doi.partition("/")
    if not sep:
        return doi
    return head + "/" + tail.replace("/", "_")

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
    """Load the ChromaDB vector store once and reuse it, using the active profile's
    embedding recipe (BGE query-prefix for the clean collection)."""
    global _store
    if _store is None:
        emb = _CFG["embeddings"]() if _CFG["embeddings"] else None
        _store = load_existing_vector_store(DB_DIR, COLLECTION, EMB_MODEL, embeddings=emb)
    return _store


def retrieve(question, k=5, exclude_dois=None):
    """
    Top-k retrieval via the pipeline's retriever.

    exclude_dois: a DOI or list of DOIs whose chunks must NEVER appear in the result.
    Every DOI is canonicalised to the stored (possibly mangled) form before comparison,
    so a mangled OUP ground-truth paper is excluded too. Used to guarantee Condition C
    never includes ANY of the item's ground-truth papers. The drop is applied per chunk,
    so no chunk whose source DOI is in the list survives. Over-fetches so exclusion still
    leaves k chunks even when several ground-truth chunks rank near the distractor topic.
    """
    store = get_store()

    # Canonicalise every excluded DOI so it matches the stored form. Accept a single DOI
    # or a list; drop falsy entries.
    if exclude_dois is None:
        exclude_set = set()
    elif isinstance(exclude_dois, str):
        exclude_set = {canonicalise_doi(exclude_dois)}
    else:
        exclude_set = {canonicalise_doi(d) for d in exclude_dois if d}

    fetch_k = k + 10 if exclude_set else k
    docs_scores = store.similarity_search_with_score(question, k=fetch_k)

    out = []
    for doc, score in docs_scores:
        doi = doc.metadata.get("doi")
        if doi in exclude_set:
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
def _meta(retrieved):
    """Compact per-chunk provenance for the record: doi, chunk_index, score."""
    return [{kk: r[kk] for kk in ("doi", "chunk_index", "score")} for r in retrieved]


def _finalise(public, gen_context, model=None, temperature=None):
    """
    Generate the subject answer for an already-prepared cell and attach it.

    public:      the cell dict from a prepare_* function (context + provenance, no
                 answer yet).
    gen_context: what to pass as generation context -- None for Condition A (parametric
                 prompt), else the list of context passages.
    model / temperature: forwarded only when set, so the runner can pin the REAL subject
                 model and the determinism temperature. Left None -> the generation
                 layer's defaults, preserving the original single-model behaviour.

    The prepare_*/finalise split lets the runner compute a cell's content-hash key from
    its exact inputs (prompt, context ids, model, k, temperature) BEFORE generating, so
    resume never regenerates or silently reuses a stale answer.
    """
    kwargs = {}
    if model is not None:
        kwargs["model"] = model
    if temperature is not None:
        kwargs["temperature"] = temperature
    public["answer"] = generate_answer(public["question"], context=gen_context, **kwargs)
    return public


def prepare_A(question):
    """Assemble Condition A inputs (no documents). gen_context is None -> parametric."""
    public = {"condition": "A", "question": question, "context_docs": [], "retrieved_meta": []}
    return public, None


def condition_A(question, model=None, temperature=None):
    public, gen_context = prepare_A(question)
    return _finalise(public, gen_context, model, temperature)


# ------------------------------------------------------------------
# CONDITION B1 -- standard RAG, retrieved documents as-is
# ------------------------------------------------------------------
def prepare_B1(question, k=5):
    """Assemble Condition B1 inputs: top-k retrieval as-is."""
    retrieved = retrieve(question, k=k)
    context = [r["text"] for r in retrieved]
    public = {"condition": "B1", "question": question,
              "context_docs": context, "retrieved_meta": _meta(retrieved)}
    return public, context


def condition_B1(question, k=5, model=None, temperature=None):
    public, gen_context = prepare_B1(question, k=k)
    return _finalise(public, gen_context, model, temperature)


# ------------------------------------------------------------------
# CONDITION C -- irrelevant documents (topic mismatch)
# ------------------------------------------------------------------
def prepare_C(question, k=5, gt_dois=None, distractor_query=None, seed=None):
    """
    Assemble Condition C inputs: real chunks about an UNRELATED topic. If the model
    still answers correctly -> it is leaning on parametric memory, not the context.

    gt_dois: the question's ground-truth paper DOI(s), a str or list from
             the eval set's matched_dois. ALL of them are excluded (each canonicalised),
             so no correct paper -- including a mangled OUP one and including every paper
             when an item has several -- can leak into the distractor context.
    distractor_query: force a specific off-topic query; otherwise picked at random.
    Deterministic given seed, so the distractor pick is reproducible per item.
    """
    if seed is not None:
        random.seed(seed)
    dq = distractor_query or random.choice(DISTRACTOR_QUERIES)
    retrieved = retrieve(dq, k=k, exclude_dois=gt_dois)
    context = [r["text"] for r in retrieved]
    public = {"condition": "C", "question": question, "distractor_query": dq,
              "context_docs": context, "retrieved_meta": _meta(retrieved)}
    return public, context


def condition_C(question, k=5, gt_dois=None, distractor_query=None, seed=None,
                model=None, temperature=None):
    public, gen_context = prepare_C(question, k=k, gt_dois=gt_dois,
                                    distractor_query=distractor_query, seed=seed)
    return _finalise(public, gen_context, model, temperature)


# ------------------------------------------------------------------
# CONDITION B2 -- oracle retrieval (best chunks of the KNOWN-correct paper)
# ------------------------------------------------------------------
def prepare_B2(question, gt_dois, k=5):
    """
    Assemble Condition B2 inputs: top-k chunks from the ground-truth paper(s) ONLY.
    Same generation path as B1, but with retrieval quality removed as a confound.

    gt_dois: str or list[str] from the eval set's matched_dois. Canonicalised so a true
             eval-set DOI matches a mangled OUP entry. Stored data is never mutated.
    When the paper is not in the index, returns oracle_available=False and gen_context
    None; the caller must NOT generate (the answer stays None, which is itself data).
    """
    store = get_store()
    if isinstance(gt_dois, str):
        gt_dois = [gt_dois]
    gt_dois = [canonicalise_doi(d) for d in gt_dois]
    flt = {"doi": gt_dois[0]} if len(gt_dois) == 1 else {"doi": {"$in": gt_dois}}

    docs_scores = store.similarity_search_with_score(question, k=k, filter=flt)
    if not docs_scores:
        public = {"condition": "B2", "question": question, "oracle_available": False,
                  "context_docs": [], "retrieved_meta": []}
        return public, None

    context = [d.page_content for d, _ in docs_scores]
    public = {
        "condition": "B2", "question": question, "oracle_available": True,
        "context_docs": context,
        "retrieved_meta": [
            {"doi": d.metadata.get("doi"), "chunk_index": d.metadata.get("chunk_index"), "score": float(s)}
            for d, s in docs_scores
        ],
    }
    return public, context


def condition_B2(question, gt_dois, k=5, model=None, temperature=None):
    public, gen_context = prepare_B2(question, gt_dois, k=k)
    if not public.get("oracle_available", True):
        public["answer"] = None      # ground-truth paper absent: no generation
        return public
    return _finalise(public, gen_context, model, temperature)


# ------------------------------------------------------------------
# CONDITION D -- contradictory documents
# ------------------------------------------------------------------
def prepare_D(question, contradiction_text):
    """
    Assemble Condition D inputs: a single PRE-GENERATED, frozen counterfactual passage
    that asserts the wrong answer. If the model follows it (answers wrongly) -> it is
    reading context; if it overrides the false context with the truth -> parametric
    memory wins. contradiction_text is built once by build_contradictions.py and loaded
    from the cache by the runner -- never generated on the fly, so D is reproducible.
    """
    context = [contradiction_text]
    public = {"condition": "D", "question": question, "context_docs": context,
              "retrieved_meta": [{"doi": "SYNTHETIC_COUNTERFACTUAL", "chunk_index": None, "score": None}]}
    return public, context


def condition_D(question, contradiction_text, model=None, temperature=None):
    public, gen_context = prepare_D(question, contradiction_text)
    return _finalise(public, gen_context, model, temperature)


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
