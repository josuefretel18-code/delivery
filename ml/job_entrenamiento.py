"""
Trabajo de entrenamiento del modelo.

En Google Cloud se ejecuta como Cloud Run Job (lo lanza la API de ML
al entregarse un pedido o desde el boton del dashboard). En
desarrollo lo lanza ml/servicio.py como subproceso.

    1. Descarga del almacen: dataset DoorDash, modelo, metricas e historial.
    2. Ejecuta ml/reentrenar.py (exportar + entrenar). Repite mientras
       haya pedidos reales nuevos (maximo 3 vueltas): asi incluye los
       pedidos entregados mientras entrenaba.
    3. Sube al almacen lo que cambio.
    4. Guarda el resultado en estado_reentrenamiento.json.

Variable ORIGEN: MANUAL | AUTOMATICO (por defecto AUTOMATICO).
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from ml import almacen


SCRIPT = RAIZ / "ml" / "reentrenar.py"

# Solo en modo local: evita dos entrenamientos a la vez. En Google
# Cloud lo controla la API de ML consultando las ejecuciones del job.
BLOQUEO_LOCAL = RAIZ / "ml" / "metrics" / ".reentrenando.lock"
BLOQUEO_VENCIDO_SEG = 15 * 60

MAXIMO_VUELTAS = 3
TIEMPO_LIMITE_SEG = 900

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


def ahora():

    return datetime.now(timezone.utc).isoformat()


# =========================================================
# BLOQUEO LOCAL
# =========================================================

def bloqueo_local_activo():

    return (
        BLOQUEO_LOCAL.exists()
        and time.time() - BLOQUEO_LOCAL.stat().st_mtime <= BLOQUEO_VENCIDO_SEG
    )


def adquirir_bloqueo_local():

    if BLOQUEO_LOCAL.exists() and not bloqueo_local_activo():
        BLOQUEO_LOCAL.unlink(missing_ok=True)

    try:
        descriptor = os.open(
            BLOQUEO_LOCAL,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )
    except FileExistsError:
        return False

    os.write(descriptor, str(os.getpid()).encode())
    os.close(descriptor)

    return True


# =========================================================
# ENTRENAMIENTO
# =========================================================

def descargar_entradas():

    if not almacen.descargar(almacen.DATASET_EXTERNO):

        raise FileNotFoundError(
            "Falta el dataset DoorDash en el almacen: "
            + almacen.DATASET_EXTERNO
        )

    # Pueden no existir en el primer entrenamiento.
    for nombre in (almacen.MODELO, almacen.METRICAS, almacen.HISTORIAL):
        almacen.descargar(nombre)


def subir_resultados(codigo):

    if codigo == 0:

        for nombre in (
            almacen.MODELO,
            almacen.METRICAS,
            almacen.COMPARACION,
            almacen.MATRIZ,
            almacen.DATASET_INFO,
            almacen.HISTORIAL
        ):
            almacen.subir(nombre)

        # Version anterior archivada por entrenar_modelo.py
        for archivo in (RAIZ / "ml" / "models").glob("modelo_v*.joblib"):
            almacen.subir(f"ml/models/{archivo.name}")

    elif codigo == 3:

        almacen.subir(almacen.HISTORIAL)
        almacen.subir(almacen.DATASET_INFO)


def ejecutar_vuelta():

    try:

        proceso = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=RAIZ,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=TIEMPO_LIMITE_SEG
        )

    except subprocess.TimeoutExpired:

        return {
            "codigo": None,
            "resultado": "ERROR",
            "mensaje": "El entrenamiento superó el tiempo límite."
        }

    # La salida queda en los logs (Cloud Logging en Google Cloud).
    print(proceso.stdout, flush=True)

    if proceso.returncode in RESULTADOS:

        resultado, mensaje = RESULTADOS[proceso.returncode]

        return {
            "codigo": proceso.returncode,
            "resultado": resultado,
            "mensaje": mensaje
        }

    lineas_error = [
        linea
        for linea in proceso.stderr.splitlines()
        if "warning" not in linea.lower()
    ]

    print("\n".join(lineas_error[-40:]), file=sys.stderr, flush=True)

    ultima = (
        lineas_error[-1]
        if lineas_error
        else f"Código de salida {proceso.returncode}"
    )

    return {
        "codigo": proceso.returncode,
        "resultado": "ERROR",
        "mensaje": "Error durante el reentrenamiento: " + ultima[-300:]
    }


def main():

    origen = os.getenv("ORIGEN", "AUTOMATICO").upper()
    inicio = ahora()

    local = not almacen.usa_nube()

    if local and not adquirir_bloqueo_local():
        print("Ya hay un entrenamiento en curso.")
        return

    ultimo = None
    promovido = None

    try:

        descargar_entradas()

        for _ in range(MAXIMO_VUELTAS):

            resultado = ejecutar_vuelta()

            if resultado["codigo"] in (0, 3):
                subir_resultados(resultado["codigo"])

            if resultado["resultado"] != "SIN_DATOS_NUEVOS" or ultimo is None:
                ultimo = resultado

            if resultado["resultado"] == "PROMOVIDO":
                promovido = resultado

            if resultado["resultado"] in ("SIN_DATOS_NUEVOS", "ERROR"):
                break

        if promovido and ultimo["resultado"] != "ERROR":
            ultimo = promovido

    except Exception as error:

        ultimo = {
            "codigo": None,
            "resultado": "ERROR",
            "mensaje": f"Error durante el reentrenamiento: {error}"
        }

        print(ultimo["mensaje"], file=sys.stderr, flush=True)

    finally:

        # Una vuelta automatica sin pedidos nuevos no reemplaza el
        # resultado anterior.
        sin_cambios = (
            origen == "AUTOMATICO"
            and ultimo is not None
            and ultimo["resultado"] == "SIN_DATOS_NUEVOS"
        )

        if not sin_cambios:

            almacen.escribir_json(almacen.ESTADO, {
                "origen": origen,
                "inicio": inicio,
                "fin": ahora(),
                "resultado": ultimo["resultado"] if ultimo else "ERROR",
                "mensaje": ultimo["mensaje"] if ultimo else "Error inesperado."
            })

        if local:
            BLOQUEO_LOCAL.unlink(missing_ok=True)

    print(f"\nRESULTADO: {ultimo['resultado'] if ultimo else 'ERROR'}", flush=True)


if __name__ == "__main__":
    main()
