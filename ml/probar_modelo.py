from pathlib import Path

import joblib
import pandas as pd


RAIZ = Path(__file__).resolve().parent.parent

RUTA_MODELO = (
    RAIZ
    / "ml"
    / "models"
    / "modelo_final.joblib"
)


# =========================================================
# CARGAR MODELO
# =========================================================

paquete = joblib.load(
    RUTA_MODELO
)

modelo = paquete["modelo"]
columnas = paquete["columnas"]


print("\n========================================")
print("PRUEBA DEL MODELO ML - KIMBOS")
print("========================================")

print(
    "Modelo:",
    paquete["nombre_modelo"]
)

print(
    "Version:",
    paquete["version"]
)

print(
    "Variables:",
    columnas
)


# =========================================================
# EJEMPLO 1 - PEDIDO DE MENOR RIESGO
# =========================================================

pedido_1 = {
    "distancia_km": 1.8,
    "duracion_estimada_min": 8,
    "tiempo_preparacion_estimado_min": 8,
    "cantidad_items": 2,
    "hora_pedido": 16,
    "dia_semana": 1,
    "hora_pico": 0,
    "fin_semana": 0,
    "pedidos_activos": 1
}


# =========================================================
# EJEMPLO 2 - PEDIDO DE MAYOR RIESGO
# =========================================================

pedido_2 = {
    "distancia_km": 7.2,
    "duracion_estimada_min": 23,
    "tiempo_preparacion_estimado_min": 18,
    "cantidad_items": 5,
    "hora_pedido": 20,
    "dia_semana": 5,
    "hora_pico": 1,
    "fin_semana": 1,
    "pedidos_activos": 8
}


def predecir(datos):

    entrada = pd.DataFrame(
        [datos],
        columns=columnas
    )

    clase = int(
        modelo.predict(
            entrada
        )[0]
    )

    probabilidad = float(
        modelo.predict_proba(
            entrada
        )[0][1]
    )

    resultado = (
        "RETRASADO"
        if clase == 1
        else "A TIEMPO"
    )

    return (
        resultado,
        probabilidad
    )


for numero, pedido in enumerate(
    [pedido_1, pedido_2],
    start=1
):

    resultado, probabilidad = (
        predecir(pedido)
    )

    print(
        f"\n--- PEDIDO {numero} ---"
    )

    print(
        "Prediccion:",
        resultado
    )

    print(
        "Probabilidad de retraso:",
        f"{probabilidad * 100:.2f}%"
    )


print("\n========================================")
print("PRUEBA FINALIZADA")
print("========================================")