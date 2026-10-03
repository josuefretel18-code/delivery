"""
Prediccion de retraso para un pedido.

Recibe el paquete del modelo ya cargado (joblib) y los datos del
pedido. Lo usan:
    ml/servicio.py         -> API de ML en Google Cloud
    backend/ml_service.py  -> modo local de desarrollo (sin ML_API_URL)
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from ml.variables import (
    es_hora_pico,
    es_fin_semana,
    repartidores_disponibles,
    carga_repartidor
)


TZ_PERU = ZoneInfo("America/Lima")


def a_hora_peru(fecha_pedido=None):

    if fecha_pedido is None:
        return datetime.now(TZ_PERU)

    if isinstance(fecha_pedido, str):
        fecha_pedido = datetime.fromisoformat(fecha_pedido)

    if fecha_pedido.tzinfo is None:
        return fecha_pedido.replace(tzinfo=TZ_PERU)

    return fecha_pedido.astimezone(TZ_PERU)


def predecir(
    paquete,
    distancia_km,
    duracion_estimada_min,
    tiempo_preparacion_estimado_min,
    cantidad_items,
    pedidos_activos,
    fecha_pedido=None,
    repartidores=None
):

    fecha_pedido = a_hora_peru(fecha_pedido)

    hora_pedido = fecha_pedido.hour
    dia_semana = fecha_pedido.weekday()

    if repartidores is None:
        repartidores = repartidores_disponibles()

    repartidores = max(int(repartidores), 1)

    # Se calculan todas las variables conocidas; el modelo
    # toma solo las columnas con las que fue entrenado.
    datos = {
        "distancia_km": float(distancia_km),
        "duracion_estimada_min": int(duracion_estimada_min),
        "tiempo_preparacion_estimado_min": int(tiempo_preparacion_estimado_min),
        "cantidad_items": int(cantidad_items),
        "hora_pedido": int(hora_pedido),
        "dia_semana": int(dia_semana),
        "hora_pico": int(es_hora_pico(hora_pedido)),
        "fin_semana": int(es_fin_semana(dia_semana)),
        "pedidos_activos": int(pedidos_activos),
        "repartidores": repartidores,
        "carga_repartidor": carga_repartidor(int(pedidos_activos), repartidores)
    }

    modelo = paquete["modelo"]

    entrada = pd.DataFrame(
        [datos],
        columns=paquete["columnas"]
    )

    clase = int(modelo.predict(entrada)[0])
    probabilidad = float(modelo.predict_proba(entrada)[0][1])

    return {
        "clase": clase,
        "clase_predicha": "RETRASADO" if clase == 1 else "A_TIEMPO",
        "probabilidad_retraso": round(probabilidad, 6),
        "probabilidad_porcentaje": round(probabilidad * 100, 2),
        "modelo_version": paquete["version"],
        "modelo_nombre": paquete["nombre_modelo"],
        "variables": datos
    }
