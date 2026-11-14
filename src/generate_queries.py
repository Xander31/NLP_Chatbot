"""Genera las consultas de prueba (queries.jsonl) con un LLM local (Ollama).

Cuarto paso del pipeline. Sigue la sección 4.1 del notebook: consultas de tipo
*known-item* (cada consulta describe UNA receta concreta, que es la única
relevante), generadas con un LLM a partir de recetas elegidas al azar.

Flujo de trabajo (tres modos):

  1. GENERAR candidatas con un modelo:
       python src/generate_queries.py --model qwen3.5:9b-q4_K_M --n 10
     (por defecto guarda en data/processed/candidates_<modelo>.jsonl)
     Muestrea N_QUERIES recetas con SEED = 42, toma las --n primeras y pide al
     LLM una consulta para cada una. Cada receta tiene asignado uno de cinco
     tipos de consulta (búsqueda directa, por ingredientes, duda sobre la
     receta, restricción/técnica/ocasión y lista de la compra; ver
     QUERY_TYPES), repartidos por igual. Para cada consulta calcula métricas
     que ayudan a la revisión manual (ver compute_metrics) y marca las sospechosas.

  2. COMPARAR dos modelos sobre las mismas recetas:
       python src/generate_queries.py --compare results/query_model_selection/candidates_qwen3.5_9b-q4_K_M.jsonl results/query_model_selection/candidates_gemma4_12b-it-q4_K_M.jsonl

  3. FINALIZAR tras la revisión manual: en el fichero de candidatas se pone
     "discard": true en las consultas que copian el texto o son ambiguas (o se
     corrige "query" a mano) y se genera queries.jsonl:
       python src/generate_queries.py --finalize data/queries_candidates.jsonl

Requisitos: Ollama en marcha (`ollama serve`) y el modelo descargado
(`ollama pull <modelo>`). También deben existir data/processed/chunks.jsonl y
data/processed/tokens.jsonl (build_collection.py y preprocess.py).

Reproducibilidad: temperature=0, semilla fija, etiqueta exacta del modelo (con
cuantización) y se guarda el digest del modelo y la respuesta original del
LLM junto a cada consulta.
"""
import argparse
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

import requests

# preprocess.py está en la misma carpeta (src/), que Python añade al path al
# ejecutar `python src/generate_queries.py`
from preprocess import build_stopwords, load_nlp, load_tokens, prepare_data, strip_accents

ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = ROOT / "data" / "processed" / "chunks.jsonl"
QUERIES_PATH = ROOT / "queries.jsonl"

# --- Configuración -------------------------------------------------------------
SEED = 42
N_QUERIES = 100            # tamaño de la muestra completa de recetas
OLLAMA_URL = "http://localhost:11434"
# Modelo elegido (etiqueta exacta con cuantización, para que todos usemos el
# mismo). Se comparó con gemma4:12b-it-q4_K_M: ver results/query_model_selection/
MODEL = "qwen3.5:9b-q4_K_M"
LLM_OPTIONS = {
    "temperature": 0,      # sin aleatoriedad: misma receta -> misma consulta
    "seed": SEED,
    "num_ctx": 4096,       # una receta (<= 400 palabras) + el prompt caben de sobra
}

# Umbrales orientativos para marcar consultas a revisar (no descartan solas)
MIN_WORDS, MAX_WORDS = 8, 20
HIGH_OVERLAP = 0.75        # más del 75 % de los lemas de la consulta están en la receta
COPY_RUN = 4               # 4 o más palabras seguidas copiadas literalmente

