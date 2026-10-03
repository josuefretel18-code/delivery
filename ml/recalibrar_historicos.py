import hashlib
import math
import random
import sys

from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


# =========================================================
# PERMITIR IMPORTAR db.py
# =========================================================

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))


from db import get_connection


# =========================================================
# CONFIGURACION
# =========================================================

TZ = ZoneInfo("America/Lima")

TAMANO_LOTE = 50


# =========================================================
# FUNCIONES
# =========================================================

def sigmoide(valor):
    return 1 / (1 + math.exp(-valor))


def crear_rng(codigo):
    """
    Generador aleatorio estable por pedido.

    Si ejecutamos otra vez este script,
    el mismo pedido obtiene el mismo resultado.
    """

    digest = hashlib.sha256(
        codigo.encode("utf-8")
    ).hexdigest()

    semilla = int(
        digest[:16],
        16
    )

    return random.Random(
        semilla
    )


def calcular_resultado(fila):

    (
        pedido_id,
        codigo,
        fecha_pedido,
        distancia_km,
        duracion_ruta,
        tiempo_preparacion,
        cantidad_items,
        pedidos_activos,
        tiempo_estimado_total
    ) = fila

    rng = crear_rng(
        codigo
    )

    distancia_km = float(
        distancia_km
    )

    duracion_ruta = int(
        duracion_ruta
    )

    tiempo_preparacion = int(
        tiempo_preparacion
    )

    cantidad_items = int(
        cantidad_items
    )

    pedidos_activos = int(
        pedidos_activos
    )

    tiempo_estimado_total = int(
        tiempo_estimado_total
    )

    # ---------------------------------------------
    # FECHA LOCAL PERU
    # ---------------------------------------------

    fecha_local = (
        fecha_pedido.astimezone(TZ)
    )

    hora = fecha_local.hour

    dia_semana = (
        fecha_local.weekday()
    )

    # 12-14 almuerzo
    # 19-21 cena

    hora_pico = (
        12 <= hora <= 14
        or
        19 <= hora <= 21
    )

    # viernes, sabado y domingo

    fin_semana = (
        dia_semana
        in (4, 5, 6)
    )

    # ---------------------------------------------
    # RIESGO DE RETRASO
    # ---------------------------------------------

    score = -2.25

    # Distancias mayores aumentan riesgo
    score += (
        0.22
        * max(
            distancia_km - 2.5,
            0
        )
    )

    # Rutas largas aumentan riesgo
    score += (
        0.10
        * max(
            duracion_ruta - 10,
            0
        )
    )

    # Preparaciones largas
    score += (
        0.12
        * max(
            tiempo_preparacion - 10,
            0
        )
    )

    # Pedidos con varios productos
    score += (
        0.18
        * max(
            cantidad_items - 2,
            0
        )
    )

    # Carga del negocio
    score += (
        0.16
        * pedidos_activos
    )

    if hora_pico:
        score += 0.65

    if fin_semana:
        score += 0.35

    # Variacion natural
    score += rng.normalvariate(
        0,
        0.40
    )

    probabilidad = sigmoide(
        score
    )

    retraso_simulado = (
        rng.random()
        < probabilidad
    )

    # ---------------------------------------------
    # DURACION REAL
    # ---------------------------------------------

    if retraso_simulado:

        minutos_extra = rng.randint(
            6,
            18
        )

        # Con mucha carga puede demorarse algo mas

        if pedidos_activos >= 6:

            minutos_extra += rng.randint(
                1,
                5
            )

        duracion_real = (
            tiempo_estimado_total
            + minutos_extra
        )

    else:

        variacion = rng.randint(
            -4,
            5
        )

        duracion_real = max(
            8,
            tiempo_estimado_total
            + variacion
        )

    # Regla histórica:
    # retraso = más de 5 minutos sobre el estimado

    retraso = (
        duracion_real
        > tiempo_estimado_total + 5
    )

    fecha_entrega = (
        fecha_pedido
        + timedelta(
            minutes=duracion_real
        )
    )

    return {
        "pedido_id": pedido_id,
        "duracion_real": duracion_real,
        "retraso": retraso,
        "fecha_entrega": fecha_entrega
    }


