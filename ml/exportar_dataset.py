"""
Construye el dataset de entrenamiento:

    1. DoorDash (dataset publico de entregas reales, 2014-2015)
       ml/data/externo/historical_data.csv
    2. Pedidos reales de Kimbos ya entregados (PostgreSQL)

Los registros sinteticos (fuente_datos = SINTETICO_ML) NO se usan.

Salida:
    ml/data/pedidos_ml.csv
    ml/data/dataset_info.json   (limpieza y regla de retraso)
"""

import json
import sys
from pathlib import Path

import pandas as pd


# =========================================================
# RUTA DEL PROYECTO
# =========================================================

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))


from db import get_connection
from ml.variables import (
    COLUMNAS_MODELO,
    TARGET,
    TOLERANCIA_RETRASO_MIN,
    es_hora_pico,
    es_fin_semana,
    repartidores_disponibles,
    carga_repartidor
)


# =========================================================
# ARCHIVOS
# =========================================================

CARPETA_DATA = RAIZ_PROYECTO / "ml" / "data"

ARCHIVO_DOORDASH = (
    CARPETA_DATA
    / "externo"
    / "historical_data.csv"
)

ARCHIVO_SALIDA = CARPETA_DATA / "pedidos_ml.csv"

ARCHIVO_INFO = CARPETA_DATA / "dataset_info.json"

# Las fechas de DoorDash estan en UTC y los mercados estan
# anonimizados. Se asume hora del Pacifico (EE. UU.): con esa
# conversion los picos caen a las 12 h y 18 h (almuerzo/cena).
ZONA_DOORDASH = "America/Los_Angeles"

COLUMNAS_SALIDA = [
    "fuente_datos",
    "referencia",
    "fecha_pedido",
    "duracion_estimada_min",
    "cantidad_items",
    "hora_pedido",
    "dia_semana",
    "hora_pico",
    "fin_semana",
    "pedidos_activos",
    "repartidores",
    "carga_repartidor",
    "tiempo_estimado_total_min",
    "duracion_real_min",
    "retraso"
]


# =========================================================
# 1. DOORDASH
# =========================================================

if not ARCHIVO_DOORDASH.exists():

    raise FileNotFoundError(
        f"No existe {ARCHIVO_DOORDASH}. Descargar de Kaggle: "
        "'DoorDash ETA Prediction' (historical_data.csv)."
    )


dd = pd.read_csv(
    ARCHIVO_DOORDASH,
    parse_dates=["created_at", "actual_delivery_time"]
)

filas_originales = len(dd)


# --- Limpieza ---------------------------------------------

dd = dd.dropna(subset=[
    "actual_delivery_time",
    "estimated_store_to_consumer_driving_duration",
    "total_outstanding_orders",
    "total_onshift_dashers"
])

# Conteos negativos son errores. Tambien se excluyen filas
# con 0 repartidores en turno o 0 pedidos pendientes: el
# pedido se entrego igual, asi que el registro es inconsistente
# (y distorsiona la relacion entre carga y retraso).
dd = dd[
    (dd["total_outstanding_orders"] > 0)
    & (dd["total_onshift_dashers"] > 0)
    & (dd["total_busy_dashers"] >= 0)
]

dd["duracion_real_min"] = (
    dd["actual_delivery_time"] - dd["created_at"]
).dt.total_seconds() / 60

dd["duracion_estimada_min"] = (
    dd["estimated_store_to_consumer_driving_duration"] / 60
)

dd["envio_restaurante_min"] = (
    dd["estimated_order_place_duration"] / 60
)

# Duraciones fuera de 10-180 min, rutas en 0 y pedidos de
# mas de 30 items se consideran errores o casos atipicos.
dd = dd[
    dd["duracion_real_min"].between(10, 180)
    & (dd["duracion_estimada_min"] > 0)
    & (dd["total_items"] <= 30)
]

filas_limpias = len(dd)


# --- Regla de retraso -------------------------------------
# DoorDash no incluye un tiempo prometido. Se estima como:
#   ruta estimada + envio al restaurante + preparacion tipica
# donde la preparacion tipica es la mediana del tiempo que no
# explican la ruta ni el envio.

preparacion_tipica_min = float(
    (
        dd["duracion_real_min"]
        - dd["duracion_estimada_min"]
        - dd["envio_restaurante_min"]
    ).median()
)

dd["tiempo_estimado_total_min"] = (
    dd["duracion_estimada_min"]
    + dd["envio_restaurante_min"]
    + preparacion_tipica_min
)

dd[TARGET] = (
    dd["duracion_real_min"]
    > dd["tiempo_estimado_total_min"] + TOLERANCIA_RETRASO_MIN
).astype(int)


# --- Variables --------------------------------------------

fecha_local = (
    dd["created_at"]
    .dt.tz_localize("UTC")
    .dt.tz_convert(ZONA_DOORDASH)
)

dd["fecha_pedido"] = fecha_local
dd["hora_pedido"] = fecha_local.dt.hour
dd["dia_semana"] = fecha_local.dt.weekday
dd["hora_pico"] = dd["hora_pedido"].map(es_hora_pico)
dd["fin_semana"] = dd["dia_semana"].map(es_fin_semana)

dd["cantidad_items"] = dd["total_items"]
dd["pedidos_activos"] = dd["total_outstanding_orders"]
dd["repartidores"] = dd["total_onshift_dashers"]

