# Chatbot de recetas con citas

Proyecto de PLN (Máster en IA Aplicada, UC3M): chatbot que responde preguntas sobre **recetas de cocina en español** citando las recetas en que se basa.

- **Hito 1 (hecho):** baseline de recuperación con TF-IDF y BM25, evaluado con Recall@K y MRR. Ver [`MILESTONE_1.md`](MILESTONE_1.md) y [`notebooks/Milestone_1.ipynb`](notebooks/Milestone_1.ipynb).
- **Hito 2:** RAG (embeddings densos + LLM que cita) comparado con el baseline, con la misma unidad de indexación.

Seguimos el notebook del profesor (*Text Vectorization I*, sección 4) siempre que es posible; las desviaciones se justifican abajo y en `MILESTONE_1.md`.

## Puesta en marcha
Con [uv](https://docs.astral.sh/uv/), desde la raíz del repo:
```bash
uv venv --python 3.12
uv pip install -r requirements.txt
.venv\Scripts\activate        # en Linux o macOS: source .venv/bin/activate
```
En VS Code hay que seleccionar el intérprete de `.venv`. Para volver a generar las consultas hace falta además [Ollama](https://ollama.com/download).

## Pipeline
| # | Script | Salida | Estado |
|---|---|---|---|
| 1 | `src/download.py` | `data/dataset.csv` | ✅ |
| 2 | `src/build_collection.py` | `data/processed/chunks.jsonl` | ✅ |
| 3 | `src/preprocess.py --n-process 4` | `tokens.jsonl`, `phrases.model`, `dictionary.dict` | ✅ |
| 4 | `src/generate_queries.py --model …` y luego `--finalize …` | `data/queries_candidates.jsonl` y `queries.jsonl` | ✅ |
| 5 | `src/retrieval.py "consulta"` | Búsqueda con TF-IDF y BM25 | ✅ |
| 6 | `src/evaluate.py` | Recall@K y MRR, `results/evaluation/per_query.csv` | ✅ |

Todos los scripts se ejecutan desde la raíz del repo y son deterministas.

## Decisiones

**1. Dataset.** [`somosnlp/recetas-cocina`](https://huggingface.co/datasets/somosnlp/recetas-cocina) (MIT), con la versión fijada y verificada por SHA-256 para que los `doc_id` sean reproducibles. El CSV no se sube al repo.

**2. Filtrado.** 28.238 recetas → sin nulos: 22.640 → sin duplicados (`ingredients`, `steps`): 19.410 → **≤ 400 palabras: 17.505** (90,2 %). 400 es el límite superior del fragmento recomendado (200–400).

**3. Unidad de indexación.** Una receta = un fragmento (`doc_00001_c00`), con el texto `Receta / Ingredientes / Preparación`. `chunks.jsonl` es la colección de trabajo y **se sube al repo**: es la referencia de los `relevant_ids`.

**4. Títulos genéricos.** 1.238 recetas (7 %) tenían como título un eslogan («¡Receta FÁCIL y RÁPIDA!»). Se detectan porque no comparten ninguna palabra con la URL, y se corrigen con el nombre del plato sacado de ella: `Canelones de ricota (¡Listos en 30 minutos!)`. El original se guarda en `original_title`.

**5. Preprocesado.** spaCy → n-gramas → diccionario, como el notebook, con estas adaptaciones al español:
- modelo `es_core_news_md` (el pequeño lematizaba mal: «cebolla» → `cebollo`);
- minúsculas antes de spaCy, para que «Arepas» y «arepas» den el mismo lema;
- sin tildes en los lemas, para que `limon` case con `limón`;
- se quitan las etiquetas del fragmento y se separan los verbos con pronombre (`hacer el` → `hacer`);
- stopwords de spaCy más una lista corta del dominio (nunca ingredientes).

Parámetros del notebook: `Phrases(min_count=2, threshold=20)` y `filter_extremes(no_below=4, no_above=0.80)`. Resultado: ~96 lemas por receta y un diccionario de 11.201 términos.

**6. Consultas de prueba.** Cada consulta describe una única receta relevante (como en el notebook), generada con un LLM local a partir de 100 recetas al azar (`SEED = 42`).
- **Modelo: `qwen3.5:9b-q4_K_M`** (Ollama). Lo comparamos con `gemma4:12b-it-q4_K_M` sobre las mismas 10 recetas: Qwen fue más preciso y específico (Gemma daba consultas vagas, como «guiso de legumbres con marisco») y más rápido (6,8 frente a 10,8 s por consulta), con un solapamiento similar (66 % frente a 60 %) y ninguna copia literal en ninguno de los dos. Resultados en [`results/query_model_selection/`](results/query_model_selection/).
- **Cinco tipos de consulta**, 20 de cada, basados en los casos de uso del chatbot: `busqueda` (frase sin verbo), `ingredientes`, `duda` sobre un detalle de la receta, `restriccion` (dieta, técnica u ocasión) y `compra`. Cada consulta guarda su tipo para analizar los resultados por tipo. Los casos con varias recetas correctas (comparar, sustituciones) o ninguna (preguntas sin respuesta) quedan para el Hito 2.
- **Para no favorecer a TF-IDF y BM25:** el prompt prohíbe copiar el título o frases de la receta y pide describir con otras palabras, manteniendo rasgos que identifiquen la receta.
- **Revisión** apoyada en métricas: % de lemas copiados, palabras seguidas copiadas y longitud. Las consultas vagas no saltan ningún aviso: hay que leerlas. Claude hizo una primera revisión de las 100 consultas y después revisamos a mano muchas de ellas.
- **Resultado de la revisión:** quedan **65** consultas en `queries.jsonl`. De las 35 descartadas, 34 son ambiguas (otra receta responde igual de bien) y 1 pregunta un dato que la receta no contiene; 2 de las ambiguas tienen además ese segundo problema. Detalle en [`results/query_review/revision_consultas.md`](results/query_review/revision_consultas.md).

**7. Recuperación y evaluación.** TF-IDF con similitud coseno (gensim) y BM25 (`bm25s`, variante `lucene`, `k1 = 1.5`, `b = 0.75`). La evaluación es a nivel de documento, sobre los 10 primeros resultados.

| Método | Recall@5 | Recall@10 | MRR |
|---|---|---|---|
| TF-IDF | 0,692 | 0,785 | 0,588 |
| BM25 | 0,923 | 0,954 | 0,805 |

## Estructura
```
data/
  dataset.csv              # CSV original (no se sube)
  processed/chunks.jsonl   # colección de trabajo (se sube)
  queries_candidates.jsonl # consultas generadas y revisadas (se sube)
results/                   # resultados que justifican decisiones
src/                       # scripts del pipeline
notebooks/Milestone_1.ipynb # todo el Hito 1 paso a paso, ejecutado
queries.jsonl              # consultas de prueba (entregable)
MILESTONE_1.md             # entregable del Hito 1
```
