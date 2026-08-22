#!/usr/bin/env python3
"""
RAG Processing Pipeline (LangChain Version)
=============================================
Pipeline stages:
  1. PDF loading and text extraction (LangChain PyPDFLoader)
  2. Text cleaning
  3. Chunking (LangChain RecursiveCharacterTextSplitter)
  4. Embedding (HuggingFace BGE-small via LangChain)
  5. Indexing in ChromaDB (LangChain Chroma integration)
  6. Retrieval testing (LangChain retriever)

Usage:
  # Full pipeline: extract, chunk, embed, index, test
  python rag_pipeline.py --pdf_dir PDFs --db_dir chroma_db

  # Run a custom query on existing index
  python rag_pipeline.py --skip_index --query "impact of wind farms on marine mammals"

  # Reindex after downloading more PDFs
  python rag_pipeline.py --pdf_dir PDFs --db_dir chroma_db --rebuild
"""

import argparse
import os
import re
import sys
import json
from pathlib import Path
from typing import List, Dict, Optional

# ---- Dependency check ----
def ensure_packages(auto_install=None):
    """
    Verify the pipeline's third-party dependencies are importable.

    By default this INSTALLS NOTHING: if anything is missing it raises ImportError
    naming the missing packages and telling you to activate the project venv. An
    unattended `pip install` on import is a hazard -- it fires on any import of this
    module (conditions.py imports it), can mutate the interpreter's environment
    mid-run, and is the last thing you want happening during a live demonstration.

    Opt back into installing explicitly, either per-call with auto_install=True or
    for the process with the environment variable:
        RAG_AUTO_INSTALL=1 python rag_pipeline.py ...

    Returns the list of missing packages (empty when everything is present).
    """
    packages = {
        "langchain": "langchain",
        "langchain_community": "langchain-community",
        "langchain_chroma": "langchain-chroma",
        "langchain_huggingface": "langchain-huggingface",
        "langchain_text_splitters": "langchain-text-splitters",
        "pypdf": "pypdf",
        "chromadb": "chromadb",
        "sentence_transformers": "sentence-transformers",
        "tqdm": "tqdm",
    }
    missing = []
    for module, pip_name in packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return missing

    if auto_install is None:
        auto_install = os.environ.get("RAG_AUTO_INSTALL", "").strip().lower() in (
            "1", "true", "yes", "on",
        )

    if not auto_install:
        raise ImportError(
            "Missing required package(s): " + ", ".join(missing) + ".\n"
            "Activate the project venv and install them there:\n"
            "    Windows:      venv\\Scripts\\activate\n"
            "    macOS/Linux:  source venv/bin/activate\n"
            f"    then:         python -m pip install {' '.join(missing)}\n"
            "Nothing was installed. Set RAG_AUTO_INSTALL=1 to let this module install "
            "them automatically instead."
        )

    print(f"RAG_AUTO_INSTALL is set; installing missing packages: {', '.join(missing)}")
    os.system(f"{sys.executable} -m pip install {' '.join(missing)}")
    print("Packages installed. Continuing...\n")
    return missing

ensure_packages()

from langchain_community.document_loaders import PyPDFLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from tqdm import tqdm

# Repo root = parent of core/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# STAGE 1: PDF LOADING
# ============================================================

def load_pdfs(pdf_dir: str) -> List[Document]:
    """Load all PDFs from a directory using LangChain PyPDFLoader."""
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]

    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        return []

    print(f"\n{'='*60}")
    print(f"  STAGE 1: PDF Loading (LangChain PyPDFLoader)")
    print(f"  PDFs found: {len(pdf_files)}")
    print(f"{'='*60}\n")

    all_docs = []
    success = 0
    failed = 0

    for pdf_file in tqdm(pdf_files, desc="Loading PDFs", unit="pdf", ncols=80):
        pdf_path = os.path.join(pdf_dir, pdf_file)
        doi = pdf_file.replace(".pdf", "").replace("_", "/", 1)

        try:
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()

            if not pages or sum(len(p.page_content) for p in pages) < 100:
                failed += 1
                continue

            # Combine all pages into one document per PDF
            full_text = "\n".join(p.page_content for p in pages)
            doc = Document(
                page_content=full_text,
                metadata={
                    "doi": doi,
                    "source": pdf_file,
                    "total_pages": len(pages),
                }
            )
            all_docs.append(doc)
            success += 1

        except Exception as e:
            print(f"  Error loading {pdf_file}: {e}")
            failed += 1

    print(f"\n  Loaded: {success} | Failed: {failed}")
    return all_docs


# ============================================================
# STAGE 2: TEXT CLEANING
# ============================================================