dd["carga_repartidor"] = [
    carga_repartidor(pedidos, repartidores)
    for pedidos, repartidores
    in zip(dd["pedidos_activos"], dd["repartidores"])
]

dd["fuente_datos"] = "DOORDASH"
dd["referencia"] = "DD-" + dd.index.astype(str)

dd["duracion_estimada_min"] = dd["duracion_estimada_min"].round(2)
dd["tiempo_estimado_total_min"] = dd["tiempo_estimado_total_min"].round(2)
dd["duracion_real_min"] = dd["duracion_real_min"].round(2)

dd = dd[COLUMNAS_SALIDA]


# =========================================================
# 2. PEDIDOS REALES DE KIMBOS (ENTREGADOS)
# =========================================================

consulta = """
    SELECT
        codigo AS referencia,
        fecha_pedido,
        duracion_estimada_min,
        cantidad_items,

        EXTRACT(
            HOUR FROM (
                fecha_pedido
                AT TIME ZONE 'America/Lima'
            )
        )::integer
            AS hora_pedido,

        (
            EXTRACT(
                ISODOW FROM (
                    fecha_pedido
                    AT TIME ZONE 'America/Lima'
                )
            )::integer - 1
        )
            AS dia_semana,

        pedidos_activos_momento
            AS pedidos_activos,

        tiempo_estimado_total_min,
        duracion_real_min,

        CASE
            WHEN retraso = TRUE THEN 1
            ELSE 0
        END AS retraso

    FROM pedidos

    WHERE COALESCE(fuente_datos, 'REAL') = 'REAL'
      AND duracion_real_min IS NOT NULL
      AND retraso IS NOT NULL
      AND duracion_estimada_min IS NOT NULL
      AND cantidad_items IS NOT NULL
      AND pedidos_activos_momento IS NOT NULL

    ORDER BY
        fecha_pedido,
        id;
"""

with get_connection() as conn:
    with conn.cursor() as cur:

        cur.execute(consulta)

        kimbos = pd.DataFrame(
            cur.fetchall(),
            columns=[d.name for d in cur.description]
        )


repartidores_kimbos = repartidores_disponibles()

kimbos["fuente_datos"] = "REAL"
kimbos["hora_pico"] = kimbos["hora_pedido"].map(es_hora_pico)
kimbos["fin_semana"] = kimbos["dia_semana"].map(es_fin_semana)
kimbos["repartidores"] = repartidores_kimbos

kimbos["carga_repartidor"] = [
    carga_repartidor(pedidos, repartidores_kimbos)
    for pedidos in kimbos["pedidos_activos"]
]

kimbos = kimbos.reindex(columns=COLUMNAS_SALIDA)


# =========================================================
# UNIR Y VALIDAR
# =========================================================

df = pd.concat(
    [dd, kimbos],
    ignore_index=True
)

nulos = df[COLUMNAS_MODELO + [TARGET]].isnull().sum()

if nulos.any():

    raise ValueError(
        f"Valores nulos en variables del modelo:\n{nulos[nulos > 0]}"
    )


print("\n=== DATASET ===")
print("DoorDash original:", filas_originales)
print("DoorDash limpio:  ", filas_limpias)
print("Kimbos reales:    ", len(kimbos))
print("Total:            ", len(df))

print(
    f"\nPreparacion tipica DoorDash: {preparacion_tipica_min:.1f} min"
)

print("\n=== DISTRIBUCION TARGET POR FUENTE ===")
print(
    df.groupby("fuente_datos")[TARGET]
    .agg(["count", "mean"])
    .rename(columns={"count": "registros", "mean": "% retraso"})
)


# =========================================================
# EXPORTAR
# =========================================================

df.to_csv(
    ARCHIVO_SALIDA,
    index=False,
    encoding="utf-8-sig"
)

ARCHIVO_INFO.write_text(
    json.dumps(
        {
            "fuente_externa": "DoorDash ETA Prediction (Kaggle) - historical_data.csv",
            "descripcion_externa": (
                "Entregas reales de DoorDash (oct. 2014 - feb. 2015), "
                "con ruido anadido por DoorDash para anonimizar."
            ),
            "doordash_filas_originales": int(filas_originales),
            "doordash_filas_limpias": int(filas_limpias),
            "kimbos_reales": int(len(kimbos)),
            "limpieza": (
                "Sin nulos en tiempos/carga; conteos no negativos; "
                "al menos 1 repartidor en turno y 1 pedido pendiente; "
                "duracion real entre 10 y 180 min; ruta > 0; "
                "maximo 30 items."
            ),
            "zona_horaria_doordash": ZONA_DOORDASH,
            "preparacion_tipica_min": round(preparacion_tipica_min, 2),
            "regla_retraso": (
                "DoorDash: real > ruta + envio al restaurante + "
                f"preparacion tipica ({preparacion_tipica_min:.1f} min) "
                f"+ {TOLERANCIA_RETRASO_MIN} min. "
                "Kimbos: real > ruta + preparacion estimada "
                f"+ {TOLERANCIA_RETRASO_MIN} min."
            ),
            "repartidores_kimbos": repartidores_kimbos
        },
        indent=4,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

print("\n========================================")
print("DATASET EXPORTADO CORRECTAMENTE")
print("========================================")
print("Archivo:", ARCHIVO_SALIDA)
print("Registros:", len(df))
print("========================================")
