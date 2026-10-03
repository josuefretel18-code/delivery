"""
API de Machine Learning de Kimbos (se despliega en Google Cloud Run).

El sistema web (Render) la consume por HTTPS:

    GET  /salud        estado del servicio y version del modelo (publico)
    POST /predecir     riesgo de retraso de un pedido
    GET  /metricas     metricas, matriz de confusion, historial y estado
    POST /reentrenar   lanza el entrenamiento (Cloud Run Job)

Las rutas, salvo /salud, exigen la cabecera X-API-Key = ML_API_KEY.

Variables de entorno:
    ML_API_KEY   clave compartida con el sistema web
    ML_BUCKET    bucket de Cloud Storage (sin el: archivos locales)
    ML_JOB       projects/<proyecto>/locations/<region>/jobs/<job>
"""

import hmac
import os
import subprocess
import sys
import threading
import time
from functools import wraps
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import joblib
from flask import Flask, jsonify, request

from ml import almacen
from ml.job_entrenamiento import bloqueo_local_activo
from ml.prediccion import predecir


app = Flask(__name__)


# =========================================================
# SEGURIDAD
# =========================================================

def requiere_clave(funcion):

    @wraps(funcion)
    def envoltura(*args, **kwargs):

        clave = os.getenv("ML_API_KEY", "")

        # Sin clave configurada solo se permite en desarrollo local.
        if not clave and almacen.usa_nube():
            return jsonify({"ok": False, "mensaje": "ML_API_KEY no configurada"}), 500

        recibida = request.headers.get("X-API-Key", "")

        if clave and not hmac.compare_digest(recibida, clave):
            return jsonify({"ok": False, "mensaje": "No autorizado"}), 401

        return funcion(*args, **kwargs)

    return envoltura


# =========================================================
# MODELO (se recarga cuando el job publica una version nueva)
# =========================================================

INTERVALO_REVISION_SEG = 30

_modelo = {"version": None, "paquete": None, "revisado": 0.0}
_bloqueo_modelo = threading.Lock()


def obtener_modelo():

    with _bloqueo_modelo:

        vencido = time.time() - _modelo["revisado"] > INTERVALO_REVISION_SEG

        if _modelo["paquete"] is None or vencido:

            version = almacen.version(almacen.MODELO)
            _modelo["revisado"] = time.time()

            if version is None:
                raise FileNotFoundError("No hay modelo publicado en el almacén.")

            if version != _modelo["version"]:

                almacen.descargar(almacen.MODELO)

                _modelo["paquete"] = joblib.load(
                    almacen.ruta_local(almacen.MODELO)
                )
                _modelo["version"] = version

        return _modelo["paquete"]


# =========================================================
# ENTRENAMIENTO (Cloud Run Job)
# =========================================================

# Tras lanzar el job, la ejecucion tarda unos segundos en aparecer
# en la API: durante ese margen se considera "en curso".
MARGEN_LANZAMIENTO_SEG = 60

_ultimo_lanzamiento = {"momento": 0.0}


def entrenamiento_en_curso():

    if time.time() - _ultimo_lanzamiento["momento"] < MARGEN_LANZAMIENTO_SEG:
        return True

    if not almacen.usa_nube():
        return bloqueo_local_activo()

    from google.cloud import run_v2

    ejecuciones = run_v2.ExecutionsClient().list_executions(
        parent=os.environ["ML_JOB"]
    )

    # Vienen de la mas reciente a la mas antigua.
    for indice, ejecucion in enumerate(ejecuciones):

        if not ejecucion.completion_time:
            return True

        if indice >= 4:
            break

    return False


