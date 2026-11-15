# Hito 1: baseline de recuperación

Chatbot de recetas de cocina en español. Notebook ejecutado: [`notebooks/Milestone_1.ipynb`](notebooks/Milestone_1.ipynb). Consultas: [`queries.jsonl`](queries.jsonl).

## Qué se ha hecho

- **Corpus:** [`somosnlp/recetas-cocina`](https://huggingface.co/datasets/somosnlp/recetas-cocina). De 28.238 recetas nos quedamos con 17.505, después de quitar las incompletas, las repetidas y las de más de 400 palabras.
- **Unidad de indexación:** cada receta es un fragmento. El 90 % de las recetas no supera las 400 palabras, el límite superior recomendado, así que no hizo falta trocear.
- **Preprocesado:** spaCy (`es_core_news_md`) con lematización, filtro por categoría gramatical y stopwords. Luego n-gramas y diccionario con los parámetros del notebook de clase. Quedan 11.201 términos.
- **Consultas:** generamos 100 con `qwen3.5:9b` en local (Ollama), de cinco tipos distintos, pidiéndole que no copiara el texto de la receta. Después de revisarlas nos quedamos con 69.
- **Baselines:** TF-IDF con similitud coseno (gensim) y BM25 (`bm25s`, variante `lucene`, `k1 = 1.5`, `b = 0.75`). Las consultas se preprocesan igual que las recetas.

## Resultados

| Método | Recall@5 | Recall@10 | MRR |
|---|---|---|---|
| TF-IDF | 0,710 | 0,797 | 0,597 |
| BM25 | 0,928 | 0,957 | 0,809 |

BM25 funciona bastante mejor que TF-IDF: acierta en la primera posición en 51 de las 69 consultas, y TF-IDF en 35. Probamos BM25 usando solo el vocabulario del diccionario y casi no baja (Recall@10 = 0,942), así que la diferencia está en la fórmula y no en las palabras que usa cada uno.

Las consultas de tipo duda y restricción, que describen la receta en vez de nombrarla, son las que más fallan: BM25 falla en 3 de esas 28 consultas y en ninguna de las otras 41, y TF-IDF en 9 frente a 5. Con 12–17 consultas por tipo no se puede sacar una conclusión firme, pero sí se ve una tendencia. Cambiar `k1` y `b` apenas mueve los resultados, por eso dejamos los valores de clase.

Los dos métodos fallan en 3 consultas:

- **q018** pide un postre «sin azúcar ni lácteos» y la receta habla de *edulcorante* y *light*.
- **q042** dice «setas» y «cremosa», y la receta dice *champiñones* y *nata*.
- **q077** pregunta cuánto «se fríen» los tomates. La receta dice «fríelos» y spaCy no lo lematiza bien, así que no coinciden.

## Problemas encontrados y decisiones de diseño

- **Consultas ambiguas.** Fue lo que más trabajo dio. De las 31 que descartamos, 30 describían un plato que tiene varias recetas válidas en la colección (por ejemplo, hay 9 recetas con pico de gallo en el título). Como solo contamos una receta como correcta, la métrica habría penalizado respuestas buenas. La otra preguntaba algo que la receta no dice. El detalle está en [`results/query_review/revision_consultas.md`](results/query_review/revision_consultas.md).
- **Títulos sin el nombre del plato.** Un 7 % eran frases tipo «¡Receta FÁCIL y RÁPIDA!». Los arreglamos sacando el nombre del plato de la URL.
- **spaCy en español.** El modelo pequeño lematizaba mal («cebolla» → `cebollo`) y pasamos al mediano. También ponemos todo en minúsculas antes de spaCy y quitamos las tildes para que recetas y consultas coincidan.
- **Limitaciones.** Son pocas consultas y las escribió un LLM viendo la receta: de media, el 68 % de los lemas de cada consulta aparecen en su receta. Eso favorece a TF-IDF y BM25, que se basan en coincidencias exactas de palabras, así que sus cifras probablemente son optimistas; habrá que tenerlo en cuenta al compararlos con los embeddings densos en el Hito 2. Además quedan recetas casi iguales que no detectamos como duplicadas.

## Siguiente paso

En el Hito 2 montaremos el sistema RAG sobre las mismas recetas: embeddings en una base de datos vectorial y un LLM que responda citando la receta. Lo compararemos con BM25 usando estas mismas consultas, fijándonos sobre todo en las de duda y restricción, que es donde el baseline falla más.

## Uso de herramientas de IA generativa

- **Qwen 3.5 y Gemma 4 (Ollama):** para generar las consultas de prueba y comparar qué modelo lo hacía mejor.
- **Claude:** como ayuda para programar y depurar el código. También hizo una primera revisión de las 100 consultas y una segunda de las descartadas; el grupo revisó a mano muchas de ellas.
