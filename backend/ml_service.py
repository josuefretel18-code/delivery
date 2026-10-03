from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd

from ml.variables import (
    es_hora_pico,
    es_fin_semana,
    repartidores_disponibles,
    carga_repartidor
)


# =========================================================
# CONFIGURACION
# =========================================================

RAIZ_PROYECTO = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

RUTA_MODELO = (
    RAIZ_PROYECTO
    / "ml"
    / "models"
    / "modelo_final.joblib"
)

TZ_PERU = ZoneInfo(
    "America/Lima"
)


# =========================================================
# CARGAR MODELO
# Se carga al iniciar y se vuelve a cargar solo si el
# archivo cambia (por ejemplo, despues de reentrenar).
# =========================================================

if not RUTA_MODELO.exists():

    raise FileNotFoundError(
        f"No existe el modelo ML: "
        f"{RUTA_MODELO}"
    )


_CACHE_MODELO = {
    "mtime": None,
    "paquete": None
}


def obtener_modelo():

    mtime = RUTA_MODELO.stat().st_mtime

    if _CACHE_MODELO["mtime"] != mtime:

        _CACHE_MODELO["paquete"] = joblib.load(
            RUTA_MODELO
        )

        _CACHE_MODELO["mtime"] = mtime

    return _CACHE_MODELO["paquete"]


obtener_modelo()


# =========================================================
# FUNCION DE PREDICCION
# =========================================================

def predecir_retraso(
    distancia_km,
    duracion_estimada_min,
    tiempo_preparacion_estimado_min,
    cantidad_items,
    pedidos_activos,
    fecha_pedido=None
):

    if fecha_pedido is None:

        fecha_pedido = (
            datetime.now(
                TZ_PERU
            )
        )

    elif fecha_pedido.tzinfo is None:

        fecha_pedido = (
            fecha_pedido.replace(
                tzinfo=TZ_PERU
            )
        )

    else:

        fecha_pedido = (
            fecha_pedido.astimezone(
                TZ_PERU
            )
        )


    hora_pedido = (
        fecha_pedido.hour
    )

    dia_semana = (
        fecha_pedido.weekday()
    )


    hora_pico = es_hora_pico(
        hora_pedido
    )


    fin_semana = es_fin_semana(
        dia_semana
    )


    repartidores = (
        repartidores_disponibles()
    )


    # Se calculan todas las variables conocidas; el modelo
    # toma solo las columnas con las que fue entrenado.
    datos = {

        "distancia_km":
            float(distancia_km),

        "duracion_estimada_min":
            int(duracion_estimada_min),

        "tiempo_preparacion_estimado_min":
            int(
                tiempo_preparacion_estimado_min
            ),

        "cantidad_items":
            int(cantidad_items),

        "hora_pedido":
            int(hora_pedido),

        "dia_semana":
            int(dia_semana),

        "hora_pico":
            int(hora_pico),

        "fin_semana":
            int(fin_semana),

        "pedidos_activos":
            int(pedidos_activos),

        "repartidores":
            int(repartidores),

        "carga_repartidor":
            carga_repartidor(
                int(pedidos_activos),
                repartidores
            )
    }


    paquete = obtener_modelo()

    MODELO = paquete["modelo"]

    entrada = pd.DataFrame(
        [datos],
        columns=paquete["columnas"]
    )


    clase = int(
        MODELO.predict(
            entrada
        )[0]
    )


    probabilidad = float(
        MODELO.predict_proba(
            entrada
        )[0][1]
    )


    clase_predicha = (
        "RETRASADO"
        if clase == 1
        else "A_TIEMPO"
    )


    return {

        "clase": clase,

        "clase_predicha":
            clase_predicha,

        "probabilidad_retraso":
            round(
                probabilidad,
                6
            ),

        "probabilidad_porcentaje":
            round(
                probabilidad * 100,
                2
            ),

        "modelo_version":
            paquete["version"],

        "modelo_nombre":
            paquete["nombre_modelo"],

        "variables":
            datos
    }