# --- Tipos de consulta -----------------------------------------------------------
# Cada receta de la muestra recibe un tipo de consulta, inspirado en los casos de
# uso del chatbot que tienen UNA sola receta correcta (los que necesitan varias
# recetas —comparar, sustituciones— o ninguna —preguntas sin respuesta— no sirven
# para Recall@K/MRR con una única receta relevante; se dejan para el Hito 2).
# Cada tipo tiene su instrucción y un ejemplo con una receta inventada (no está
# en la colección muestreada).
QUERY_TYPES = {
    "busqueda": {
        "instruction": "Búsqueda directa: una frase corta sin verbo, como la que se escribe en un buscador.",
        "example": ('Bizcocho de yogur y limón',
                    'bizcocho esponjoso y cítrico para el desayuno medido con el envase del yogur'),
    },
    "ingredientes": {
        "instruction": ("Por ingredientes: pregunta qué se puede preparar con 2 o 3 ingredientes "
                        "característicos de la receta (evita los comunes como sal, aceite, agua o "
                        "cebolla), añadiendo si hace falta un rasgo del plato."),
        "example": ('Lentejas estofadas con chorizo',
                    '¿qué puedo cocinar con lentejas, chorizo y pimentón para una comida de cuchara?'),
    },
    "duda": {
        "instruction": ("Duda sobre la receta: pregunta por un detalle concreto que aparece en la "
                        "receta (tiempo, temperatura, cantidad o un paso), describiendo el plato "
                        "para que se sepa de cuál hablas."),
        "example": ('Pollo al horno con limón',
                    '¿cuánto tiempo hay que hornear el pollo marinado con cítricos y romero para que quede jugoso?'),
    },
    "restriccion": {
        "instruction": ("Restricción, técnica u ocasión: una petición que parte de una restricción "
                        "dietética (sin gluten, sin lactosa, vegetariano…), una técnica (al vapor, "
                        "olla exprés, sin horno…) o una ocasión (cena rápida, merienda, fiesta…) que "
                        "encaje con la receta, más uno o dos rasgos que la identifiquen."),
        "example": ('Brownie vegano de aguacate',
                    'busco un postre de chocolate sin huevos ni lácteos que lleve aguacate y quede muy jugoso'),
    },
    "compra": {
        "instruction": ("Lista de la compra: pregunta qué hay que comprar o qué ingredientes hacen "
                        "falta para preparar este plato (puedes indicar un número de personas), "
                        "describiéndolo para que se sepa de cuál hablas."),
        "example": ('Gazpacho andaluz',
                    '¿qué tengo que comprar para preparar la sopa fría de tomate típica del sur para seis personas?'),
    },
}

# Prompt: adaptación al español de la plantilla del notebook (sección 4.1). Para
# que las consultas no favorezcan artificialmente a TF-IDF/BM25 (que buscan
# palabras exactas): no copiar el título ni frases, describir con otras palabras.
PROMPT_TEMPLATE = """Eres una persona que usa un asistente de cocina para encontrar una receta concreta. Vas a ver la receta que quieres encontrar. Escribe lo que le dirías al asistente, en español natural y con entre 8 y 20 palabras.

Tipo de consulta: {instruction}

Reglas:
- No copies el título tal cual ni frases de la receta; puedes nombrar el tipo de plato con tus palabras.
- Usa tus propias palabras: sinónimos o descripciones del sabor, la textura, la técnica, el origen o la ocasión.
- No enumeres los ingredientes de la receta, salvo que el tipo de consulta lo pida.
- Aunque no des el título, la consulta debe permitir distinguir esta receta de otras parecidas: incluye uno o dos rasgos característicos.
- Usa signos de interrogación (¿?) solo si es una pregunta; una petición o una búsqueda no los lleva.
- Sin comillas.

Ejemplo de este tipo (de otra receta): receta "{example_title}" → {example_query}

Responde en JSON con un único campo "query".

Receta:
{text}"""


def build_prompt(recipe_text, query_type):
    t = QUERY_TYPES[query_type]
    example_title, example_query = t["example"]
    return PROMPT_TEMPLATE.format(instruction=t["instruction"], example_title=example_title,
                                  example_query=example_query, text=recipe_text)


def assign_query_types(n_total=N_QUERIES):
    """Reparte los tipos por igual (20 de cada en 100) con la semilla fija.
    Se hace por bloques de 5 (una permutación aleatoria de los 5 tipos por
    bloque), de modo que cualquier prefijo múltiplo de 5 también está
    equilibrado: las 10 recetas de la comparación de modelos tienen 2 de cada."""
    keys = list(QUERY_TYPES)
    assert n_total % len(keys) == 0, "N_QUERIES debe ser múltiplo del número de tipos"
    rng = random.Random(SEED)
    types = []
    for _ in range(n_total // len(keys)):
        block = keys[:]
        rng.shuffle(block)
        types.extend(block)
    return types

# Formato de salida estructurada de Ollama: obliga a responder {"query": "..."}
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


# --- Datos ---------------------------------------------------------------------
def load_chunks(path=CHUNKS_PATH):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def sample_chunks(chunks, n):
    """Muestra fija de N_QUERIES recetas (SEED = 42); devuelve las n primeras.
    Así las 10 recetas de la comparación de modelos son las 10 primeras de la
    muestra definitiva de 100."""
    sample = random.Random(SEED).sample(chunks, N_QUERIES)
    return sample[:n]


# --- Llamadas a Ollama ---------------------------------------------------------
def model_digest(model):
    """Huella (digest) del modelo descargado, para dejar constancia de la versión exacta."""
    tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10).json()
    for m in tags.get("models", []):
        if m["name"] == model or m["model"] == model:
            return m["digest"]
    raise SystemExit(f"El modelo {model} no está descargado. Ejecuta: ollama pull {model}")