def lanzar_entrenamiento(origen):

    if almacen.usa_nube():

        from google.cloud import run_v2

        Overrides = run_v2.RunJobRequest.Overrides

        run_v2.JobsClient().run_job(
            request=run_v2.RunJobRequest(
                name=os.environ["ML_JOB"],
                overrides=Overrides(
                    container_overrides=[
                        Overrides.ContainerOverride(
                            env=[run_v2.EnvVar(name="ORIGEN", value=origen)]
                        )
                    ]
                )
            )
        )

    else:

        subprocess.Popen(
            [sys.executable, str(RAIZ / "ml" / "job_entrenamiento.py")],
            cwd=RAIZ,
            env={**os.environ, "ORIGEN": origen, "ML_N_JOBS": "1"}
        )

    _ultimo_lanzamiento["momento"] = time.time()


# =========================================================
# RUTAS
# =========================================================

@app.get("/salud")
def salud():

    try:
        paquete = obtener_modelo()
        version = paquete["version"]
    except Exception as error:
        return jsonify({"ok": False, "mensaje": str(error)}), 503

    return jsonify({
        "ok": True,
        "servicio": "kimbos-ml",
        "modelo_version": version,
        "almacen": "Cloud Storage" if almacen.usa_nube() else "local"
    })


@app.post("/predecir")
@requiere_clave
def ruta_predecir():

    datos = request.get_json(silent=True) or {}

    obligatorios = (
        "distancia_km",
        "duracion_estimada_min",
        "tiempo_preparacion_estimado_min",
        "cantidad_items",
        "pedidos_activos"
    )

    faltantes = [campo for campo in obligatorios if datos.get(campo) is None]

    if faltantes:
        return jsonify({"ok": False, "mensaje": f"Faltan campos: {faltantes}"}), 400

    try:

        resultado = predecir(
            obtener_modelo(),
            distancia_km=datos["distancia_km"],
            duracion_estimada_min=datos["duracion_estimada_min"],
            tiempo_preparacion_estimado_min=datos["tiempo_preparacion_estimado_min"],
            cantidad_items=datos["cantidad_items"],
            pedidos_activos=datos["pedidos_activos"],
            fecha_pedido=datos.get("fecha_pedido"),
            repartidores=datos.get("repartidores")
        )

    except (TypeError, ValueError) as error:
        return jsonify({"ok": False, "mensaje": f"Datos no válidos: {error}"}), 400

    return jsonify({"ok": True, "prediccion": resultado})


@app.get("/metricas")
@requiere_clave
def ruta_metricas():

    estado = almacen.leer_json(almacen.ESTADO, {}) or {}

    estado["en_curso"] = entrenamiento_en_curso()
    estado["disponible"] = almacen.existe(almacen.DATASET_EXTERNO)
    estado["donde"] = (
        "Google Cloud (Cloud Run Job)"
        if almacen.usa_nube()
        else "Equipo local"
    )

    return jsonify({
        "ok": True,
        "metricas": almacen.leer_json(almacen.METRICAS),
        "historial": almacen.leer_json(almacen.HISTORIAL, []),
        "estado": estado
    })


@app.post("/reentrenar")
@requiere_clave
def ruta_reentrenar():

    datos = request.get_json(silent=True) or {}

    origen = str(datos.get("origen", "MANUAL")).upper()

    if origen not in ("MANUAL", "AUTOMATICO"):
        origen = "MANUAL"

    if not almacen.existe(almacen.DATASET_EXTERNO):
        return jsonify({
            "ok": False,
            "mensaje": "Falta el dataset DoorDash en el almacén."
        }), 500

    if entrenamiento_en_curso():
        return jsonify({
            "ok": False,
            "resultado": "EN_CURSO",
            "mensaje": "Ya hay un entrenamiento en curso."
        }), 409

    lanzar_entrenamiento(origen)

    return jsonify({
        "ok": True,
        "resultado": "INICIADO",
        "mensaje": (
            "Entrenamiento iniciado en Google Cloud. Tarda unos minutos."
            if almacen.usa_nube()
            else "Entrenamiento iniciado en el equipo local."
        )
    }), 202


if __name__ == "__main__":

    # Desarrollo local: python ml/servicio.py  (puerto 8000)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
