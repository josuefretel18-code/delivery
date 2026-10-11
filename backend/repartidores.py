"""
Repartidores: turno, carga y sugerencia de asignacion.

- El admin registra a los repartidores y marca quienes estan en turno.
- Al enviar un pedido, el sistema sugiere al repartidor en turno con
  menos pedidos activos; el admin confirma o elige otro.
- Los repartidores en turno alimentan la variable carga_repartidor del
  modelo ML (si no hay ninguno en turno se usa REPARTIDORES_DISPONIBLES).
- Si todos los repartidores estan ocupados, se estima cuanto esperaria
  un pedido nuevo a que uno vuelva (se suma al tiempo prometido).
"""

import heapq
import math
import os

from db import get_connection
from ml.variables import repartidores_disponibles


# Estados en los que un pedido ocupa a su repartidor
ESTADOS_ACTIVOS = ("ASIGNADO", "RECOGIDO", "EN_RUTA")


_COLUMNA_LISTA = {"ok": False}


def asegurar_columna_turno():

    if _COLUMNA_LISTA["ok"]:
        return

    # Primero solo se consulta (sin bloquear tablas): esta funcion se
    # llama mientras se crea un pedido y un ALTER TABLE pedidos dentro
    # de esa operacion quedaria esperando a la propia transaccion.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE (table_name = 'repartidores' AND column_name = 'en_turno')
                   OR (table_name = 'pedidos' AND column_name = 'espera_repartidor_min');
            """)

            if cur.fetchone()[0] == 2:
                _COLUMNA_LISTA["ok"] = True
                return

    ruta = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sql",
        "agregar_repartidores_turno.sql",
    )

    with open(ruta, encoding="utf-8") as archivo:
        script = archivo.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(script)

    _COLUMNA_LISTA["ok"] = True


def repartidores_en_turno():
    """Cantidad de repartidores activos en turno. Si no hay ninguno
    registrado en turno, el valor configurado (respaldo)."""

    try:
        asegurar_columna_turno()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM repartidores
                    WHERE activo = TRUE
                      AND en_turno = TRUE;
                """)

                cantidad = cur.fetchone()[0]

    except Exception as error:
        print(f"[REPARTIDORES] Sin conteo de turno: {error}", flush=True)
        cantidad = 0

    return cantidad if cantidad > 0 else repartidores_disponibles()


def listar_repartidores(solo_activos=False):
    """Repartidores con su carga actual y entregas de hoy."""

    asegurar_columna_turno()

    filtro = "WHERE r.activo = TRUE" if solo_activos else ""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    r.id,
                    r.codigo,
                    u.nombre_completo,
                    u.telefono,
                    r.tipo_vehiculo,
                    r.placa,
                    r.activo,
                    r.en_turno,
                    COUNT(p.id) FILTER (
                        WHERE e.codigo = ANY(%s)
                    ),
                    COUNT(p.id) FILTER (
                        WHERE e.codigo = 'ENTREGADO'
                          AND (p.fecha_entrega AT TIME ZONE 'America/Lima')::date
                              = (NOW() AT TIME ZONE 'America/Lima')::date
                    )
                FROM repartidores r
                JOIN usuarios u
                    ON u.id = r.usuario_id
                LEFT JOIN pedidos p
                    ON p.repartidor_id = r.id
                LEFT JOIN estados_pedido e
                    ON e.id = p.estado_id
                {filtro}
                GROUP BY r.id, u.nombre_completo, u.telefono
                ORDER BY r.activo DESC, r.en_turno DESC, u.nombre_completo;
            """, (list(ESTADOS_ACTIVOS),))

            filas = cur.fetchall()

    return [
        {
            "id": fila[0],
            "codigo": fila[1],
            "nombre": fila[2],
            "telefono": fila[3],
            "tipo_vehiculo": fila[4],
            "placa": fila[5],
            "activo": fila[6],
            "en_turno": fila[7],
            "pedidos_activos": fila[8],
            "entregas_hoy": fila[9],
        }
        for fila in filas
    ]


def sugerir_repartidor(repartidores=None):
    """El repartidor en turno con menos pedidos activos (o None)."""

    repartidores = (
        repartidores
        if repartidores is not None
        else listar_repartidores(solo_activos=True)
    )

    disponibles = [
        r for r in repartidores
        if r["activo"] and r["en_turno"]
    ]

    if not disponibles:
        return None

    return min(
        disponibles,
        key=lambda r: (r["pedidos_activos"], r["entregas_hoy"], r["id"]),
    )


def repartidores_por_pedido(pedido_ids):
    """{pedido_id: {id, nombre, telefono, tipo_vehiculo}}"""

    if not pedido_ids:
        return {}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.id,
                    r.id,
                    u.nombre_completo,
                    u.telefono,
                    r.tipo_vehiculo
                FROM pedidos p
                JOIN repartidores r
                    ON r.id = p.repartidor_id
                JOIN usuarios u
                    ON u.id = r.usuario_id
                WHERE p.id = ANY(%s);
            """, (list(pedido_ids),))

            filas = cur.fetchall()

    return {
        fila[0]: {
            "id": fila[1],
            "nombre": fila[2],
            "telefono": fila[3],
            "tipo_vehiculo": fila[4],
        }
        for fila in filas
    }



