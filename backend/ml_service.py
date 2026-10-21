"""
Acceso del sistema web al Machine Learning.

- Con ML_API_URL (produccion): todo se pide a la API de ML en
  Google Cloud (ml/servicio.py). Este servidor no carga el modelo.
- Sin ML_API_URL (desarrollo): se usa el modelo y los archivos
  locales de la carpeta ml/.
"""

import json
import os
import threading
import time
from pathlib import Path

import requests

from backend.repartidores import repartidores_en_turno


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

RUTA_MODELO = RAIZ_PROYECTO / "ml" / "models" / "modelo_final.joblib"
RUTA_METRICAS = RAIZ_PROYECTO / "ml" / "metrics" / "metricas.json"
RUTA_HISTORIAL = RAIZ_PROYECTO / "ml" / "metrics" / "historial_modelos.json"
RUTA_COMPARACION = RAIZ_PROYECTO / "ml" / "metrics" / "comparacion_modelos.json"

# (conexion, respuesta). La API de ML se apaga sin uso y su primer
# arranque tarda unos segundos.
TIEMPO_ESPERA = (5, 30)


def ml_remoto():

    return bool(os.getenv("ML_API_URL", "").strip())


def _url(ruta):

    return os.getenv("ML_API_URL", "").strip().rstrip("/") + ruta


def _cabeceras():

    return {"X-API-Key": os.getenv("ML_API_KEY", "")}


# La API de ML (Cloud Run) se apaga tras ~15 min sin uso y el primer
# pedido despues esperaba a que arrancara y cargara el modelo. El aviso
# de Cloud Scheduler que mantiene despierto este servidor (cada 10 min,
# GET /api/health) tambien la despierta, en segundo plano.
_ULTIMO_DESPERTAR = {"momento": 0.0}
DESPERTAR_CADA_SEG = 5 * 60


def despertar_ml():

    if not ml_remoto():
        return

    ahora = time.monotonic()

    if ahora - _ULTIMO_DESPERTAR["momento"] < DESPERTAR_CADA_SEG:
        return

    _ULTIMO_DESPERTAR["momento"] = ahora

    def tarea():
        try:
            requests.get(_url("/salud"), timeout=(5, 60))
        except Exception as error:
            print(f"[ML] No se pudo despertar la API de ML: {error}", flush=True)

    threading.Thread(target=tarea, daemon=True).start()


# =========================================================
# MODELO LOCAL (solo desarrollo)
# =========================================================

_CACHE_MODELO = {"mtime": None, "paquete": None}


def obtener_modelo():

    import joblib

    mtime = RUTA_MODELO.stat().st_mtime

    if _CACHE_MODELO["mtime"] != mtime:
        _CACHE_MODELO["paquete"] = joblib.load(RUTA_MODELO)
        _CACHE_MODELO["mtime"] = mtime

    return _CACHE_MODELO["paquete"]


# =========================================================
# PREDICCION
# =========================================================

def predecir_retraso(
    distancia_km,
    duracion_estimada_min,
    tiempo_preparacion_estimado_min,
    cantidad_items,
    pedidos_activos,
    fecha_pedido=None
):

    datos = {
        "distancia_km": float(distancia_km),
        "duracion_estimada_min": int(duracion_estimada_min),
        "tiempo_preparacion_estimado_min": int(tiempo_preparacion_estimado_min),
        "cantidad_items": int(cantidad_items),
        "pedidos_activos": int(pedidos_activos),
        "fecha_pedido": fecha_pedido.isoformat() if fecha_pedido else None,
        # Repartidores en turno (respaldo: REPARTIDORES_DISPONIBLES)
        "repartidores": repartidores_en_turno()
    }

    if ml_remoto():

        respuesta = requests.post(
            _url("/predecir"),
            json=datos,
            headers=_cabeceras(),
            timeout=TIEMPO_ESPERA
        )

        respuesta.raise_for_status()

        return respuesta.json()["prediccion"]

    from ml.prediccion import predecir

    return predecir(obtener_modelo(), **datos)


# =========================================================
# METRICAS, HISTORIAL Y ESTADO DEL ENTRENAMIENTO
# =========================================================

def obtener_datos_ml():
    """{metricas, historial, comparacion, estado}"""

    if ml_remoto():

        respuesta = requests.get(
            _url("/metricas"),
            headers=_cabeceras(),
            timeout=TIEMPO_ESPERA
        )

        respuesta.raise_for_status()

        datos = respuesta.json()

        # El reentrenamiento automatico es configuracion de este
        # servidor (lo dispara al entregar un pedido), no de la API.
        from backend.ml_reentrenamiento import (
            reentrenamiento_automatico_activo
        )

        datos.setdefault("estado", {})["automatico"] = (
            reentrenamiento_automatico_activo()
        )

        return datos

    from backend.ml_reentrenamiento import leer_estado

    def leer(ruta, defecto):
        return (
            json.loads(ruta.read_text(encoding="utf-8"))
            if ruta.exists()
            else defecto
        )

    estado = leer_estado()
    estado["donde"] = "Equipo local"

    return {
        "metricas": leer(RUTA_METRICAS, None),
        "historial": leer(RUTA_HISTORIAL, []),
        "comparacion": leer(RUTA_COMPARACION, None),
        "estado": estado
    }


def solicitar_reentrenamiento(origen):
    """Pide a la API de ML que entrene. Devuelve (codigo_http, json)."""

    respuesta = requests.post(
        _url("/reentrenar"),
        json={"origen": origen},
        headers=_cabeceras(),
        timeout=TIEMPO_ESPERA
    )

    return respuesta.status_code, respuesta.json()
