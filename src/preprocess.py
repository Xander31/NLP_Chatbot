"""Preprocesado de la colección: spaCy + n-gramas (Phrases) + diccionario (Dictionary).

Tercer paso del pipeline. Adapta al español la sección 1.3 y 2.2-2.3 del
notebook de referencia (Text Vectorization I):

  1. prepare_data: limpieza → spaCy (nlp.pipe) → lemas de los tokens
     alfabéticos con POS en {NOUN, VERB, ADJ, PROPN}, sin stopwords.
     Adaptaciones al español (desviaciones justificadas del notebook):
       - Modelo es_core_news_md en lugar del pequeño: lematiza bastante mejor
         ("cebolla" y no "cebollo", "chorizo" y no "choracer").
       - El texto se pasa a minúsculas ANTES de spaCy: con mayúsculas spaCy
         cree que es un nombre propio y no lematiza ("Arepas" -> "arepas"),
         mientras que el usuario escribe en minúsculas ("arepas" -> "arepa").
       - Se quitan las tildes de los lemas (la ñ se conserva) para que una
         consulta sin tildes ("limon") case con "limón".
  2. Phrases(min_count=2, threshold=20): une pares de palabras que aparecen
     juntas con frecuencia ("aceite oliva" → "aceite_oliva").
  3. Dictionary + filter_extremes(no_below=4, no_above=0.80): vocabulario con un
     número por palabra, sin palabras rarísimas ni casi omnipresentes. Lo usa
     TF-IDF; BM25 trabaja con los tokens directamente (como en el notebook).

Las consultas deben pasar EXACTAMENTE por el mismo proceso: mismo spaCy, mismo
modelo de n-gramas y mismo diccionario. Para eso se guardan los modelos y se
expone preprocess_queries(), que usarán retrieval.py y generate_queries.py.

Entrada:  data/processed/chunks.jsonl (build_collection.py)
Salidas (en data/processed/, no versionadas):
  - tokens.jsonl     {"chunk_id": ..., "tokens": [...]} por fragmento, mismo orden
  - phrases.model    modelo de n-gramas de gensim
  - dictionary.dict  diccionario de gensim ya filtrado

Uso (desde la raíz del repo, con el entorno `.venv` activado):
    python src/preprocess.py
    python src/preprocess.py --n-process 4    # varios procesos de spaCy (más rápido)
"""
import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import spacy
from gensim.corpora import Dictionary
from gensim.models.phrases import Phrases

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
CHUNKS_PATH = PROCESSED / "chunks.jsonl"
TOKENS_PATH = PROCESSED / "tokens.jsonl"
PHRASES_PATH = PROCESSED / "phrases.model"
DICTIONARY_PATH = PROCESSED / "dictionary.dict"

# --- Parámetros (los del notebook) --------------------------------------------
SPACY_MODEL = "es_core_news_md"
valid_POS = {"NOUN", "VERB", "ADJ", "PROPN"}   # solo palabras con contenido
PHRASES_MIN_COUNT = 2     # mínimo de apariciones de un n-grama para considerarlo
PHRASES_THRESHOLD = 20    # puntuación mínima; más alto = menos n-gramas
NO_BELOW = 4              # quitar términos que aparecen en menos de 4 recetas
NO_ABOVE = 0.80           # quitar términos que aparecen en más del 80 % de recetas


def strip_accents(text):
    """Quita tildes (á é í ó ú) y diéresis (ü) pero CONSERVA la ñ.
    'limón' -> 'limon', 'pingüino' -> 'pinguino', 'piña' -> 'piña'.
    NFD separa cada letra de sus marcas (ó = o + ´); eliminamos solo la tilde
    aguda (U+0301) y la diéresis (U+0308) y volvemos a unir con NFC, de modo que
    la ñ (n + U+0303) queda intacta.
    (No confundir con strip_accents de build_collection.py, que sí quita la ñ.)"""
    nfd = unicodedata.normalize("NFD", text)
    return unicodedata.normalize("NFC", "".join(c for c in nfd if c not in "́̈"))


# Stopwords específicas del dominio, en forma de lema y sin tildes: palabras
# muy repetidas en las recetas que no distinguen unas de otras ("receta",
# "ingrediente") y adjetivos de los eslóganes. Lista revisable; NUNCA incluir
# ingredientes.
specific_stw = {"receta", "ingrediente",
                "facil", "rapido", "delicioso", "casero", "saludable", "tradicional"}

# Etiquetas que build_collection.py pone al inicio de cada línea del fragmento.
# No son contenido de la receta, así que se quitan antes de spaCy.
CHUNK_LABELS = re.compile(r"^(Receta|Ingredientes|Preparación): ", flags=re.MULTILINE)


def strip_labels(text):
    """'Receta: Tarta…\\nIngredientes: …' -> 'Tarta…\\n…'"""
    return CHUNK_LABELS.sub("", text)


def load_nlp():
    """Carga spaCy en español sin parser ni NER (no los necesitamos y así va
    mucho más rápido), igual que en el notebook."""
    return spacy.load(SPACY_MODEL, disable=["parser", "ner"])


def build_stopwords(nlp):
    """Stopwords generales de spaCy + las del dominio, todas sin tildes para
    compararlas con los lemas ya sin tildes."""
    return {strip_accents(w.lower()) for w in nlp.Defaults.stop_words} | specific_stw


