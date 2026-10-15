"""
Dashboard del administrador (solo lectura).

Indicadores del periodo elegido (hoy, 7 o 30 dias, hora de Lima) a
partir de las tablas que ya existen. No modifica datos ni reutiliza
funciones de otras pantallas: solo consultas SQL agregadas.
"""

from flask import Blueprint, jsonify, request

from db import get_connection
from backend.decorators import roles_required


dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    url_prefix="/api/dashboard"
)


ZONA = "America/Lima"
PERIODOS = (1, 7, 30)

# Pedidos reales del rango [desde, hasta] (fechas en hora de Lima)
FILTRO = f"""
    COALESCE(p.fuente_datos, 'REAL') = 'REAL'
    AND (p.fecha_pedido AT TIME ZONE '{ZONA}')::date BETWEEN %(desde)s AND %(hasta)s
"""


def _numero(valor, decimales=None):

    if valor is None:
        return None

    valor = float(valor)

    return round(valor, decimales) if decimales is not None else valor


def _porcentaje(parte, total):

    return round(parte * 100 / total, 1) if total else None


def _indicadores(cur, rango):

    cur.execute(f"""
        SELECT
            COUNT(*),
            COUNT(*) FILTER (WHERE e.codigo = 'CANCELADO'),
            COALESCE(SUM(p.total) FILTER (WHERE e.codigo <> 'CANCELADO'), 0),
            COUNT(*) FILTER (WHERE p.retraso IS NOT NULL),
            COUNT(*) FILTER (WHERE p.retraso IS FALSE),
            AVG(p.duracion_real_min) FILTER (WHERE p.duracion_real_min IS NOT NULL),
            AVG(p.tiempo_estimado_total_min) FILTER (WHERE p.duracion_real_min IS NOT NULL)
        FROM pedidos p
        JOIN estados_pedido e ON e.id = p.estado_id
        WHERE {FILTRO};
    """, rango)

    (pedidos, cancelados, ventas, evaluadas, a_tiempo,
     real_prom, prometido_prom) = cur.fetchone()

    cur.execute(f"""
        SELECT
            COUNT(*),
            COUNT(*) FILTER (
                WHERE (pm.clase_predicha = 'RETRASADO') = p.retraso
            )
        FROM pedidos p
        JOIN LATERAL (
            SELECT clase_predicha
            FROM predicciones_ml
            WHERE pedido_id = p.id
            ORDER BY id DESC
            LIMIT 1
        ) pm ON TRUE
        WHERE {FILTRO} AND p.retraso IS NOT NULL;
    """, rango)

    ml_evaluados, ml_aciertos = cur.fetchone()

    vendidos = pedidos - cancelados

    return {
        "pedidos": pedidos,
        "cancelados": cancelados,
        "ventas_soles": _numero(ventas, 2),
        "ticket_promedio_soles": _numero(ventas / vendidos, 2) if vendidos else None,
        "entregas_evaluadas": evaluadas,
        "porcentaje_a_tiempo": _porcentaje(a_tiempo, evaluadas),
        "tiempo_real_promedio_min": _numero(real_prom, 1),
        "tiempo_prometido_promedio_min": _numero(prometido_prom, 1),
        "ml_evaluados": ml_evaluados,
        "porcentaje_acierto_ml": _porcentaje(ml_aciertos, ml_evaluados),
    }


