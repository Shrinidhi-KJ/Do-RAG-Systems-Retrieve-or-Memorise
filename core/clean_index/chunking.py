"""
chunking.py
-----------
Section-bounded chunking of a ParsedDoc into LangChain Documents with rich metadata.

Key property: each section (and the abstract, and each caption) is split INDEPENDENTLY,
so a chunk never straddles two sections. This is the concrete improvement over the
frozen index, where the whole paper was concatenated and split blind, letting a chunk
run from one section (or one paper's references) straight into the next.

Per-chunk metadata: source DOI, title, canonical section label, raw section heading,
an is_caption flag (and caption kind), plus chunk bookkeeping.
"""

from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .tei_parser import ParsedDoc


def _splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
        is_separator_regex=False,
    )


def build_documents(parsed: ParsedDoc, doi: str, source: str, config) -> List[Document]:
    """
    Turn one parsed paper into a list of chunk Documents.

    doi:    canonical DOI (from the filename mapping, consistent with the rest of the
            pipeline), stored on every chunk.
    source: the PDF filename, for traceability.
    """
    splitter = _splitter(config.chunk_size, config.chunk_overlap)
    docs: List[Document] = []
    running = 0

    def emit(text: str, *, label: str, head: str, is_caption: bool, kind: str = ""):
        nonlocal running
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if not piece:
                continue
            docs.append(Document(
                page_content=piece,
                metadata={
                    "doi": doi,
                    "title": parsed.title,
                    "source": source,
                    "section": label,
                    "section_head": head,
                    "is_caption": is_caption,
                    "caption_kind": kind,
                    "chunk_index": running,
                },
            ))
            running += 1

    # Abstract first (kept as content, labelled 'abstract').
    if parsed.abstract:
        emit(parsed.abstract, label="abstract", head="Abstract", is_caption=False)

    # Body sections, each split within its own boundary.
    for sec in parsed.sections:
        emit(sec.text, label=sec.label, head=sec.head, is_caption=False)

    # Captions, each its own unit, tagged.
    if config.keep_captions:
        for cap in parsed.captions:
            emit(cap.text, label="caption", head="", is_caption=True, kind=cap.kind)

    # Stamp total after we know it (useful for retrieval-side display).
    total = len(docs)
    for d in docs:
        d.metadata["total_chunks"] = total
    return docs
