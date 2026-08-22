"""
clean_index
-----------
Clean, GROBID-based extraction and indexing for the diagnostic RAG study.

Corpus-swappable: build a Config (config.py), point it at a PDF folder or DOI list,
name an output Chroma collection, and run build_index. Writes into a NEW collection
(default owf_clean_v1 in chroma_db_clean/) so the frozen study is never touched.

Public surface:
    from core.clean_index.config import Config, default_config
    from core.clean_index.embeddings import build_embeddings
    from core.clean_index.build_index import build, extract_one
"""

from .config import Config, default_config

__all__ = ["Config", "default_config"]
