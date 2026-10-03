"""
Reentrenamiento del modelo ML desde Flask.

- Manual: boton del dashboard (POST /api/pedidos/ml/reentrenar).
- Automatico: al marcar un pedido como ENTREGADO, en segundo
  plano, si REENTRENAMIENTO_AUTOMATICO esta activo (.env).

Solo puede haber un reentrenamiento a la vez. El bloqueo es un
archivo, asi funciona tambien con varios procesos (Gunicorn).
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

RUTA_SCRIPT = RAIZ_PROYECTO / "ml" / "reentrenar.py"

CARPETA_METRICAS = RAIZ_PROYECTO / "ml" / "metrics"

RUTA_BLOQUEO = CARPETA_METRICAS / ".reentrenando.lock"

RUTA_ESTADO = CARPETA_METRICAS / "estado_reentrenamiento.json"

# Sin este archivo (no se sube a Git) no se puede reentrenar:
# es el caso del servidor de produccion, que solo predice.
RUTA_DATASET_EXTERNO = (
    RAIZ_PROYECTO / "ml" / "data" / "externo" / "historical_data.csv"
)

# Si un bloqueo tiene mas de 15 min, el proceso que lo creo
# murio (p. ej. se reinicio Flask) y se descarta.
BLOQUEO_VENCIDO_SEG = 15 * 60

TIEMPO_LIMITE_SEG = 600

# Seguridad: maximo de entrenamientos seguidos en una ronda
# automatica (cada uno incluye los pedidos entregados mientras
# corria el anterior).
MAXIMO_RONDAS = 3

RESULTADOS = {
    0: (
        "PROMOVIDO",
        "Nueva versión entrenada y activada: mejora al modelo anterior."
    ),
    2: (
        "SIN_DATOS_NUEVOS",
        "No hay pedidos reales nuevos desde el último entrenamiento."
    ),
    3: (
        "NO_PROMOVIDO",
        "Se entrenó una nueva versión, pero no mejora al modelo vigente. "
        "Se mantiene el actual."
    )
}


def reentrenamiento_disponible():

    return RUTA_DATASET_EXTERNO.exists()


def reentrenamiento_automatico_activo():

    return reentrenamiento_disponible() and os.getenv(
        "REENTRENAMIENTO_AUTOMATICO",
        "true"
    ).strip().lower() in ("1", "true", "si", "sí", "yes")


# =========================================================
# BLOQUEO
# =========================================================

def _adquirir_bloqueo():

    if RUTA_BLOQUEO.exists():

        antiguedad = time.time() - RUTA_BLOQUEO.stat().st_mtime

        if antiguedad > BLOQUEO_VENCIDO_SEG:
            RUTA_BLOQUEO.unlink(missing_ok=True)

    try:

        descriptor = os.open(
            RUTA_BLOQUEO,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )

    except FileExistsError:
        return False

    os.write(descriptor, str(os.getpid()).encode())
    os.close(descriptor)

    return True


def _liberar_bloqueo():

    RUTA_BLOQUEO.unlink(missing_ok=True)


def en_curso():

    return (
        RUTA_BLOQUEO.exists()
        and time.time() - RUTA_BLOQUEO.stat().st_mtime
        <= BLOQUEO_VENCIDO_SEG
    )


# =========================================================
# ESTADO (visible en el dashboard)
# =========================================================

def _ahora():

    return datetime.now(timezone.utc).isoformat()


def leer_estado():

    estado = {}

    if RUTA_ESTADO.exists():

        try:
            estado = json.loads(
                RUTA_ESTADO.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            estado = {}

    estado["en_curso"] = en_curso()
    estado["automatico"] = reentrenamiento_automatico_activo()
    estado["disponible"] = reentrenamiento_disponible()

    return estado


def _guardar_estado(**datos):

    estado = leer_estado()
    estado.pop("en_curso", None)
    estado.pop("automatico", None)
    estado.pop("disponible", None)
    estado.update(datos)

    temporal = RUTA_ESTADO.with_suffix(".tmp")

    temporal.write_text(
        json.dumps(estado, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    temporal.replace(RUTA_ESTADO)


# =========================================================
# EJECUCION
# =========================================================

def _ejecutar_script():

    try:

        proceso = subprocess.run(
            [sys.executable, str(RUTA_SCRIPT)],
            cwd=RAIZ_PROYECTO,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            # 1 proceso: Flask ya ocupa memoria y el entrenamiento
            # en paralelo puede agotarla.
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "ML_N_JOBS": "1"
            },
            timeout=TIEMPO_LIMITE_SEG
        )

    except subprocess.TimeoutExpired:

        return {
            "codigo": None,
            "resultado": "ERROR",
            "mensaje": "El reentrenamiento superó el tiempo límite.",
            "detalle": ""
        }

    if proceso.returncode in RESULTADOS:

        resultado, mensaje = RESULTADOS[proceso.returncode]

        return {
            "codigo": proceso.returncode,
            "resultado": resultado,
            "mensaje": mensaje,
            "detalle": ""
        }

    # Sin las advertencias de librerias, que no son el error.
    lineas_error = [
        linea
        for linea in proceso.stderr.splitlines()
        if "warning" not in linea.lower()
    ]

    detalle = "\n".join(lineas_error[-40:])

    print(
        f"\n[REENTRENAMIENTO] Error (codigo {proceso.returncode}):\n"
        + detalle,
        flush=True
    )

    ultima_linea = (
        lineas_error[-1]
        if lineas_error
        else f"Código de salida {proceso.returncode}"
    )

    return {
        "codigo": proceso.returncode,
        "resultado": "ERROR",
        "mensaje": "Error durante el reentrenamiento: " + ultima_linea[-300:],
        "detalle": detalle
    }


def _ronda(origen):
    """Requiere el bloqueo adquirido. Entrena hasta que no queden
    pedidos reales nuevos (o hasta MAXIMO_RONDAS)."""

    # "en curso" se deduce del bloqueo; el estado solo se escribe
    # al terminar.
    inicio = _ahora()

    ultimo = None
    promovido = None

    try:

        for _ in range(MAXIMO_RONDAS):

            resultado = _ejecutar_script()

            # Un "sin datos nuevos" despues de entrenar no
            # reemplaza el resultado real del entrenamiento.
            if resultado["resultado"] != "SIN_DATOS_NUEVOS" or ultimo is None:
                ultimo = resultado

            if resultado["resultado"] == "PROMOVIDO":
                promovido = resultado

            if resultado["resultado"] in ("SIN_DATOS_NUEVOS", "ERROR"):
                break

        # Si alguna vuelta activo un modelo nuevo, eso es lo que
        # se informa (salvo que la ultima haya fallado).
        if promovido and ultimo["resultado"] != "ERROR":
            ultimo = promovido

    finally:

        # Una ronda automatica que no encontro pedidos nuevos (otra
        # ya los proceso) no reemplaza el resultado anterior.
        sin_cambios = (
            origen == "AUTOMATICO"
            and ultimo is not None
            and ultimo["resultado"] == "SIN_DATOS_NUEVOS"
        )

        if not sin_cambios:

            _guardar_estado(
                origen=origen,
                inicio=inicio,
                fin=_ahora(),
                resultado=ultimo["resultado"] if ultimo else "ERROR",
                mensaje=ultimo["mensaje"] if ultimo else "Error inesperado."
            )

        _liberar_bloqueo()

    return ultimo


def reentrenar_manual():
    """Reentrena y espera el resultado. None si ya hay uno en curso."""

    if not reentrenamiento_disponible():

        return {
            "codigo": None,
            "resultado": "ERROR",
            "mensaje": (
                "Este servidor no reentrena: falta el dataset DoorDash. "
                "El modelo se entrena en el equipo de desarrollo y se "
                "publica con git push."
            ),
            "detalle": ""
        }

    if not _adquirir_bloqueo():
        return None

    return _ronda("MANUAL")


def iniciar_reentrenamiento_automatico():
    """Lanza el reentrenamiento en segundo plano y vuelve enseguida."""

    def tarea():

        # Si hay uno en curso, esperar a que termine: el script
        # solo entrena si quedan pedidos reales sin usar.
        limite = time.time() + TIEMPO_LIMITE_SEG * MAXIMO_RONDAS

        while not _adquirir_bloqueo():

            if time.time() > limite:
                return

            time.sleep(5)

        _ronda("AUTOMATICO")

    threading.Thread(
        target=tarea,
        name="reentrenamiento-ml",
        daemon=True
    ).start()
