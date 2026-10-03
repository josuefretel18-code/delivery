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


# =========================================================
# ARCHIVO DE SALIDA
# =========================================================

CARPETA_DATA = RAIZ_PROYECTO / "ml" / "data"

CARPETA_DATA.mkdir(
    parents=True,
    exist_ok=True
)

ARCHIVO_SALIDA = (
    CARPETA_DATA
    / "pedidos_ml.csv"
)


# =========================================================
# CONSULTA
# =========================================================

consulta = """
    SELECT
        id AS pedido_id,
        codigo,
        fecha_pedido,

        distancia_km::double precision
            AS distancia_km,

        duracion_estimada_min,

        tiempo_preparacion_estimado_min,

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

        CASE
            WHEN EXTRACT(
                HOUR FROM (
                    fecha_pedido
                    AT TIME ZONE 'America/Lima'
                )
            )::integer BETWEEN 12 AND 14
            OR EXTRACT(
                HOUR FROM (
                    fecha_pedido
                    AT TIME ZONE 'America/Lima'
                )
            )::integer BETWEEN 19 AND 21
            THEN 1
            ELSE 0
        END AS hora_pico,

        CASE
            WHEN EXTRACT(
                ISODOW FROM (
                    fecha_pedido
                    AT TIME ZONE 'America/Lima'
                )
            )::integer IN (5, 6, 7)
            THEN 1
            ELSE 0
        END AS fin_semana,

        pedidos_activos_momento
            AS pedidos_activos,

        tiempo_estimado_total_min,

        duracion_real_min,

        CASE
            WHEN retraso = TRUE THEN 1
            ELSE 0
        END AS retraso

    FROM pedidos

    WHERE fuente_datos = 'SINTETICO_ML'

    ORDER BY
        fecha_pedido,
        id;
"""


# =========================================================
# EXTRAER DE POSTGRESQL
# =========================================================

conn = get_connection()
cur = conn.cursor()

cur.execute(consulta)

filas = cur.fetchall()

columnas = [
    descripcion.name
    for descripcion in cur.description
]

cur.close()
conn.close()


df = pd.DataFrame(
    filas,
    columns=columnas
)


# =========================================================
# VALIDACIONES
# =========================================================

print("\n=== VALIDACION DEL DATASET ===")

print(
    "Registros:",
    len(df)
)

print(
    "Columnas:",
    len(df.columns)
)


columnas_modelo = [
    "distancia_km",
    "duracion_estimada_min",
    "tiempo_preparacion_estimado_min",
    "cantidad_items",
    "hora_pedido",
    "dia_semana",
    "hora_pico",
    "fin_semana",
    "pedidos_activos"
]


faltantes = (
    df[columnas_modelo + ["retraso"]]
    .isnull()
    .sum()
)

print("\n=== VALORES NULOS ===")

print(faltantes)


print("\n=== DISTRIBUCION TARGET ===")

print(
    df["retraso"]
    .value_counts()
    .sort_index()
)

print("\n0 = A TIEMPO")
print("1 = RETRASADO")


# =========================================================
# EXPORTAR CSV
# =========================================================

df.to_csv(
    ARCHIVO_SALIDA,
    index=False,
    encoding="utf-8-sig"
)


print("\n========================================")
print("DATASET EXPORTADO CORRECTAMENTE")
print("========================================")

print(
    "Archivo:",
    ARCHIVO_SALIDA
)

print(
    "Registros:",
    len(df)
)

print("========================================")