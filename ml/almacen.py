"""
Almacenamiento de los archivos del ML.

- En Google Cloud (variable ML_BUCKET definida): Cloud Storage.
- En desarrollo (sin ML_BUCKET): las carpetas locales del proyecto.

En el bucket cada archivo usa como nombre su ruta relativa en el
proyecto (ej. "ml/models/modelo_final.joblib"), asi se mantiene la
misma estructura en los dos casos.
"""

import json
import os
from pathlib import Path


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

MODELO = "ml/models/modelo_final.joblib"
METRICAS = "ml/metrics/metricas.json"
COMPARACION = "ml/metrics/comparacion_modelos.csv"
MATRIZ = "ml/metrics/matriz_confusion.png"
HISTORIAL = "ml/metrics/historial_modelos.json"
ESTADO = "ml/metrics/estado_reentrenamiento.json"
DATASET_INFO = "ml/data/dataset_info.json"
DATASET_EXTERNO = "ml/data/externo/historical_data.csv"


def bucket_nombre():

    return os.getenv("ML_BUCKET", "").strip()


def usa_nube():

    return bool(bucket_nombre())


_BUCKET = None


def _bucket():

    global _BUCKET

    if _BUCKET is None:

        from google.cloud import storage

        _BUCKET = storage.Client().bucket(bucket_nombre())

    return _BUCKET


def ruta_local(nombre):

    return RAIZ_PROYECTO / nombre


def existe(nombre):

    if usa_nube():
        return _bucket().blob(nombre).exists()

    return ruta_local(nombre).exists()


def version(nombre):
    """Identificador que cambia cuando cambia el archivo
    (generacion en Cloud Storage, fecha de modificacion en local).
    None si no existe."""

    if usa_nube():

        blob = _bucket().get_blob(nombre)

        return blob.generation if blob else None

    ruta = ruta_local(nombre)

    return ruta.stat().st_mtime if ruta.exists() else None


def descargar(nombre):
    """Trae el archivo del bucket a su ruta local. En modo local no
    hace nada. Devuelve True si el archivo queda disponible."""

    ruta = ruta_local(nombre)

    if usa_nube():

        blob = _bucket().blob(nombre)

        if not blob.exists():
            return False

        ruta.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(ruta))

    return ruta.exists()


def subir(nombre):
    """Sube la copia local al bucket. En modo local no hace nada."""

    if usa_nube():

        ruta = ruta_local(nombre)

        if ruta.exists():
            _bucket().blob(nombre).upload_from_filename(str(ruta))


def leer_json(nombre, defecto=None):

    if usa_nube():

        blob = _bucket().blob(nombre)

        if not blob.exists():
            return defecto

        return json.loads(blob.download_as_text(encoding="utf-8"))

    ruta = ruta_local(nombre)

    if not ruta.exists():
        return defecto

    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(nombre, datos):

    texto = json.dumps(datos, indent=4, ensure_ascii=False)

    if usa_nube():

        _bucket().blob(nombre).upload_from_string(
            texto,
            content_type="application/json"
        )

        return

    ruta = ruta_local(nombre)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(texto, encoding="utf-8")
    temporal.replace(ruta)