@dashboard_bp.get("")
@roles_required("ADMIN", "OPERADOR")
def obtener_dashboard():

    try:
        periodo = int(request.args.get("periodo", 7))
    except ValueError:
        periodo = 7

    if periodo not in PERIODOS:
        periodo = 7

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(f"SELECT (NOW() AT TIME ZONE '{ZONA}')::date;")
            hoy = cur.fetchone()[0]

            cur.execute("SELECT %s::date - %s, %s::date - %s, %s::date - %s;", (
                hoy, periodo - 1,
                hoy, 2 * periodo - 1,
                hoy, periodo,
            ))
            desde, desde_anterior, hasta_anterior = cur.fetchone()

            rango = {"desde": desde, "hasta": hoy}
            rango_anterior = {"desde": desde_anterior, "hasta": hasta_anterior}

            actual = _indicadores(cur, rango)
            anterior = _indicadores(cur, rango_anterior)

            # Ventas, pedidos y entregas por dia (dias sin pedidos = 0)
            cur.execute(f"""
                WITH dias AS (
                    SELECT generate_series(%(desde)s::date, %(hasta)s::date, '1 day')::date AS dia
                ),
                datos AS (
                    SELECT
                        (p.fecha_pedido AT TIME ZONE '{ZONA}')::date AS dia,
                        COUNT(*) AS pedidos,
                        COALESCE(SUM(p.total) FILTER (WHERE e.codigo <> 'CANCELADO'), 0) AS ventas,
                        COUNT(*) FILTER (WHERE p.retraso IS FALSE) AS a_tiempo,
                        COUNT(*) FILTER (WHERE p.retraso IS TRUE) AS retrasados
                    FROM pedidos p
                    JOIN estados_pedido e ON e.id = p.estado_id
                    WHERE {FILTRO}
                    GROUP BY 1
                )
                SELECT
                    d.dia,
                    COALESCE(x.pedidos, 0),
                    COALESCE(x.ventas, 0),
                    COALESCE(x.a_tiempo, 0),
                    COALESCE(x.retrasados, 0)
                FROM dias d
                LEFT JOIN datos x ON x.dia = d.dia
                ORDER BY d.dia;
            """, rango)

            por_dia = [
                {
                    "dia": fila[0].isoformat(),
                    "pedidos": fila[1],
                    "ventas_soles": _numero(fila[2], 2),
                    "a_tiempo": fila[3],
                    "retrasados": fila[4],
                }
                for fila in cur.fetchall()
            ]

            # Pedidos y ventas por hora del dia
            cur.execute(f"""
                SELECT
                    EXTRACT(HOUR FROM p.fecha_pedido AT TIME ZONE '{ZONA}')::int,
                    COUNT(*),
                    COALESCE(SUM(p.total) FILTER (WHERE e.codigo <> 'CANCELADO'), 0)
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE {FILTRO}
                GROUP BY 1;
            """, rango)

            horas = {fila[0]: (fila[1], fila[2]) for fila in cur.fetchall()}

            por_hora = [
                {
                    "hora": h,
                    "pedidos": horas.get(h, (0, 0))[0],
                    "ventas_soles": _numero(horas.get(h, (0, 0))[1], 2),
                }
                for h in range(24)
            ]

            # Productos mas vendidos
            cur.execute(f"""
                SELECT d.nombre_producto, SUM(d.cantidad), SUM(d.subtotal)
                FROM detalle_pedido d
                JOIN pedidos p ON p.id = d.pedido_id
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE {FILTRO} AND e.codigo <> 'CANCELADO'
                GROUP BY 1
                ORDER BY 2 DESC, 3 DESC
                LIMIT 5;
            """, rango)

            productos = [
                {
                    "producto": fila[0],
                    "unidades": int(fila[1]),
                    "ventas_soles": _numero(fila[2], 2),
                }
                for fila in cur.fetchall()
            ]

            # Repartidores
            cur.execute(f"""
                SELECT
                    u.nombre_completo,
                    COUNT(*) FILTER (WHERE e.codigo = 'ENTREGADO'),
                    COUNT(*) FILTER (WHERE p.retraso IS TRUE),
                    AVG(p.duracion_real_min)
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                JOIN repartidores r ON r.id = p.repartidor_id
                JOIN usuarios u ON u.id = r.usuario_id
                WHERE {FILTRO}
                GROUP BY 1
                ORDER BY 2 DESC, 1;
            """, rango)

            repartidores = [
                {
                    "repartidor": fila[0],
                    "entregas": fila[1],
                    "retrasos": fila[2],
                    "tiempo_real_promedio_min": _numero(fila[3], 1),
                }
                for fila in cur.fetchall()
            ]

            # Modelo ML: prediccion vs resultado real
            cur.execute(f"""
                SELECT
                    COUNT(*) FILTER (WHERE pm.clase_predicha = 'RETRASADO' AND p.retraso),
                    COUNT(*) FILTER (WHERE pm.clase_predicha = 'RETRASADO' AND NOT p.retraso),
                    COUNT(*) FILTER (WHERE pm.clase_predicha <> 'RETRASADO' AND p.retraso),
                    COUNT(*) FILTER (WHERE pm.clase_predicha <> 'RETRASADO' AND NOT p.retraso)
                FROM pedidos p
                JOIN LATERAL (
                    SELECT clase_predicha
                    FROM predicciones_ml
                    WHERE pedido_id = p.id
                    ORDER BY id DESC
                    LIMIT 1
                ) pm ON TRUE
                WHERE {FILTRO} AND p.retraso IS NOT NULL;
            """, rango)

            vp, fp, fn, vn = cur.fetchone()

            cur.execute(f"""
                SELECT AVG(pm.probabilidad_retraso) * 100
                FROM pedidos p
                JOIN LATERAL (
                    SELECT probabilidad_retraso
                    FROM predicciones_ml
                    WHERE pedido_id = p.id
                    ORDER BY id DESC
                    LIMIT 1
                ) pm ON TRUE
                WHERE {FILTRO};
            """, rango)

            riesgo_promedio = _numero(cur.fetchone()[0], 1)

            # Sistema multiagente (la tabla puede no existir aun)
            alertas = {"por_nivel": {}, "por_accion": {}}

            try:
                cur.execute(f"""
                    SELECT a.nivel, a.accion, COUNT(*)
                    FROM alertas_pedido a
                    JOIN pedidos p ON p.id = a.pedido_id
                    WHERE {FILTRO} AND a.estado = 'LISTA'
                    GROUP BY 1, 2;
                """, rango)

                for nivel, accion, cantidad in cur.fetchall():
                    alertas["por_nivel"][nivel] = alertas["por_nivel"].get(nivel, 0) + cantidad
                    alertas["por_accion"][accion] = alertas["por_accion"].get(accion, 0) + cantidad

            except Exception:
                conn.rollback()

    return jsonify({
        "ok": True,
        "periodo": periodo,
        "desde": desde.isoformat(),
        "hasta": hoy.isoformat(),
        "indicadores": actual,
        "anterior": anterior,
        "por_dia": por_dia,
        "por_hora": por_hora,
        "productos": productos,
        "repartidores": repartidores,
        "modelo_ml": {
            "verdaderos_retrasos": vp,
            "falsas_alarmas": fp,
            "retrasos_no_detectados": fn,
            "verdaderos_a_tiempo": vn,
            "riesgo_promedio_pct": riesgo_promedio,
        },
        "alertas": alertas,
    })
