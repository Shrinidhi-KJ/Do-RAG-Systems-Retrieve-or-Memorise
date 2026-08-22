"""
embeddings.py
-------------
The single source of truth for the embedding recipe, imported by BOTH the indexer and
(in the re-run phase) the retrieval path, so indexing and querying can never drift.

BGE recipe for bge-small-en-v1.5:
  * QUERIES  carry the instruction prefix ("Represent this sentence for searching
    relevant passages:").
  * PASSAGES are embedded plain (no prefix).
  * All vectors L2-normalised (so ChromaDB's L2 distance ranks identically to cosine).

`HuggingFaceBgeEmbeddings` applies `query_instruction` on embed_query() and
`embed_instruction` (here empty) on embed_documents(), which is exactly this recipe.
"""

from langchain_community.embeddings import HuggingFaceBgeEmbeddings


def build_embeddings(config):
    """Construct the BGE embeddings object from a Config. Use this everywhere."""
    return HuggingFaceBgeEmbeddings(
        model_name=config.embedding_model,
        model_kwargs={"device": config.device},
        encode_kwargs={"normalize_embeddings": config.normalize_embeddings},
        query_instruction=config.query_instruction,
        embed_instruction=config.embed_instruction,
    )
