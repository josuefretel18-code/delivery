from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd


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
# CARGAR MODELO UNA SOLA VEZ
# =========================================================

if not RUTA_MODELO.exists():

    raise FileNotFoundError(
        f"No existe el modelo ML: "
        f"{RUTA_MODELO}"
    )


PAQUETE_MODELO = joblib.load(
    RUTA_MODELO
)

MODELO = PAQUETE_MODELO[
    "modelo"
]

COLUMNAS = PAQUETE_MODELO[
    "columnas"
]

VERSION_MODELO = PAQUETE_MODELO[
    "version"
]

NOMBRE_MODELO = PAQUETE_MODELO[
    "nombre_modelo"
]


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


    hora_pico = int(
        12 <= hora_pedido <= 14
        or
        19 <= hora_pedido <= 21
    )


    fin_semana = int(
        dia_semana
        in (4, 5, 6)
    )


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
            int(pedidos_activos)
    }


    entrada = pd.DataFrame(
        [datos],
        columns=COLUMNAS
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
            VERSION_MODELO,

        "modelo_nombre":
            NOMBRE_MODELO,

        "variables":
            datos
    }