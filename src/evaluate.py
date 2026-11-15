"""Evaluación de TF-IDF y BM25 con Recall@K (K = 5 y 10) y MRR.

Sexto paso del pipeline. Sigue la sección 4.4 del notebook de referencia.

Para cada consulta de queries.jsonl:
  1. Se preprocesa igual que las recetas.
  2. Se recuperan los fragmentos con TF-IDF y con BM25.
  3. Se pasa a nivel de documento (mejor fragmento de cada documento, sin
     repetidos) y se guardan los 10 primeros.
  4. Se mira en qué posición está la receta relevante.

Métricas:
  - Recall@K: fracción de consultas cuya receta relevante está entre las K
    primeras (cada consulta tiene una sola receta relevante).
  - MRR: media de 1/posición de la receta relevante (0 si no está en las 10
    primeras).

Uso (desde la raíz del repo):
    python src/evaluate.py

Salida: tabla por pantalla y results/evaluation/per_query.csv con la posición
de la receta relevante en cada consulta.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from preprocess import load_pipeline, load_tokens, preprocess_queries
from retrieval import (build_bm25, build_tfidf, load_chunks, retrieve_bm25,
                       retrieve_tfidf, to_documents)

ROOT = Path(__file__).resolve().parents[1]
QUERIES_PATH = ROOT / "queries.jsonl"
OUTPUT_PATH = ROOT / "results" / "evaluation" / "per_query.csv"

K_MAX = 10   # se evalúa sobre los 10 primeros documentos


def recall_at_k(rankings, relevant, k):
    """Media, sobre las consultas, de la fracción de documentos relevantes
    que aparecen entre los k primeros."""
    recalls = []
    for ranking, rel in zip(rankings, relevant):
        found = len(set(ranking[:k]) & rel)
        recalls.append(found / len(rel))
    return float(np.mean(recalls))


def mrr(rankings, relevant):
    """Media de 1/posición del primer documento relevante (0 si no aparece)."""
    reciprocal_ranks = []
    for ranking, rel in zip(rankings, relevant):
        rr = 0.0
        for rank, doc_id in enumerate(ranking, 1):
            if doc_id in rel:
                rr = 1 / rank
                break
        reciprocal_ranks.append(rr)
    return float(np.mean(reciprocal_ranks))


def rank_of_relevant(ranking, rel):
    """Posición del primer documento relevante (None si no está en la lista)."""
    for rank, doc_id in enumerate(ranking, 1):
        if doc_id in rel:
            return rank
    return None


def main():
    # Datos e índices
    chunks = load_chunks()
    chunk_ids, corpus = load_tokens()
    nlp, stopwords, phrase_model, D = load_pipeline()
    tfidf, index = build_tfidf(corpus, D)
    bm25 = build_bm25(corpus)

    # Consultas de prueba
    with open(QUERIES_PATH, encoding="utf-8") as f:
        queries = [json.loads(line) for line in f]
    relevant = [set(q["relevant_ids"]) for q in queries]
    query_tokens = preprocess_queries([q["query"] for q in queries],
                                      nlp, stopwords, phrase_model)

    # Rankings de documentos (los 10 primeros) con cada método
    rankings_tfidf, rankings_bm25 = [], []
    for tokens in query_tokens:
        rows = retrieve_tfidf(tokens, D, tfidf, index, k=K_MAX)
        rankings_tfidf.append(to_documents(rows, chunks, k=K_MAX))
        rows = retrieve_bm25(tokens, bm25, k=K_MAX)
        rankings_bm25.append(to_documents(rows, chunks, k=K_MAX))

    # Tabla de resultados
    results = pd.DataFrame({
        "Recall@5": [recall_at_k(rankings_tfidf, relevant, 5),
                     recall_at_k(rankings_bm25, relevant, 5)],
        "Recall@10": [recall_at_k(rankings_tfidf, relevant, 10),
                      recall_at_k(rankings_bm25, relevant, 10)],
        "MRR": [mrr(rankings_tfidf, relevant), mrr(rankings_bm25, relevant)],
    }, index=["TF-IDF", "BM25"])
    print(f"{len(queries)} consultas | {len(chunks):,} recetas\n")
    print(results.round(3))

    # Posición de la receta relevante en cada consulta
    per_query = pd.DataFrame({
        "qid": [q["qid"] for q in queries],
        "query_type": [q["query_type"] for q in queries],
        "rank_tfidf": [rank_of_relevant(r, rel) for r, rel in zip(rankings_tfidf, relevant)],
        "rank_bm25": [rank_of_relevant(r, rel) for r, rel in zip(rankings_bm25, relevant)],
        "query": [q["query"] for q in queries],
    })
    # Int64 permite guardar enteros con huecos (consultas no encontradas)
    per_query["rank_tfidf"] = per_query["rank_tfidf"].astype("Int64")
    per_query["rank_bm25"] = per_query["rank_bm25"].astype("Int64")

    # Recall@10 por tipo de consulta
    print("\nRecall@10 por tipo de consulta")
    by_type = per_query.groupby("query_type").agg(
        consultas=("qid", "count"),
        tfidf=("rank_tfidf", lambda s: s.notna().mean()),
        bm25=("rank_bm25", lambda s: s.notna().mean()),
    )
    print(by_type.round(3))

    # Consultas en las que fallan los dos métodos
    failed = per_query[per_query["rank_tfidf"].isna() & per_query["rank_bm25"].isna()]
    print(f"\nConsultas que fallan con los dos métodos: {len(failed)}")
    for row in failed.itertuples():
        print(f"  {row.qid} [{row.query_type}] {row.query}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    per_query.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    print(f"\nGuardado {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