# Espera maxima que se suma al tiempo prometido (minutos)
ESPERA_MAXIMA_MIN = 90


def estimar_espera_repartidor(tiempo_preparacion_min):
    """
    Minutos que un pedido nuevo esperaria a un repartidor libre cuando
    la comida ya esta lista.

    1. Cada repartidor en turno queda libre ya (sin pedidos) o al volver
       a la tienda: ida + vuelta (2 x ruta) menos lo que ya lleva fuera.
    2. Los pedidos que esperan antes que este (sin repartidor) toman
       primero los repartidores que se van liberando, en orden.
    3. Espera = cuando queda libre un repartidor para este pedido menos
       su tiempo de preparacion (nunca negativa).

    Sin repartidores registrados en turno devuelve 0 (comportamiento
    anterior: preparacion + ruta).
    """

    resultado = {
        "espera_min": 0,
        "repartidores_en_turno": 0,
        "repartidores_libres": 0,
        "pedidos_en_espera": 0,
    }

    try:
        asegurar_columna_turno()

        with get_connection() as conn:
            with conn.cursor() as cur:

                # Minutos hasta que cada repartidor en turno vuelve libre
                cur.execute("""
                    SELECT
                        r.id,
                        COALESCE(SUM(
                            GREATEST(
                                2 * COALESCE(p.duracion_estimada_min, 0)
                                - EXTRACT(EPOCH FROM (
                                    NOW() - COALESCE(p.fecha_recojo, NOW())
                                )) / 60.0,
                                0
                            )
                        ) FILTER (WHERE e.codigo = ANY(%s)), 0)
                    FROM repartidores r
                    LEFT JOIN pedidos p
                        ON p.repartidor_id = r.id
                    LEFT JOIN estados_pedido e
                        ON e.id = p.estado_id
                    WHERE r.activo = TRUE
                      AND r.en_turno = TRUE
                    GROUP BY r.id;
                """, (list(ESTADOS_ACTIVOS),))

                libres_en = [float(fila[1]) for fila in cur.fetchall()]

                if not libres_en:
                    return resultado

                # Pedidos que esperan antes que este (aun sin repartidor)
                cur.execute("""
                    SELECT
                        GREATEST(
                            COALESCE(p.tiempo_preparacion_estimado_min, 0)
                            - EXTRACT(EPOCH FROM (NOW() - p.fecha_pedido)) / 60.0,
                            0
                        ),
                        COALESCE(p.duracion_estimada_min, 0)
                    FROM pedidos p
                    JOIN estados_pedido e
                        ON e.id = p.estado_id
                    WHERE p.repartidor_id IS NULL
                      AND e.codigo IN ('REGISTRADO', 'PREPARANDO')
                      AND COALESCE(p.fuente_datos, 'REAL') = 'REAL'
                    ORDER BY p.fecha_pedido;
                """)

                en_espera = cur.fetchall()

    except Exception as error:
        print(f"[REPARTIDORES] Sin estimacion de espera: {error}", flush=True)
        return resultado

    resultado["repartidores_en_turno"] = len(libres_en)
    resultado["repartidores_libres"] = sum(1 for t in libres_en if t <= 0)
    resultado["pedidos_en_espera"] = len(en_espera)

    heapq.heapify(libres_en)

    for listo_en, ruta in en_espera:
        libre = heapq.heappop(libres_en)
        salida = max(libre, float(listo_en))
        heapq.heappush(libres_en, salida + 2 * float(ruta))

    espera = max(libres_en[0] - float(tiempo_preparacion_min or 0), 0)

    resultado["espera_min"] = min(math.ceil(espera), ESPERA_MAXIMA_MIN)

    return resultado
