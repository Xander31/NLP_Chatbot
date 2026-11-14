# Chatbot de recetas con citas

Proyecto de PLN (Máster en IA Aplicada, UC3M). Chatbot que responde preguntas sobre una colección de **recetas de cocina en español** citando las recetas que respaldan cada respuesta.

- **Hito 1 (en curso):** baseline de recuperación con TF-IDF y BM25, evaluado con Recall@K y MRR.
- **Hito 2:** sistema RAG (embeddings densos + LLM que cita las recetas) comparado con el baseline, con la misma unidad de indexación.

Seguimos el notebook de referencia del profesor (*Text Vectorization I*, sección 4) siempre que es posible; las desviaciones se justifican aquí y en `MILESTONE_1.md`.

## Puesta en marcha

```bash
git clone <URL del repo> && cd NLP_chatbot
conda create -n pln python=3.12 -y      # Python 3.12: gensim y spaCy tienen wheels
conda activate pln
pip install -r requirements.txt         # incluye el modelo es_core_news_sm de spaCy
```

En VS Code, seleccionad el intérprete/kernel `pln`.

## Pipeline

Cada paso es un script reproducible que se ejecuta desde la raíz del repo:

| # | Script | Entrada → salida | Estado |
|---|---|---|---|
| 1 | `src/download.py` | Hugging Face → `data/dataset.csv` | ✅ |
| 2 | `src/build_collection.py` | `data/dataset.csv` → `data/processed/chunks.jsonl` | ✅ |
| 3 | `src/preprocess.py` | spaCy + n-gramas + diccionario | ⏳ |
| 4 | `src/generate_queries.py` | muestreo + LLM → `queries.jsonl` | ⏳ |
| 5 | `src/retrieval.py` | TF-IDF y BM25 | ⏳ |
| 6 | `src/evaluate.py` | Recall@K y MRR | ⏳ |

```bash
python src/download.py
python src/build_collection.py
```

## Pasos realizados y decisiones

### 1. Descarga del dataset
- **Fuente:** [`somosnlp/recetas-cocina`](https://huggingface.co/datasets/somosnlp/recetas-cocina) (licencia MIT), 28.238 recetas con columnas `title`, `url`, `ingredients`, `steps`, `uuid`.
- **Versión fijada** (commit `4946898c…`) y verificación con SHA-256: los `doc_id` dependen del orden de las filas, así que la descarga tiene que ser siempre idéntica.
- **El CSV no se sube al repo** (40 MB, se regenera con el script).

### 2. Filtrado
| Paso | Recetas | Motivo |
|---|---|---|
| CSV original | 28.238 | |
| Quitar `title`, `ingredients` o `steps` nulos | 22.640 | Elimina recetas.com entero (sin títulos) |
| Deduplicar por (`ingredients`, `steps`) | 19.410 | Misma receta publicada varias veces |
| Conservar ≤ 400 palabras | **17.505** | Límite superior del fragmento recomendado (200–400); conserva el 90,2 % |

No usamos la columna `uuid` (falta en 1.286 filas); asignamos IDs propios.

### 3. Unidad de indexación
- **Documento = receta = un único fragmento.** Con el filtro de 400 palabras no hace falta trocear.
- **IDs:** `doc_00001`… en el orden del CSV tras el filtrado; `chunk_id` = `{doc_id}_c00`.
- **Texto del fragmento:** `Receta: {title}` / `Ingredientes: …` / `Preparación: …`, con los espacios en blanco normalizados (`\r\n`, `\xa0`, espacios múltiples).
- **Salida:** `data/processed/chunks.jsonl` (campos `doc_id`, `chunk_id`, `title`, `original_title`, `url`, `text`). **Es la colección de trabajo** y **sí se sube al repo** una vez cerrada (~26 MB), porque es la referencia de los `relevant_ids` de las consultas. Su generación es determinista.

### 4. Títulos genéricos
- **Problema:** ~7 % de las recetas tienen como título un eslogan sin el nombre del plato (`"¡Receta FÁCIL y RÁPIDA!"`, `"¡Para chuparse los dedos!"`). El nombre real solo está en la URL (`receta-de-empanada-calabresa-76474.html`).
- **Detección:** el título es genérico si no comparte ninguna palabra significativa con la URL (sin tildes, sin stopwords y sin adjetivos genéricos como «fácil» o «casera»). Lo preferimos a una lista de eslóganes porque es imposible prever todos: la lista detectaba 515 casos y esta regla 1.238. Revisando una muestra de 60, todos eran genéricos o, como mucho, descripciones parciales.
- **Corrección:** `{Nombre del plato} ({título original})`, p. ej. `Canelones de ricota (¡Listos en 30 minutos!)`. Se conserva el eslogan porque a veces aporta información (ingredientes, sinónimos).
- **Tildes:** las URL no llevan tildes; se recuperan buscando cada palabra en el texto de la propia receta (`lacon` → `lacón`).
- **Resultado:** 1.238 títulos corregidos (1.236 de recetasgratis, 2 de Nestlé). El título original se guarda en `original_title`.

### 5. Preprocesado (en curso)
- **Tildes:** después de lematizar con spaCy se quitan las tildes (á é í ó ú) y la diéresis (ü) de cada lema, tanto en las recetas como en las consultas. Así una consulta escrita sin tildes (`tarta de limon`) encuentra recetas escritas con ellas (`limón`). Es una adaptación al español que el notebook no necesita, porque trabaja en inglés.

## Estructura del repositorio
```
data/
  dataset.csv          # CSV original (no se sube al repositorio)
  processed/
    chunks.jsonl       # colección de trabajo (se sube al repositorio)
src/                   # scripts del pipeline
notebooks/             # exploración y resultados
queries.jsonl          # consultas de prueba (Hito 1)
MILESTONE_1.md         # entregable del Hito 1
requirements.txt
```