# =========================================================
# LEER HISTORICOS
# =========================================================

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT
        id,
        codigo,
        fecha_pedido,
        distancia_km,
        duracion_estimada_min,
        tiempo_preparacion_estimado_min,
        cantidad_items,
        pedidos_activos_momento,
        tiempo_estimado_total_min
    FROM pedidos
    WHERE fuente_datos = 'SINTETICO_ML'
    ORDER BY id;
""")

filas = cur.fetchall()

cur.close()
conn.close()


if len(filas) != 1000:

    raise RuntimeError(
        f"Se esperaban 1000 historicos, "
        f"pero existen {len(filas)}."
    )


print("\n========================================")
print("RECALIBRACION DE HISTORICOS ML")
print("========================================")

print(
    "Pedidos encontrados:",
    len(filas)
)


# =========================================================
# PROCESAR POR LOTES
# =========================================================

procesados = 0


for inicio in range(
    0,
    len(filas),
    TAMANO_LOTE
):

    lote = filas[
        inicio:
        inicio + TAMANO_LOTE
    ]

    conn = get_connection()

    try:

        cur = conn.cursor()

        for fila in lote:

            resultado = calcular_resultado(
                fila
            )

            # -----------------------------------------
            # ACTUALIZAR PEDIDO
            # -----------------------------------------

            cur.execute("""
                UPDATE pedidos
                SET
                    duracion_real_min = %s,
                    retraso = %s,
                    fecha_entrega = %s
                WHERE id = %s
                  AND fuente_datos = 'SINTETICO_ML';
            """, (
                resultado["duracion_real"],
                resultado["retraso"],
                resultado["fecha_entrega"],
                resultado["pedido_id"]
            ))

            # -----------------------------------------
            # ACTUALIZAR ESTADO ENTREGADO DEL HISTORIAL
            # -----------------------------------------

            cur.execute("""
                UPDATE historial_pedido
                SET fecha = %s
                WHERE pedido_id = %s
                  AND estado_id = (
                      SELECT id
                      FROM estados_pedido
                      WHERE codigo = 'ENTREGADO'
                      LIMIT 1
                  );
            """, (
                resultado["fecha_entrega"],
                resultado["pedido_id"]
            ))

        conn.commit()

        procesados += len(
            lote
        )

        print(
            f"{procesados} historicos "
            f"recalibrados correctamente..."
        )

    except Exception:

        try:
            conn.rollback()
        except Exception:
            pass

        raise

    finally:

        conn.close()


# =========================================================
# VERIFICAR RESULTADO FINAL
# =========================================================

conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT
        COUNT(*) FILTER (
            WHERE retraso = FALSE
        ),
        COUNT(*) FILTER (
            WHERE retraso = TRUE
        ),
        ROUND(
            AVG(duracion_real_min),
            2
        )
    FROM pedidos
    WHERE fuente_datos = 'SINTETICO_ML';
""")

a_tiempo, retrasados, promedio_real = (
    cur.fetchone()
)

cur.close()
conn.close()


total = (
    a_tiempo
    + retrasados
)

porcentaje_retraso = (
    retrasados
    / total
    * 100
)


print("\n========================================")
print("RECALIBRACION COMPLETADA")
print("========================================")

print(
    "Total:",
    total
)

print(
    "A tiempo:",
    a_tiempo
)

print(
    "Retrasados:",
    retrasados
)

print(
    "Porcentaje retrasados:",
    f"{porcentaje_retraso:.2f}%"
)

print(
    "Duracion real promedio:",
    promedio_real,
    "min"
)

print("========================================")