def clean_document_text(text: str) -> str:
    """Clean extracted PDF text by removing common noise."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\n\s*\d{1,3}\s*\n", "\n", text)
    text = re.sub(r"\n.*(?:Downloaded from|All rights reserved|Copyright \u00a9).*\n", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]{3,}", " ", text)
    text = re.sub(r" +", " ", text)

    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
        elif len(stripped) >= 5:
            cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_documents(docs: List[Document]) -> List[Document]:
    """Clean all loaded documents."""
    print(f"\n{'='*60}")
    print(f"  STAGE 2: Text Cleaning")
    print(f"  Documents to clean: {len(docs)}")
    print(f"{'='*60}\n")

    cleaned = []
    for doc in tqdm(docs, desc="Cleaning text", unit="doc", ncols=80):
        cleaned_text = clean_document_text(doc.page_content)
        cleaned_doc = Document(
            page_content=cleaned_text,
            metadata=doc.metadata.copy(),
        )
        cleaned_doc.metadata["char_count"] = len(cleaned_text)
        cleaned.append(cleaned_doc)

    total_chars = sum(len(d.page_content) for d in cleaned)
    avg_chars = total_chars // len(cleaned) if cleaned else 0
    print(f"\n  Total characters: {total_chars:,}")
    print(f"  Average per document: {avg_chars:,}")

    return cleaned


# ============================================================
# STAGE 3: CHUNKING
# ============================================================

def chunk_documents(
    docs: List[Document],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[Document]:
    """
    Split documents into chunks using LangChain RecursiveCharacterTextSplitter.
    chunk_size=1000 characters is roughly 150-200 words.
    chunk_overlap=200 characters provides context continuity.
    """
    print(f"\n{'='*60}")
    print(f"  STAGE 3: Chunking (LangChain RecursiveCharacterTextSplitter)")
    print(f"  Chunk size: {chunk_size} chars | Overlap: {chunk_overlap} chars")
    print(f"{'='*60}\n")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
        is_separator_regex=False,
    )

    all_chunks = []

    for doc in tqdm(docs, desc="Chunking", unit="doc", ncols=80):
        chunks = text_splitter.split_documents([doc])
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["total_chunks"] = len(chunks)
        all_chunks.extend(chunks)

    print(f"\n  Total chunks: {len(all_chunks)}")
    if all_chunks:
        avg_len = sum(len(c.page_content) for c in all_chunks) // len(all_chunks)
        print(f"  Average chunk length: {avg_len} characters")

    return all_chunks


# ============================================================
# STAGE 4 & 5: EMBEDDING + CHROMADB INDEXING
# ============================================================

def create_vector_store(
    chunks: List[Document],
    db_dir: str = "chroma_db",
    collection_name: str = "wind_farm_papers",
    embedding_model: str = "BAAI/bge-small-en-v1.5",
) -> Chroma:
    """Embed chunks and store in ChromaDB using LangChain Chroma integration."""
    print(f"\n{'='*60}")
    print(f"  STAGE 4 & 5: Embedding + ChromaDB Indexing")
    print(f"  Model: {embedding_model}")
    print(f"  Chunks to index: {len(chunks)}")
    print(f"  Database: {db_dir}")
    print(f"{'='*60}\n")

    print("  Loading embedding model (first run downloads ~130MB)...")
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    import hashlib
    ids = []
    for i, chunk in enumerate(chunks):
        doi = chunk.metadata.get("doi", "unknown")
        chunk_idx = chunk.metadata.get("chunk_index", i)
        chunk_id = hashlib.md5(f"{doi}_{chunk_idx}".encode()).hexdigest()[:12]
        ids.append(chunk_id)

    batch_size = 50
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    print(f"  Indexing {len(chunks)} chunks in {total_batches} batches...\n")

    vectorstore = None

    for i in tqdm(range(0, len(chunks), batch_size), desc="Embedding & Indexing", unit="batch", ncols=80, total=total_batches):
        batch_chunks = chunks[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]

        if vectorstore is None:
            vectorstore = Chroma.from_documents(
                documents=batch_chunks,
                embedding=embeddings,
                ids=batch_ids,
                collection_name=collection_name,
                persist_directory=db_dir,
            )
        else:
            vectorstore.add_documents(
                documents=batch_chunks,
                ids=batch_ids,
            )

    print(f"\n  Indexed {len(chunks)} chunks in ChromaDB")
    return vectorstore


def load_existing_vector_store(
    db_dir: str = "chroma_db",
    collection_name: str = "wind_farm_papers",
    embedding_model: str = "BAAI/bge-small-en-v1.5",
    embeddings=None,
) -> Chroma:
    """
    Load an existing ChromaDB vector store.

    embeddings: a pre-built embedding function to use for the QUERY path. Pass this
    to select the retrieval recipe (for owf_clean_v1 this is the BGE query-instruction
    builder, so queries carry the prefix the passages were indexed against). If left
    None, we fall back to the old plain HuggingFaceEmbeddings (no prefix) -- the recipe
    the frozen wind_farm_papers collection was built with.
    """
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return Chroma(
        collection_name=collection_name,
        persist_directory=db_dir,
        embedding_function=embeddings,
    )


# ============================================================
# STAGE 6: RETRIEVAL TESTING
# ============================================================

def test_retrieval(vectorstore: Chroma, queries: List[str], top_k: int = 5):
    """Test retrieval using LangChain retriever interface."""
    print(f"\n{'='*60}")
    print(f"  STAGE 6: Retrieval Testing (LangChain Retriever)")
    print(f"  Test queries: {len(queries)}")
    print(f"  Top-K: {top_k}")
    print(f"{'='*60}\n")

    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": top_k},
    )

    for i, query in enumerate(queries, 1):
        print(f"  Query {i}: \"{query}\"")
        print(f"  {'-'*50}")

        results = retriever.invoke(query)

        if not results:
            print("  No results found.\n")
            continue

        for j, doc in enumerate(results, 1):
            preview = doc.page_content[:200].replace("\n", " ")
            doi = doc.metadata.get("doi", "unknown")
            chunk_idx = doc.metadata.get("chunk_index", "?")
            total = doc.metadata.get("total_chunks", "?")
            print(f"\n  Result {j}:")
            print(f"  DOI: {doi}")
            print(f"  Chunk: {chunk_idx}/{total}")
            print(f"  Preview: {preview}...")

        print()

    # Show relevance scores for first query
    print(f"  {'='*50}")
    print(f"  Relevance scores for first query:")
    print(f"  {'='*50}\n")

    results_with_scores = vectorstore.similarity_search_with_score(queries[0], k=top_k)
    for doc, score in results_with_scores:
        doi = doc.metadata.get("doi", "unknown")
        print(f"  Score: {score:.4f} | DOI: {doi} | Chunk: {doc.metadata.get('chunk_index', '?')}")
    print()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="RAG Processing Pipeline (LangChain)")
    parser.add_argument("--pdf_dir", default=str(ROOT / "PDFs"), help="Directory containing PDF files")
    parser.add_argument("--db_dir", default=str(ROOT / "chroma_db"), help="ChromaDB storage directory")
    parser.add_argument("--chunk_size", type=int, default=1000, help="Chunk size in characters")
    parser.add_argument("--chunk_overlap", type=int, default=200, help="Chunk overlap in characters")
    parser.add_argument("--embedding_model", default="BAAI/bge-small-en-v1.5", help="HuggingFace embedding model")
    parser.add_argument("--collection_name", default="wind_farm_papers", help="ChromaDB collection name")
    parser.add_argument("--top_k", type=int, default=5, help="Number of results to retrieve")
    parser.add_argument("--query", type=str, default=None, help="Run a single custom query")
    parser.add_argument("--skip_index", action="store_true", help="Skip indexing, query existing DB")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of the index")
    args = parser.parse_args()

    default_queries = [
        "What is the impact of offshore wind farms on marine mammals?",
        "How do wind turbines affect seabird populations?",
        "What are the effects of pile driving noise on fish?",
        "How does wind farm construction affect seabed integrity?",
        "What environmental monitoring is required for wind farm development?",
    ]

    if args.skip_index:
        print("\nLoading existing ChromaDB index...")
        vectorstore = load_existing_vector_store(
            args.db_dir, args.collection_name, args.embedding_model
        )
        count = vectorstore._collection.count()
        print(f"Collection loaded: {count} chunks")

        queries = [args.query] if args.query else default_queries
        test_retrieval(vectorstore, queries, args.top_k)
        return

    # Full pipeline
    docs = load_pdfs(args.pdf_dir)
    if not docs:
        print("No documents loaded. Check your PDF directory.")
        return

    cleaned = clean_documents(docs)
    chunks = chunk_documents(cleaned, args.chunk_size, args.chunk_overlap)
    if not chunks:
        print("No chunks created. Check your documents.")
        return

    # Save chunks metadata
    chunks_meta = []
    for c in chunks:
        chunks_meta.append({
            "doi": c.metadata.get("doi"),
            "chunk_index": c.metadata.get("chunk_index"),
            "total_chunks": c.metadata.get("total_chunks"),
            "char_count": len(c.page_content),
            "preview": c.page_content[:100],
        })
    with open(ROOT / "chunks_metadata.json", "w", encoding="utf-8") as f:
        json.dump(chunks_meta, f, indent=2, ensure_ascii=False)
    print(f"\n  Chunks metadata saved to: chunks_metadata.json")

    vectorstore = create_vector_store(
        chunks, args.db_dir, args.collection_name, args.embedding_model
    )

    queries = [args.query] if args.query else default_queries
    test_retrieval(vectorstore, queries, args.top_k)

    # Summary
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  PDFs processed:      {len(docs)}")
    print(f"  Chunks created:      {len(chunks)}")
    print(f"  ChromaDB location:   {args.db_dir}")
    print(f"  Collection:          {args.collection_name}")
    print(f"  Embedding model:     {args.embedding_model}")
    print(f"{'='*60}")
    print(f"\n  Quick commands:")
    print(f"  Custom query:   python rag_pipeline.py --skip_index --query \"your question\"")
    print(f"  Rebuild index:  python rag_pipeline.py --pdf_dir PDFs --rebuild")


if __name__ == "__main__":
    main()
