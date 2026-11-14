"""Descarga el CSV original de somosnlp/recetas-cocina desde Hugging Face.

Primer paso del pipeline: descarga → colección → preprocesado → consultas →
recuperación → evaluación.

¿Por qué fijamos la versión?
    Los doc_id de la colección (doc_00001, doc_00002…) se asignan según el orden
    de las filas del CSV. Si el dataset cambiara en Hugging Face, los doc_id se
    desplazarían y los relevant_ids de queries.jsonl apuntarían a recetas
    equivocadas. Por eso descargamos siempre el mismo commit del repositorio y
    comprobamos con un hash (SHA-256) que el fichero es idéntico byte a byte.

Uso (desde la raíz del repo, con el entorno `pln` activado):
    python src/download.py                       # guarda en data/dataset.csv
    python src/download.py --output otra/ruta.csv
"""
import argparse
import hashlib
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

# --- Configuración del dataset ------------------------------------------------
REPO_ID = "somosnlp/recetas-cocina"   # repositorio en Hugging Face (licencia MIT)
REVISION = "4946898c01d02b2f0b4223c824db53ebf516e02f"  # commit fijado (último, 2023-04-23)
FILENAME = "dataset.csv"              # único fichero de datos del repositorio
# Huella del fichero correcto. Si la descarga no coincide, el script se detiene.
EXPECTED_SHA256 = "0eb18bf728118f2ad124662adb5c127956084e2cd4c15c4c698a5944c0aba609"

# Rutas relativas a la raíz del repo (este fichero está en src/)
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "dataset.csv"


def sha256(path):
    """Calcula el hash SHA-256 de un fichero leyéndolo por bloques de 1 MB
    (así no hace falta cargarlo entero en memoria)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="ruta donde guardar el CSV (por defecto data/dataset.csv)")
    args = parser.parse_args()

    # hf_hub_download guarda el fichero en la caché local de Hugging Face
    # (~/.cache/huggingface) y devuelve su ruta; si ya estaba descargado, no lo
    # vuelve a bajar.
    cached = hf_hub_download(repo_id=REPO_ID, filename=FILENAME,
                             repo_type="dataset", revision=REVISION)

    # Copiamos el fichero de la caché a la carpeta del proyecto
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, args.output)

    # Verificación: el fichero debe ser exactamente el esperado
    digest = sha256(args.output)
    print(f"Guardado en {args.output} ({args.output.stat().st_size:,} bytes)")
    print(f"SHA-256: {digest}")
    if EXPECTED_SHA256 and digest != EXPECTED_SHA256:
        raise SystemExit("El fichero descargado no coincide con el esperado.")


if __name__ == "__main__":
    main()
