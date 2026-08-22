"""
config.py
---------
Configuration for the clean GROBID-based extraction and indexing module.

The module is corpus-swappable BY DESIGN: a new corpus is a new Config, not a code
change. Point `pdf_dir` (or `dois_file`) at the papers, give the run a
`collection_name`, and everything downstream (extraction, cleaning, chunking,
embedding, indexing) follows from this object.

Nothing here writes to the frozen study. The default collection is a NEW canonical
collection `owf_clean_v1` in a SEPARATE persist directory `chroma_db_clean/`, so the
archived `chroma_db/` (collection `wind_farm_papers`) is never touched.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, Dict

# core/clean_index/config.py -> parent(clean_index) -> parent(core) -> parent(repo root)
ROOT = Path(__file__).resolve().parent.parent.parent

# The BGE query instruction. bge-small-en-v1.5 is trained so that QUERIES carry this
# prefix and PASSAGES are embedded plain. Applying it is the single biggest retrieval
# fix versus the frozen index, which embedded queries and passages identically.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages:"

# Body-section headings whose content we DROP even if GROBID places them in <body>.
# References/acknowledgements/funding normally live in TEI <back> (which we never read),
# but some publishers emit them as ordinary body sections; this is the belt-and-braces.
DEFAULT_DROP_SECTION_KEYWORDS: Tuple[str, ...] = (
    "reference", "bibliography", "acknowledg", "funding", "grant",
    "conflict of interest", "competing interest", "declaration of competing",
    "author contribution", "credit authorship", "data availability",
    "supplementary", "supporting information", "appendix", "annex",
    "ethics", "consent to publish",
)

# Canonical section labels. The raw heading is always kept too (section_head), so no
# information is lost; this is only for grouping/filtering in analysis.
DEFAULT_SECTION_LABEL_MAP: Dict[str, str] = {
    "abstract": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "related work": "introduction",
    "method": "methods",
    "methods": "methods",
    "methodology": "methods",
    "materials and methods": "methods",
    "material and methods": "methods",
    "experimental": "methods",
    "study area": "methods",
    "data": "methods",
    "result": "results",
    "results": "results",
    "findings": "results",
    "discussion": "discussion",
    "results and discussion": "results",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "concluding remarks": "conclusion",
    "summary": "conclusion",
}


@dataclass
class Config:
    """One run of the clean indexer. Construct a new one to index a new corpus."""

    # --- corpus in ---
    pdf_dir: str = str(ROOT / "PDFs")
    dois_file: Optional[str] = None          # optional: a DOI list; resolved to PDFs on disk

    # --- index out (NEW collection, SEPARATE directory: frozen study untouched) ---
    db_dir: str = str(ROOT / "chroma_db_clean")
    collection_name: str = "owf_clean_v1"

    # --- embedding (correct BGE recipe) ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    query_instruction: str = BGE_QUERY_INSTRUCTION
    embed_instruction: str = ""              # passages embedded plain
    normalize_embeddings: bool = True
    device: str = "cpu"

    # --- chunking (unchanged 1000/200, but now section-bounded) ---
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # --- extraction ---
    grobid_url: str = "http://localhost:8070"
    grobid_timeout: int = 300                # seconds per PDF; CPU CRF is slower on big files
    keep_captions: bool = True
    drop_section_keywords: Tuple[str, ...] = DEFAULT_DROP_SECTION_KEYWORDS
    section_label_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SECTION_LABEL_MAP))

    # --- indexing bookkeeping ---
    batch_size: int = 50
    failure_log: str = str(ROOT / "clean_index_failures.log")
    skip_list: str = str(ROOT / "clean_index_skiplist.txt")

    def describe(self) -> str:
        return (
            f"corpus      : {self.pdf_dir}"
            + (f" (DOI list: {self.dois_file})" if self.dois_file else "")
            + f"\ncollection  : {self.collection_name}  (db_dir: {self.db_dir})"
            f"\nembedding   : {self.embedding_model}  normalise={self.normalize_embeddings}"
            f"\n              query prefix = {self.query_instruction!r}"
            f"\n              passage prefix = {self.embed_instruction!r}"
            f"\nchunking    : {self.chunk_size}/{self.chunk_overlap}, section-bounded"
            f"\ngrobid      : {self.grobid_url}  (timeout {self.grobid_timeout}s)"
            f"\nkeep capts  : {self.keep_captions}"
        )


def default_config() -> Config:
    """The canonical OWF clean-index configuration (owf_clean_v1)."""
    return Config()
