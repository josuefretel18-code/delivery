"""
Definicion unica de las variables del modelo.

La usan:
    ml/exportar_dataset.py  -> para construir el dataset
    ml/entrenar_modelo.py   -> columnas de entrada
    backend/ml_service.py   -> para predecir pedidos nuevos

Asi el modelo recibe en produccion exactamente las mismas
variables, calculadas igual, que en el entrenamiento.
"""

import os


# Variables de entrada (comunes a DoorDash y a Kimbos).
COLUMNAS_MODELO = [
    "duracion_estimada_min",
    "cantidad_items",
    "hora_pedido",
    "dia_semana",
    "hora_pico",
    "fin_semana",
    "carga_repartidor"
]

TARGET = "retraso"

# Un pedido se considera retrasado si su duracion real
# supera el tiempo estimado en mas de esta tolerancia.
TOLERANCIA_RETRASO_MIN = 5


def es_hora_pico(hora):

    # 12-14 almuerzo, 19-21 cena
    return int(
        12 <= hora <= 14
        or 19 <= hora <= 21
    )


def es_fin_semana(dia_semana):

    # 0 = lunes ... 4 = viernes, 5 = sabado, 6 = domingo
    return int(dia_semana in (4, 5, 6))


def repartidores_disponibles():

    # Kimbos no registra repartidores: se usa un valor fijo
    # configurable en .env (REPARTIDORES_DISPONIBLES).
    try:
        valor = int(os.getenv("REPARTIDORES_DISPONIBLES", "2"))
    except ValueError:
        valor = 2

    return max(valor, 1)


def carga_repartidor(pedidos_activos, repartidores):

    # Pedidos activos por repartidor disponible.
    return round(
        pedidos_activos / max(repartidores, 1),
        4
    )
