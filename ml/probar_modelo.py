"""
Prueba rapida del modelo activo con dos pedidos de ejemplo.

Usa la misma funcion de prediccion que Flask, asi que las
variables se calculan igual que en un pedido real.

Uso (desde la raiz del proyecto):
    python ml/probar_modelo.py
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from backend.ml_service import obtener_modelo, predecir_retraso


TZ_PERU = ZoneInfo("America/Lima")

paquete = obtener_modelo()

print("\n========================================")
print("PRUEBA DEL MODELO ML - KIMBOS")
print("========================================")
print("Modelo:", paquete["nombre_modelo"])
print("Version:", paquete["version"])
print("Variables:", paquete["columnas"])


pedidos = {
    "PEDIDO DE MENOR RIESGO": dict(
        distancia_km=1.8,
        duracion_estimada_min=8,
        tiempo_preparacion_estimado_min=8,
        cantidad_items=2,
        pedidos_activos=0,
        fecha_pedido=datetime(2026, 9, 29, 16, 0, tzinfo=TZ_PERU)
    ),
    "PEDIDO DE MAYOR RIESGO": dict(
        distancia_km=7.2,
        duracion_estimada_min=23,
        tiempo_preparacion_estimado_min=18,
        cantidad_items=5,
        pedidos_activos=5,
        fecha_pedido=datetime(2026, 10, 3, 20, 0, tzinfo=TZ_PERU)
    )
}


for titulo, datos in pedidos.items():

    resultado = predecir_retraso(**datos)

    print(f"\n=== {titulo} ===")
    print("Variables:", resultado["variables"])
    print("Prediccion:", resultado["clase_predicha"])
    print(
        "Probabilidad de retraso:",
        f"{resultado['probabilidad_porcentaje']:.2f}%"
    )