def clean_text(text):
    """Equivalente a wrangle_text del notebook para nuestro corpus: no hay HTML
    ni contracciones; colapsamos el espacio en blanco y pasamos a minúsculas
    (ver la cabecera: así recetas y consultas se lematizan igual)."""
    return " ".join(text.split()).lower()


def prepare_data(texts, nlp, stopwords, batch_size=256, n_process=1):
    """Devuelve, para cada texto, la lista de sus lemas limpios.

    Para cada token: alfabético, con POS en valid_POS, lema en minúsculas y sin
    tildes, y que no sea stopword. Ej.:
      'Tarta de limón con merengue' -> ['tarta', 'limon', 'merengue']

    Los verbos con pronombre pegado reciben de spaCy un lema con espacio
    ('hacerlo' -> 'hacer el'). Se separa en palabras y cada una pasa por el
    filtro de stopwords: 'hacer el' -> ['hacer'].
    """
    texts = [clean_text(t) for t in texts]
    result = []
    for doc in nlp.pipe(texts, batch_size=batch_size, n_process=n_process):
        lemmas = []
        for token in doc:
            if not token.is_alpha or token.pos_ not in valid_POS:
                continue
            for part in strip_accents(token.lemma_.lower()).split():
                if part not in stopwords:
                    lemmas.append(part)
        result.append(lemmas)
    return result


def preprocess_queries(queries, nlp, stopwords, phrase_model):
    """Aplica a las consultas el mismo proceso que a los documentos:
    prepare_data + el MISMO modelo de n-gramas (phrase_model[tokens])."""
    return [phrase_model[tokens] for tokens in prepare_data(queries, nlp, stopwords)]


def load_pipeline():
    """Carga todo lo necesario para preprocesar consultas y vectorizar:
    (nlp, stopwords, phrase_model, dictionary)."""
    nlp = load_nlp()
    return (nlp, build_stopwords(nlp),
            Phrases.load(str(PHRASES_PATH)), Dictionary.load(str(DICTIONARY_PATH)))


def load_tokens(path=TOKENS_PATH):
    """Lee tokens.jsonl y devuelve (chunk_ids, corpus) en el orden de chunks.jsonl."""
    chunk_ids, corpus = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            chunk_ids.append(row["chunk_id"])
            corpus.append(row["tokens"])
    return chunk_ids, corpus


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n-process", type=int, default=1,
                        help="procesos de spaCy en paralelo (por defecto 1)")
    args = parser.parse_args()

    # Leemos los fragmentos en el orden de chunks.jsonl (el orden importa:
    # tokens.jsonl debe estar alineado con los chunk_id)
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]
    chunk_ids = [c["chunk_id"] for c in chunks]
    print(f"Fragmentos: {len(chunks):,}")

    # 1. Lematización con spaCy
    t0 = time.time()
    nlp = load_nlp()
    stopwords = build_stopwords(nlp)
    corpus = prepare_data([strip_labels(c["text"]) for c in chunks], nlp, stopwords,
                          n_process=args.n_process)
    n_tokens = sum(len(doc) for doc in corpus)
    print(f"spaCy: {time.time() - t0:.0f} s | tokens medios por receta: {n_tokens / len(corpus):.1f}")

    # 2. Detección de n-gramas. Como en el notebook, se entrena sobre el corpus
    # y después se reemplaza el corpus por su versión con n-gramas.
    phrase_model = Phrases(corpus, min_count=PHRASES_MIN_COUNT, threshold=PHRASES_THRESHOLD)
    corpus = [doc for doc in phrase_model[corpus]]
    ngram_counts = {}
    for doc in corpus:
        for tok in doc:
            if "_" in tok:
                ngram_counts[tok] = ngram_counts.get(tok, 0) + 1
    top_ngrams = sorted(ngram_counts.items(), key=lambda kv: -kv[1])[:15]
    print(f"n-gramas distintos en el corpus: {len(ngram_counts):,}")
    print("  más frecuentes:", ", ".join(f"{t} ({n})" for t, n in top_ngrams))

    # 3. Diccionario y filtrado de extremos
    D = Dictionary(corpus)
    n_before = len(D)
    # Términos que se eliminarán por aparecer en más del NO_ABOVE de las recetas
    too_common = sorted((D.dfs[i] / D.num_docs, D[i]) for i in D.keys()
                        if D.dfs[i] > NO_ABOVE * D.num_docs)
    D.filter_extremes(no_below=NO_BELOW, no_above=NO_ABOVE)
    print(f"Diccionario: {n_before:,} términos → {len(D):,} tras filter_extremes "
          f"(no_below={NO_BELOW}, no_above={NO_ABOVE})")
    print("  eliminados por demasiado frecuentes:",
          ", ".join(f"{t} ({p:.0%})" for p, t in reversed(too_common)) or "ninguno")

    # Guardar artefactos
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_PATH, "w", encoding="utf-8") as f:
        for cid, tokens in zip(chunk_ids, corpus):
            f.write(json.dumps({"chunk_id": cid, "tokens": tokens}, ensure_ascii=False) + "\n")
    phrase_model.save(str(PHRASES_PATH))
    D.save(str(DICTIONARY_PATH))
    print(f"Guardados {TOKENS_PATH.name}, {PHRASES_PATH.name} y {DICTIONARY_PATH.name} en {PROCESSED}")

    # Ejemplo para comprobar que todo encaja
    print("\nEjemplo:", chunks[0]["title"])
    print(" ", corpus[0][:30])


if __name__ == "__main__":
    main()
