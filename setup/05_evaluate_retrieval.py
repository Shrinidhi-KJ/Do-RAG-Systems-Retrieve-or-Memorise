#!/usr/bin/env python3
"""
Evaluate retrieval recall using the pilot evaluation set.

For each (question, expected_dois) pair in the eval set:
  1. Run the question through the RAG retriever
  2. Get the top-k chunks
  3. Check whether the expected DOIs appear in the retrieved chunks
  4. Compute recall@k for k = 1, 3, 5, 10

This gives us a quantitative measure of retrieval quality BEFORE running
the full four-condition experiment. If retrieval recall is poor, we know
the RAG system has a retrieval problem rather than a memorisation problem.

Usage:
  python 05_evaluate_retrieval.py \
      --eval_set pilot_eval_set.json \
      --db_dir chroma_db
"""

import argparse
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Set

# Repo root = parent of setup/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent

# Dependency check
required_packages = ["langchain_chroma", "langchain_huggingface", "tqdm"]
for module in required_packages:
    try:
        __import__(module)
    except ImportError:
        print(f"Required package missing: {module}")
        print("Make sure your venv is activated. Run rag_pipeline.py first if not.")
        sys.exit(1)

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from tqdm import tqdm


def load_vector_store(db_dir: str, collection_name: str, embedding_model: str) -> Chroma:
    """Load the existing ChromaDB."""
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


def evaluate_question(
    question: str,
    expected_dois: Set[str],
    vectorstore: Chroma,
    max_k: int = 10,
) -> Dict:
    """
    Retrieve top-K chunks for a question and compute recall at various K values.
    """
    # Retrieve max_k chunks
    results = vectorstore.similarity_search_with_score(question, k=max_k)

    # Extract DOIs in order of relevance
    retrieved_dois_ranked = []
    for doc, score in results:
        doi = doc.metadata.get("doi")
        if doi:
            retrieved_dois_ranked.append((doi, score))

    # Compute recall at different K values
    recall_at_k = {}
    for k in [1, 3, 5, 10]:
        top_k_dois = set(doi for doi, _ in retrieved_dois_ranked[:k])
        # Is at least one expected DOI in the top-k?
        hit = bool(top_k_dois & expected_dois)
        # What fraction of expected DOIs are in top-k?
        if expected_dois:
            recall = len(top_k_dois & expected_dois) / len(expected_dois)
        else:
            recall = 0.0
        recall_at_k[f"recall@{k}"] = recall
        recall_at_k[f"hit@{k}"] = 1 if hit else 0

    return {
        "question": question,
        "expected_dois": list(expected_dois),
        "retrieved_top10": [{"doi": doi, "score": float(score)} for doi, score in retrieved_dois_ranked[:10]],
        "metrics": recall_at_k,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate retrieval recall on the pilot eval set")
    parser.add_argument("--eval_set", default=str(ROOT / "pilot_eval_set.json"))
    parser.add_argument("--db_dir", default=str(ROOT / "chroma_db"))
    parser.add_argument("--collection_name", default="wind_farm_papers")
    parser.add_argument("--embedding_model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--output_file", default=str(ROOT / "retrieval_evaluation.json"))
    parser.add_argument("--max_k", type=int, default=10)
    args = parser.parse_args()

    # Load eval set
    if not os.path.exists(args.eval_set):
        print(f"Error: {args.eval_set} not found.")
        print("Run 04_build_pilot_eval_set.py first.")
        sys.exit(1)

    with open(args.eval_set, "r", encoding="utf-8") as f:
        eval_set = json.load(f)

    # Filter to only entries with matched DOIs
    eval_set = [e for e in eval_set if e.get("matched_dois")]

    print("="*60)
    print("  Retrieval Evaluation")
    print("="*60)
    print(f"  Eval set size:    {len(eval_set)}")
    print(f"  Vector DB:        {args.db_dir}")
    print(f"  Max top-K:        {args.max_k}")
    print("="*60)
    print()

    if not eval_set:
        print("No evaluation entries with matched DOIs. Cannot evaluate.")
        return

    # Load vector store
    print("Loading vector store...")
    vectorstore = load_vector_store(
        args.db_dir, args.collection_name, args.embedding_model
    )
    print(f"  Collection has {vectorstore._collection.count()} chunks")
    print()

    # Evaluate each question
    results = []
    aggregate = defaultdict(list)

    for entry in tqdm(eval_set, desc="Evaluating", unit="q", ncols=80):
        question = entry["question"]
        expected_dois = set(entry["matched_dois"])

        result = evaluate_question(question, expected_dois, vectorstore, args.max_k)
        results.append(result)

        for metric, value in result["metrics"].items():
            aggregate[metric].append(value)

    # Compute aggregate metrics
    print()
    print("="*60)
    print("  RESULTS")
    print("="*60)
    print()

    for k in [1, 3, 5, 10]:
        hit_rate = sum(aggregate[f"hit@{k}"]) / len(aggregate[f"hit@{k}"])
        avg_recall = sum(aggregate[f"recall@{k}"]) / len(aggregate[f"recall@{k}"])
        print(f"  At top-{k:2d}:  Hit rate = {hit_rate:.1%}  |  Avg recall = {avg_recall:.1%}")

    print()
    print("  Interpretation:")
    print("    Hit rate@k    = % of questions where AT LEAST ONE expected DOI is in top-k")
    print("    Avg recall@k  = average fraction of expected DOIs found in top-k")
    print()

    # Show some example results
    print("  Sample results (first 3 questions):")
    print()
    for r in results[:3]:
        print(f"  Q: {r['question'][:120]}...")
        print(f"     Expected: {r['expected_dois'][:3]}")
        retrieved_top3 = [x['doi'] for x in r['retrieved_top10'][:3]]
        print(f"     Retrieved top-3: {retrieved_top3}")
        print(f"     Hit@3: {bool(r['metrics']['hit@3'])}")
        print()

    # Save full results
    summary = {
        "n_questions": len(results),
        "aggregate_metrics": {
            k: sum(v) / len(v) for k, v in aggregate.items()
        },
        "results": results,
    }
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"  Full results saved to: {args.output_file}")
    print()
    print("="*60)
    print("  WHAT TO DO WITH THESE NUMBERS")
    print("="*60)
    print()
    print("  Good retrieval recall = Hit@5 above 70%")
    print("  Excellent retrieval   = Hit@5 above 85%")
    print()
    print("  If results are poor, consider:")
    print("    1. Smaller chunk size (current: 1000 chars)")
    print("    2. Different embedding model (try BGE-base or BGE-large)")
    print("    3. Hybrid search (combine semantic + BM25)")
    print("    4. Query rewriting / HyDE")
    print()
    print("  These numbers will go in your dissertation methodology section")
    print("  as a baseline of retrieval quality.")


if __name__ == "__main__":
    main()
