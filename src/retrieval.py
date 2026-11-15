"""Recuperación con TF-IDF (similitud coseno) y con BM25.

Quinto paso del pipeline. Sigue las secciones 4.2 y 4.3 del notebook de
referencia (Text Vectorization I):

  - TF-IDF: gensim (Dictionary -> TfidfModel -> SparseMatrixSimilarity). Los
    vectores tienen norma 1, así que la similitud coseno es un producto escalar.
  - BM25: librería bm25s, variante "lucene" (la que usa por defecto), con
    k1 = 1.5 y b = 0.75, como en el notebook.

Lo que se indexa son los fragmentos de chunks.jsonl (en nuestro caso, una
receta = un fragmento). El resultado se devuelve a nivel de documento: cada
documento se queda con la posición de su mejor fragmento y no se repite.

Las consultas se preprocesan igual que las recetas (preprocess_queries).

Uso (desde la raíz del repo):
    python src/retrieval.py "tortilla de bacalao con guindilla"
"""
import json
import sys

import bm25s
import numpy as np
from gensim.models import TfidfModel
from gensim.similarities import SparseMatrixSimilarity

# preprocess.py está en la misma carpeta (src/)
from preprocess import CHUNKS_PATH, load_pipeline, load_tokens, preprocess_queries

# Parámetros de BM25 (los del notebook)
BM25_K1 = 1.5
BM25_B = 0.75


def load_chunks():
    """Lee chunks.jsonl: una lista con un diccionario por fragmento."""
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def build_tfidf(corpus, D):
    """Crea el modelo TF-IDF y el índice de similitud a partir de los tokens."""
    corpus_bow = [D.doc2bow(doc) for doc in corpus]
    tfidf = TfidfModel(corpus_bow)
    index = SparseMatrixSimilarity(tfidf[corpus_bow], num_features=len(D))
    return tfidf, index


def build_bm25(corpus, k1=BM25_K1, b=BM25_B):
    """Crea el índice BM25 a partir de los tokens."""
    bm25 = bm25s.BM25(k1=k1, b=b)
    bm25.index(corpus, show_progress=False)
    return bm25


def retrieve_tfidf(tokens, D, tfidf, index, k=10):
    """Posiciones (filas de chunks.jsonl) de los k fragmentos más parecidos."""
    query_tfidf = tfidf[D.doc2bow(tokens)]   # mismo diccionario y mismos pesos IDF
    sims = index[query_tfidf]                # similitud coseno con cada fragmento
    return np.argsort(-sims)[:k].tolist()


def retrieve_bm25(tokens, bm25, k=10):
    """Posiciones (filas de chunks.jsonl) de los k fragmentos con más puntuación."""
    rows, scores = bm25.retrieve([tokens], k=k, show_progress=False)
    return rows[0].tolist()


def to_documents(rows, chunks, k=10):
    """Pasa de una lista de fragmentos a una lista de documentos.

    La lista de fragmentos ya viene ordenada de mejor a peor, así que la
    primera vez que aparece un documento es con su mejor fragmento. Las
    siguientes apariciones del mismo documento se descartan."""
    doc_ids = []
    for row in rows:
        doc_id = chunks[row]["doc_id"]
        if doc_id not in doc_ids:
            doc_ids.append(doc_id)
    return doc_ids[:k]


def main():
    if len(sys.argv) < 2:
        sys.exit('Uso: python src/retrieval.py "tu consulta"')
    query = " ".join(sys.argv[1:])

    chunks = load_chunks()
    chunk_ids, corpus = load_tokens()
    nlp, stopwords, phrase_model, D = load_pipeline()
    tfidf, index = build_tfidf(corpus, D)
    bm25 = build_bm25(corpus)
    titles = {c["doc_id"]: c["title"] for c in chunks}

    tokens = preprocess_queries([query], nlp, stopwords, phrase_model)[0]
    print("Consulta:", query)
    print("Tokens:  ", tokens)

    print("\nTF-IDF")
    rows = retrieve_tfidf(tokens, D, tfidf, index, k=5)
    for rank, doc_id in enumerate(to_documents(rows, chunks, k=5), 1):
        print(f"  {rank}. [{doc_id}] {titles[doc_id]}")

    print("\nBM25")
    rows = retrieve_bm25(tokens, bm25, k=5)
    for rank, doc_id in enumerate(to_documents(rows, chunks, k=5), 1):
        print(f"  {rank}. [{doc_id}] {titles[doc_id]}")


if __name__ == "__main__":
    main()