def ask_llm(model, recipe_text, query_type):
    """Pide al LLM una consulta del tipo indicado para una receta.
    Devuelve (consulta, respuesta en bruto).

    'think': False desactiva el modo de razonamiento de los modelos que lo
    tienen (Qwen 3.5, Gemma 4): no lo necesitamos y multiplica el tiempo. Si un
    modelo no admite ese parámetro, se repite la petición sin él.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(recipe_text, query_type)}],
        "stream": False,
        "think": False,
        "format": RESPONSE_SCHEMA,
        "options": LLM_OPTIONS,
    }
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    if r.status_code == 400 and "think" in r.text:
        payload.pop("think")
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    r.raise_for_status()
    raw = r.json()["message"]["content"]
    try:
        query = json.loads(raw)["query"]
    except (json.JSONDecodeError, KeyError):
        query = raw   # respuesta mal formada: se guarda tal cual y se marcará al revisar
    return " ".join(query.strip().strip('"«»').split()), raw


# --- Métricas para la revisión manual ------------------------------------------
def words_for_copy_check(text):
    """Palabras en minúsculas y sin tildes, sin puntuación (para detectar copias literales)."""
    return re.findall(r"\w+", strip_accents(text.lower()))


def longest_copied_run(query, recipe_text):
    """Longitud de la secuencia más larga de palabras seguidas que la consulta
    copia literalmente de la receta (p. ej. 'aceite de oliva virgen extra' = 5)."""
    q, r = words_for_copy_check(query), words_for_copy_check(recipe_text)
    best = 0
    for n in range(1, len(q) + 1):
        recipe_ngrams = {tuple(r[i:i + n]) for i in range(len(r) - n + 1)}
        if any(tuple(q[i:i + n]) in recipe_ngrams for i in range(len(q) - n + 1)):
            best = n
        else:
            break   # si no hay ninguna secuencia de n palabras, tampoco de n+1
    return best


def compute_metrics(query, recipe_text, recipe_lemmas, nlp, stopwords):
    """Métricas de cada consulta:
    - n_words: número de palabras (se pide entre 8 y 20).
    - lemma_overlap: % de lemas de la consulta que aparecen en la receta (la
      métrica automática prevista en CLAUDE.md). Muy alto = copia vocabulario,
      lo que favorece artificialmente a TF-IDF/BM25.
    - longest_copied: palabras seguidas copiadas literalmente de la receta.
    - flags: avisos para la revisión manual.
    """
    q_lemmas = set(prepare_data([query], nlp, stopwords)[0])
    overlap = len(q_lemmas & recipe_lemmas) / len(q_lemmas) if q_lemmas else 0.0
    n_words = len(query.split())
    copied = longest_copied_run(query, recipe_text)
    flags = []
    if not MIN_WORDS <= n_words <= MAX_WORDS:
        flags.append("longitud")
    if overlap > HIGH_OVERLAP:
        flags.append("solapamiento_alto")
    if copied >= COPY_RUN:
        flags.append("copia_literal")
    return {"n_words": n_words, "lemma_overlap": round(overlap, 3),
            "longest_copied": copied, "flags": flags}


# --- Modos ---------------------------------------------------------------------
def summarize(rows, label=""):
    """Resumen agregado de un fichero de candidatas."""
    ov = [r["lemma_overlap"] for r in rows]
    print(f"\n== {label or rows[0]['model']} ({len(rows)} consultas)")
    print(f"  solapamiento de lemas: medio {statistics.mean(ov):.0%} | mediana {statistics.median(ov):.0%}")
    print(f"  longitud {MIN_WORDS}-{MAX_WORDS} palabras: {sum(MIN_WORDS <= r['n_words'] <= MAX_WORDS for r in rows)}/{len(rows)}")
    print(f"  con copia literal (>= {COPY_RUN} palabras): {sum('copia_literal' in r['flags'] for r in rows)}/{len(rows)}")
    print(f"  marcadas para revisar: {sum(bool(r['flags']) for r in rows)}/{len(rows)}")
    print(f"  segundos por consulta: {statistics.mean(r['seconds'] for r in rows):.1f}")
    print("  solapamiento medio por tipo: " + " | ".join(
        f"{t} {statistics.mean(r['lemma_overlap'] for r in rows if r['query_type'] == t):.0%}"
        for t in QUERY_TYPES if any(r["query_type"] == t for r in rows)))


def generate(model, n, output):
    chunks = load_chunks()
    sample = sample_chunks(chunks, n)
    query_types = assign_query_types()[:n]
    chunk_ids, corpus = load_tokens()
    # Lemas de cada receta (los n-gramas 'aceite_oliva' se separan en palabras)
    lemmas_by_chunk = {cid: {w for tok in toks for w in tok.split("_")}
                       for cid, toks in zip(chunk_ids, corpus)}
    nlp = load_nlp()
    stopwords = build_stopwords(nlp)
    digest = model_digest(model)

    print(f"Modelo: {model} ({digest[:12]}) | {n} recetas")
    rows = []
    for i, (chunk, query_type) in enumerate(zip(sample, query_types), start=1):
        t0 = time.time()
        query, raw = ask_llm(model, chunk["text"], query_type)
        seconds = round(time.time() - t0, 1)
        metrics = compute_metrics(query, chunk["text"], lemmas_by_chunk[chunk["chunk_id"]],
                                  nlp, stopwords)
        rows.append({
            "qid": f"q{i:03d}",
            "doc_id": chunk["doc_id"],
            "chunk_id": chunk["chunk_id"],
            "title": chunk["title"],
            "query_type": query_type,
            "query": query,
            **metrics,
            "discard": False,            # a rellenar en la revisión manual
            "model": model,
            "model_digest": digest,
            "options": LLM_OPTIONS,
            "raw_response": raw,
            "seconds": seconds,
        })
        flag_txt = f"  [{', '.join(metrics['flags'])}]" if metrics["flags"] else ""
        print(f"{i:3d}/{n} ({seconds}s) [{query_type}] {chunk['title'][:50]!r}\n      → {query}{flag_txt}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summarize(rows)
    print(f"\nGuardado en {output}")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def compare(path_a, path_b):
    """Muestra, receta a receta, las consultas de dos modelos y sus métricas."""
    a, b = read_jsonl(path_a), read_jsonl(path_b)
    by_chunk_b = {r["chunk_id"]: r for r in b}
    for ra in a:
        rb = by_chunk_b.get(ra["chunk_id"])
        if rb is None:
            continue
        print(f"\n{ra['qid']} · [{ra['query_type']}] {ra['title']}")
        for r in (ra, rb):
            flags = f" [{', '.join(r['flags'])}]" if r["flags"] else ""
            print(f"  {r['model']:>22}: {r['query']}")
            print(f"  {'':>22}  solapamiento {r['lemma_overlap']:.0%} · copia {r['longest_copied']} · {r['n_words']} palabras{flags}")
    summarize(a)
    summarize(b)


def finalize(path):
    """Escribe queries.jsonl con las candidatas no descartadas. Formato de
    CLAUDE.md más el campo query_type, para poder analizar los resultados por
    tipo de consulta."""
    rows = read_jsonl(path)
    kept = [r for r in rows if not r.get("discard")]
    with open(QUERIES_PATH, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps({"qid": r["qid"], "query": r["query"],
                                "relevant_ids": [r["doc_id"]],
                                "source_chunk": r["chunk_id"],
                                "query_type": r["query_type"]}, ensure_ascii=False) + "\n")
    print(f"{len(kept)} consultas escritas en {QUERIES_PATH} ({len(rows) - len(kept)} descartadas)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--model", help=f"modelo de Ollama (el elegido es {MODEL})")
    mode.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"),
                      help="comparar dos ficheros de candidatas")
    mode.add_argument("--finalize", type=Path, metavar="CANDIDATAS",
                      help="generar queries.jsonl a partir de las candidatas revisadas")
    parser.add_argument("--n", type=int, default=N_QUERIES,
                        help=f"número de recetas (por defecto {N_QUERIES})")
    parser.add_argument("--output", type=Path,
                        help="fichero de candidatas (por defecto data/processed/candidates_<modelo>.jsonl)")
    args = parser.parse_args()

    if args.compare:
        compare(*args.compare)
    elif args.finalize:
        finalize(args.finalize)
    else:
        if not 1 <= args.n <= N_QUERIES:
            sys.exit(f"--n debe estar entre 1 y {N_QUERIES}")
        safe_name = re.sub(r"[^\w.-]", "_", args.model)
        output = args.output or ROOT / "data" / "processed" / f"candidates_{safe_name}.jsonl"
        generate(args.model, args.n, output)


if __name__ == "__main__":
    main()
