"""
Panel del repartidor (/repartidor).

Cada repartidor inicia sesion con el acceso que le da el admin y solo
ve y entrega SUS pedidos. Marcar "entregado" usa la misma funcion que
el panel admin (calcula el retraso real y dispara el reentrenamiento).
"""

from flask import Blueprint, g, jsonify, request

from db import get_connection
from backend.decorators import roles_required
from backend.routes.pedidos import cambiar_estado_pedido


repartidor_bp = Blueprint(
    "repartidor_panel",
    __name__,
    url_prefix="/api/repartidor"
)


ZONA = "America/Lima"
ESTADOS_EN_CURSO = ("ASIGNADO", "RECOGIDO", "EN_RUTA")


def _mi_repartidor(cur):
    """(id, codigo, tipo_vehiculo, en_turno) del usuario de la sesion,
    o None si no es un repartidor activo."""

    cur.execute("""
        SELECT id, codigo, tipo_vehiculo, en_turno
        FROM repartidores
        WHERE usuario_id = %s
          AND activo = TRUE;
    """, (g.usuario["id"],))

    return cur.fetchone()


def _no_es_repartidor():

    return jsonify({
        "ok": False,
        "mensaje": "Tu cuenta no está registrada como repartidor activo"
    }), 403


@repartidor_bp.get("/perfil")
@roles_required("REPARTIDOR")
def perfil():

    with get_connection() as conn:
        with conn.cursor() as cur:

            repartidor = _mi_repartidor(cur)

            if not repartidor:
                return _no_es_repartidor()

            cur.execute(f"""
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (WHERE p.retraso IS FALSE)
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE p.repartidor_id = %s
                  AND e.codigo = 'ENTREGADO'
                  AND (p.fecha_entrega AT TIME ZONE '{ZONA}')::date
                      = (NOW() AT TIME ZONE '{ZONA}')::date;
            """, (repartidor[0],))

            entregas_hoy, a_tiempo_hoy = cur.fetchone()

    return jsonify({
        "ok": True,
        "repartidor": {
            "nombre": g.usuario["nombre"],
            "codigo": repartidor[1],
            "tipo_vehiculo": repartidor[2],
            "en_turno": repartidor[3],
            "entregas_hoy": entregas_hoy,
            "a_tiempo_hoy": a_tiempo_hoy,
        }
    })


@repartidor_bp.patch("/turno")
@roles_required("REPARTIDOR")
def cambiar_turno():

    en_turno = bool((request.get_json(silent=True) or {}).get("en_turno"))

    with get_connection() as conn:
        with conn.cursor() as cur:

            repartidor = _mi_repartidor(cur)

            if not repartidor:
                return _no_es_repartidor()

            cur.execute(
                "UPDATE repartidores SET en_turno = %s WHERE id = %s;",
                (en_turno, repartidor[0]),
            )

        conn.commit()

    return jsonify({"ok": True, "en_turno": en_turno})


@repartidor_bp.get("/pedidos")
@roles_required("REPARTIDOR")
def mis_pedidos_asignados():
    """Pedidos en curso del repartidor y sus entregas de hoy."""

    with get_connection() as conn:
        with conn.cursor() as cur:

            repartidor = _mi_repartidor(cur)

            if not repartidor:
                return _no_es_repartidor()

            cur.execute(f"""
                SELECT
                    p.id,
                    p.codigo,
                    e.codigo,
                    e.nombre,
                    p.destinatario_nombre,
                    p.destinatario_telefono,
                    p.direccion_destino,
                    p.latitud_destino,
                    p.longitud_destino,
                    p.indicaciones_entrega,
                    p.total,
                    p.metodo_pago,
                    p.distancia_km,
                    p.duracion_estimada_min,
                    p.tiempo_estimado_total_min,
                    ROUND(EXTRACT(EPOCH FROM (NOW() - p.fecha_pedido)) / 60),
                    ROUND(EXTRACT(EPOCH FROM (NOW() - COALESCE(p.fecha_recojo, NOW()))) / 60),
                    p.fecha_entrega,
                    p.retraso,
                    p.duracion_real_min,
                    (
                        SELECT STRING_AGG(d.cantidad || 'x ' || d.nombre_producto, ', ')
                        FROM detalle_pedido d
                        WHERE d.pedido_id = p.id
                    )
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE p.repartidor_id = %s
                  AND (
                      e.codigo = ANY(%s)
                      OR (
                          e.codigo = 'ENTREGADO'
                          AND (p.fecha_entrega AT TIME ZONE '{ZONA}')::date
                              = (NOW() AT TIME ZONE '{ZONA}')::date
                      )
                  )
                ORDER BY
                    (e.codigo = 'ENTREGADO'),
                    COALESCE(p.fecha_entrega, p.fecha_pedido) DESC;
            """, (repartidor[0], list(ESTADOS_EN_CURSO)))

            filas = cur.fetchall()

    en_curso = []
    entregados = []

    for fila in filas:

        prometido = fila[14]
        transcurrido = int(fila[15] or 0)

        pedido = {
            "id": fila[0],
            "codigo": fila[1],
            "estado": {"codigo": fila[2], "nombre": fila[3]},
            "cliente": fila[4],
            "telefono": fila[5],
            "direccion": fila[6],
            "latitud": float(fila[7]) if fila[7] is not None else None,
            "longitud": float(fila[8]) if fila[8] is not None else None,
            "indicaciones": fila[9],
            "total_soles": float(fila[10] or 0),
            "metodo_pago": fila[11],
            "distancia_km": float(fila[12]) if fila[12] is not None else None,
            "ruta_min": fila[13],
            "tiempo_prometido_min": prometido,
            "minutos_desde_pedido": transcurrido,
            "minutos_en_ruta": int(fila[16] or 0),
            "minutos_restantes": (prometido - transcurrido) if prometido is not None else None,
            "productos": fila[20],
        }

        if fila[2] == "ENTREGADO":
            pedido["entregado"] = fila[17].isoformat() if fila[17] else None
            pedido["con_retraso"] = fila[18]
            pedido["duracion_real_min"] = fila[19]
            entregados.append(pedido)
        else:
            en_curso.append(pedido)

    return jsonify({"ok": True, "en_curso": en_curso, "entregados_hoy": entregados})


@repartidor_bp.post("/pedidos/<int:pedido_id>/entregado")
@roles_required("REPARTIDOR")
def marcar_entregado(pedido_id):

    with get_connection() as conn:
        with conn.cursor() as cur:

            repartidor = _mi_repartidor(cur)

            if not repartidor:
                return _no_es_repartidor()

            cur.execute("""
                SELECT e.codigo
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE p.id = %s
                  AND p.repartidor_id = %s;
            """, (pedido_id, repartidor[0]))

            fila = cur.fetchone()

    if not fila:
        return jsonify({"ok": False, "mensaje": "Este pedido no está asignado a ti"}), 404

    if fila[0] != "EN_RUTA":
        return jsonify({"ok": False, "mensaje": "El pedido no está en camino"}), 409

    return cambiar_estado_pedido(pedido_id, {"estado": "ENTREGADO"})
