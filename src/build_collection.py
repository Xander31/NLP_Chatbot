"""Construye la colección de trabajo (data/processed/chunks.jsonl) a partir del CSV original.

Segundo paso del pipeline. Lee data/dataset.csv (generado por download.py) y
escribe un fichero JSONL con una receta por línea. Ese fichero es la colección
sobre la que se indexa (TF-IDF, BM25 y, en el Hito 2, embeddings), de la que se
muestrean las consultas de prueba y a cuyos doc_id apuntan los relevant_ids.

Pasos:
  1. Eliminar filas con title, ingredients o steps nulos
     (quita todas las recetas de recetas.com, que no tienen título).
  2. Deduplicar por (ingredients, steps): misma receta publicada varias veces.
  3. Conservar las recetas con <= 400 palabras (ingredients + steps), el límite
     superior del tamaño de fragmento recomendado (200-400 palabras). Así cada
     receta entera es un único fragmento y no hay que trocear nada.
  4. Limpiar los espacios en blanco y corregir los títulos genéricos
     ("¡Receta FÁCIL y RÁPIDA!") con el nombre del plato extraído de la URL.
  5. Asignar doc_id / chunk_id y escribir un fragmento por receta.

Resultado esperado: 28.238 → 22.640 → 19.410 → 17.505 recetas, con 1.238
títulos corregidos. La salida es determinista: cada ejecución produce el mismo
fichero (mismo SHA-256).

Uso (desde la raíz del repo, con el entorno `.venv` activado):
    python src/build_collection.py
    python src/build_collection.py --input data/dataset.csv --output data/processed/chunks.jsonl

Formato de cada línea de chunks.jsonl:
    {"doc_id": "doc_00001", "chunk_id": "doc_00001_c00",
     "title": "...", "original_title": "...", "url": "...",
     "text": "Receta: ...\\nIngredientes: ...\\nPreparación: ..."}
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

# Rutas relativas a la raíz del repo (este fichero está en src/)
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "dataset.csv"
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "chunks.jsonl"

# Máximo de palabras (ingredients + steps) para que la receta sea un único fragmento
MAX_WORDS = 400

# --- Listas para detectar títulos genéricos -----------------------------------
# Se escriben sin tildes porque se comparan con texto al que ya se le han quitado.
# Palabras vacías: no sirven para saber si el título nombra el plato.
TITLE_STOPWORDS = {"de", "del", "la", "el", "los", "las", "y", "con", "en", "a", "al",
                   "para", "sin", "un", "una", "receta", "recetas"}
# Adjetivos típicos de los eslóganes ("fácil y rápida", "casera"...). Se quitan
# también del slug: si no, un slug como "requeson-casero-facil" "coincidiría"
# con el título "Receta Fácil y Rápida" por la palabra "facil".
GENERIC_WORDS = {"facil", "faciles", "rapida", "rapido", "rapidas", "rapidos",
                 "deliciosa", "delicioso", "saludable", "tradicional", "casera", "casero",
                 "paso", "muy", "original", "sencilla", "sencillo", "economica",
                 "economico", "rica", "rico"}


def clean_whitespace(text):
    """Colapsa todo el espacio en blanco (\\r\\n, \\n, \\xa0, espacios múltiples)
    en un único espacio. str.split() sin argumentos ya trata \\xa0 como espacio."""
    return " ".join(text.split())


def strip_accents(text):
    """Quita tildes, diéresis y también la virgulilla de la ñ:
    'Lacón' -> 'Lacon', 'piña' -> 'pina'.
    NFD separa cada letra de su tilde (á = a + ´) y luego descartamos las tildes
    (caracteres de la categoría Unicode 'Mn').

    Convertir la ñ en n es intencionado: solo se usa para comparar con las URL,
    que no tienen ñ. NO reutilizar en el preprocesado (src/preprocess.py), donde
    la ñ debe conservarse."""
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def content_words(text):
    """Devuelve el conjunto de palabras significativas de un texto: en minúsculas,
    sin tildes, de 3 o más letras y sin stopwords ni adjetivos genéricos.
    Ej.: '¡Receta FÁCIL de Canelones!' -> {'canelones'}"""
    words = re.findall(r"[a-z]+", strip_accents(text.lower()))
    return {w for w in words
            if len(w) > 2 and w not in TITLE_STOPWORDS and w not in GENERIC_WORDS}


def slug_from_url(url):
    """Extrae el nombre del plato del último segmento de la URL.
    '.../receta-de-empanada-calabresa-76474.html' -> 'empanada calabresa'
    '.../recetas/hamburguesa-tilapia-salsa-pepinillos' -> 'hamburguesa tilapia salsa pepinillos'"""
    slug = url.rstrip("/").rsplit("/", 1)[-1]   # último segmento de la URL
    slug = re.sub(r"\.html?$", "", slug)         # quita la extensión .html
    slug = re.sub(r"-\d+$", "", slug)            # quita el identificador numérico final
    slug = re.sub(r"^receta-de-", "", slug)      # quita el prefijo de recetasgratis
    return slug.replace("-", " ").strip()


def restore_accents(slug, body):
    """Las URL no llevan tildes ni eñes ('lacon', 'bunuelos'). Para cada palabra
    del slug buscamos en el texto de la propia receta una palabra que sin tildes
    sea igual y usamos esa forma: 'lacon cocido' -> 'lacón cocido'.
    Si la palabra no aparece en la receta, se queda tal cual."""
    accented = {}
    for word in re.findall(r"\w+", body.lower()):
        # setdefault: si hay varias formas, nos quedamos con la primera que aparece
        accented.setdefault(strip_accents(word), word)
    return " ".join(accented.get(w, w) for w in slug.split())


def fix_title(title, url, body):
    """Corrige los títulos que no nombran el plato.

    Un título es genérico si no comparte ninguna palabra significativa con el
    slug de la URL. En ese caso el nuevo título es
    '{Nombre del plato} ({título original})', p. ej.
    'Canelones de ricota (¡Listos en 30 minutos!)'. Se conserva el título
    original entre paréntesis porque a veces aporta información (ingredientes,
    sinónimos del plato).

    Devuelve (título, True si se ha corregido).
    """
    slug = slug_from_url(url)
    slug_words = content_words(slug)
    # Si el slug no tiene palabras útiles no podemos sacar el plato de ahí;
    # si título y slug comparten alguna palabra, el título ya nombra el plato.
    if not slug_words or content_words(title) & slug_words:
        return title, False
    dish = restore_accents(slug, body)
    dish = dish[0].upper() + dish[1:]   # primera letra en mayúscula
    return f"{dish} ({title})", True


def load_and_filter(path):
    """Lee el CSV y aplica los pasos 1-3 del filtrado, mostrando cuántas
    recetas quedan tras cada uno."""
    # pandas lee las celdas vacías como NaN, que es lo que elimina dropna
    df = pd.read_csv(path)
    n_raw = len(df)

    # Paso 1: sin título, ingredientes o pasos no hay receta útil
    df = df.dropna(subset=["title", "ingredients", "steps"])
    n_notnull = len(df)

    # Paso 2: misma receta (mismos ingredientes y pasos) repetida; nos quedamos
    # con la primera aparición para mantener un orden estable
    df = df.drop_duplicates(subset=["ingredients", "steps"], keep="first")
    n_dedup = len(df)

    # Paso 3: contamos palabras separando por espacios y filtramos.
    # reset_index deja el índice como 0, 1, 2... en el orden del CSV, que es
    # el orden en que se asignan los doc_id.
    n_words = (df["ingredients"] + " " + df["steps"]).str.split().str.len()
    df = df[n_words <= MAX_WORDS].reset_index(drop=True)

    print(f"CSV original:          {n_raw:>6,}")
    print(f"Sin nulos:             {n_notnull:>6,}")
    print(f"Deduplicado:           {n_dedup:>6,}")
    print(f"<= {MAX_WORDS} palabras:       {len(df):>6,} ({len(df) / n_dedup:.1%})")
    return df


def build_chunks(df):
    """Aplica los pasos 4-5: limpia cada receta, corrige su título si hace
    falta y la convierte en un fragmento con sus identificadores."""
    chunks, n_fixed = [], 0
    for i, row in enumerate(df.itertuples(index=False), start=1):
        # Paso 4: limpieza de espacios en cada campo
        original_title = clean_whitespace(row.title)
        ingredients = clean_whitespace(row.ingredients)
        steps = clean_whitespace(row.steps)
        # El texto de la receta se usa para recuperar las tildes del slug
        title, fixed = fix_title(original_title, row.url, ingredients + " " + steps)
        n_fixed += fixed

        # Paso 5: identificadores. Cada receta es un único fragmento (_c00);
        # el sufijo existe para que el formato valga si en el futuro se trocea.
        doc_id = f"doc_{i:05d}"
        chunks.append({
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}_c00",
            "title": title,                    # título corregido (el que se indexa y se cita)
            "original_title": original_title,  # título del dataset, sin modificar
            "url": row.url,
            "text": f"Receta: {title}\nIngredientes: {ingredients}\nPreparación: {steps}",
        })
    print(f"Títulos corregidos:    {n_fixed:>6,} ({n_fixed / len(chunks):.1%})")
    return chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="CSV original (por defecto data/dataset.csv)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="fichero de salida (por defecto data/processed/chunks.jsonl)")
    args = parser.parse_args()

    chunks = build_chunks(load_and_filter(args.input))

    # Un objeto JSON por línea (JSONL). ensure_ascii=False guarda las tildes
    # tal cual en lugar de escaparlas como ó.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"Escritos {len(chunks):,} fragmentos en {args.output}")


if __name__ == "__main__":
    main()
