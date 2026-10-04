"""
Herramientas (funciones) que el LLM puede pedir ejecutar.

Cada herramienta devuelve datos resumidos y pequenos (menos tokens)
y aplica los permisos en el servidor: el cliente solo ve su propio
catalogo publico y sus pedidos; el admin solo tiene lectura.
"""

from decimal import Decimal

from db import get_connection
from backend.ml_service import obtener_datos_ml, predecir_retraso


COSTO_BASE_DELIVERY = Decimal("3.00")
COSTO_POR_KM = Decimal("1.20")


def _funcion(nombre, descripcion, propiedades=None):
    """Definicion de herramienta en modo estricto: todos los campos
    son obligatorios; los opcionales admiten null."""

    propiedades = propiedades or {}

    return {
        "type": "function",
        "name": nombre,
        "description": descripcion,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": propiedades,
            "required": list(propiedades),
            "additionalProperties": False,
        },
    }


def _riesgo(clase, probabilidad):

    if clase is None:
        return None

    return {
        "prediccion": clase,
        "probabilidad_retraso_pct": round(float(probabilidad) * 100, 1),
    }


# =========================================================
# CLIENTE
# =========================================================

def buscar_productos(usuario, texto=None, precio_max=None):

    filtros = ["p.activo = TRUE", "c.activa = TRUE"]
    valores = []

    if texto:
        filtros.append(
            "(p.nombre ILIKE %s OR p.descripcion ILIKE %s "
            "OR c.nombre ILIKE %s)"
        )
        patron = f"%{str(texto).strip()[:60]}%"
        valores += [patron, patron, patron]

    if precio_max is not None:
        filtros.append("p.precio <= %s")
        valores.append(precio_max)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    p.nombre,
                    c.nombre,
                    p.precio,
                    p.disponible,
                    p.tiempo_preparacion_min,
                    LEFT(p.descripcion, 80)
                FROM productos p
                JOIN categorias_producto c
                    ON c.id = p.categoria_id
                WHERE {" AND ".join(filtros)}
                ORDER BY p.disponible DESC, p.precio
                LIMIT 8;
            """, valores)

            filas = cur.fetchall()

    return {
        "productos": [
            {
                "nombre": fila[0],
                "categoria": fila[1],
                "precio_soles": float(fila[2]),
                "disponible": fila[3],
                "preparacion_min": fila[4],
                "descripcion": fila[5],
            }
            for fila in filas
        ]
    }


def mis_pedidos(usuario):

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.codigo,
                    e.nombre,
                    p.total,
                    p.fecha_pedido,
                    p.tiempo_estimado_total_min,
                    p.fecha_entrega,
                    pm.clase_predicha,
                    pm.probabilidad_retraso,
                    (
                        SELECT STRING_AGG(
                            d.cantidad || 'x ' || d.nombre_producto,
                            ', '
                        )
                        FROM detalle_pedido d
                        WHERE d.pedido_id = p.id
                    )
                FROM pedidos p
                JOIN estados_pedido e
                    ON e.id = p.estado_id
                LEFT JOIN LATERAL (
                    SELECT clase_predicha, probabilidad_retraso
                    FROM predicciones_ml
                    WHERE pedido_id = p.id
                    ORDER BY id DESC
                    LIMIT 1
                ) pm ON TRUE
                WHERE p.cliente_id = %s
                ORDER BY p.fecha_pedido DESC
                LIMIT 5;
            """, (usuario["id"],))

            filas = cur.fetchall()

    return {
        "pedidos": [
            {
                "codigo": fila[0],
                "estado": fila[1],
                "total_soles": float(fila[2] or 0),
                "fecha_pedido": fila[3].strftime("%d/%m %H:%M") if fila[3] else None,
                "tiempo_estimado_min": fila[4],
                "entregado": fila[5].strftime("%d/%m %H:%M") if fila[5] else None,
                "riesgo_retraso": _riesgo(fila[6], fila[7]),
                "productos": fila[8],
            }
            for fila in filas
        ]
    }


def info_tienda(usuario, distancia_km=None):

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT negocio_nombre, nombre, direccion, telefono
                FROM sedes
                WHERE activa = TRUE
                ORDER BY id DESC
                LIMIT 1;
            """)

            sede = cur.fetchone()

    datos = {
        "negocio": sede[0] if sede else "Kimbos",
        "sede": sede[1] if sede else None,
        "direccion": sede[2] if sede else None,
        "telefono": sede[3] if sede else None,
        "delivery": "S/ 3.00 base + S/ 1.20 por km",
        "como_pedir": (
            "Agregar productos al carrito, elegir la direccion "
            "de entrega en el mapa y confirmar el pedido."
        ),
    }

    if distancia_km is not None and 0 < distancia_km <= 50:
        costo = COSTO_BASE_DELIVERY + Decimal(str(distancia_km)) * COSTO_POR_KM
        datos["costo_delivery_estimado_soles"] = float(round(costo, 2))

    return datos


HERRAMIENTAS_CLIENTE = {
    "buscar_productos": (
        _funcion(
            "buscar_productos",
            "Busca productos del menu de Kimbos por texto (nombre, "
            "descripcion o categoria) y/o precio maximo. Devuelve hasta 8.",
            {
                "texto": {
                    "type": ["string", "null"],
                    "description": "Palabra clave, p. ej. 'pollo' o 'bebidas'. null para no filtrar.",
                },
                "precio_max": {
                    "type": ["number", "null"],
                    "description": "Precio maximo en soles. null para no filtrar.",
                },
            },
        ),
        buscar_productos,
    ),
    "mis_pedidos": (
        _funcion(
            "mis_pedidos",
            "Ultimos 5 pedidos del cliente que esta conversando: estado, "
            "total, productos, tiempo estimado y riesgo de retraso del "
            "modelo de Machine Learning.",
        ),
        mis_pedidos,
    ),
    "info_tienda": (
        _funcion(
            "info_tienda",
            "Datos de la tienda (sede, direccion, telefono), costo de "
            "delivery y como hacer un pedido.",
            {
                "distancia_km": {
                    "type": ["number", "null"],
                    "description": "Distancia en km para estimar el delivery. null si no se conoce.",
                },
            },
        ),
        info_tienda,
    ),
}


# =========================================================
# ADMIN (solo lectura)
# =========================================================

def pedidos_activos(usuario):

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.codigo,
                    e.nombre,
                    ROUND(EXTRACT(EPOCH FROM (NOW() - p.fecha_pedido)) / 60),
                    p.tiempo_estimado_total_min,
                    p.total,
                    pm.clase_predicha,
                    pm.probabilidad_retraso
                FROM pedidos p
                JOIN estados_pedido e
                    ON e.id = p.estado_id
                LEFT JOIN LATERAL (
                    SELECT clase_predicha, probabilidad_retraso
                    FROM predicciones_ml
                    WHERE pedido_id = p.id
                    ORDER BY id DESC
                    LIMIT 1
                ) pm ON TRUE
                WHERE e.es_final = FALSE
                  AND COALESCE(p.fuente_datos, 'REAL') = 'REAL'
                ORDER BY pm.probabilidad_retraso DESC NULLS LAST
                LIMIT 10;
            """)

            filas = cur.fetchall()

    return {
        "total_activos": len(filas),
        "pedidos": [
            {
                "codigo": fila[0],
                "estado": fila[1],
                "minutos_transcurridos": int(fila[2] or 0),
                "tiempo_estimado_min": fila[3],
                "total_soles": float(fila[4] or 0),
                "riesgo_retraso": _riesgo(fila[5], fila[6]),
            }
            for fila in filas
        ],
    }


def detalle_pedido(usuario, codigo):

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.id,
                    p.codigo,
                    e.nombre,
                    p.destinatario_nombre,
                    p.direccion_destino,
                    p.distancia_km,
                    p.duracion_estimada_min,
                    p.tiempo_estimado_total_min,
                    p.duracion_real_min,
                    p.retraso,
                    p.total,
                    p.metodo_pago,
                    p.fecha_pedido,
                    pm.clase_predicha,
                    pm.probabilidad_retraso,
                    pm.modelo_version
                FROM pedidos p
                JOIN estados_pedido e
                    ON e.id = p.estado_id
                LEFT JOIN LATERAL (
                    SELECT clase_predicha, probabilidad_retraso, modelo_version
                    FROM predicciones_ml
                    WHERE pedido_id = p.id
                    ORDER BY id DESC
                    LIMIT 1
                ) pm ON TRUE
                WHERE UPPER(p.codigo) = UPPER(%s);
            """, (str(codigo).strip()[:30],))

            fila = cur.fetchone()

            if not fila:
                return {"error": f"No existe el pedido {codigo}"}

            cur.execute("""
                SELECT STRING_AGG(cantidad || 'x ' || nombre_producto, ', ')
                FROM detalle_pedido
                WHERE pedido_id = %s;
            """, (fila[0],))

            productos = cur.fetchone()[0]

            cur.execute("""
                SELECT e.nombre, TO_CHAR(h.fecha, 'DD/MM HH24:MI')
                FROM historial_pedido h
                JOIN estados_pedido e
                    ON e.id = h.estado_id
                WHERE h.pedido_id = %s
                ORDER BY h.fecha;
            """, (fila[0],))

            historial = [f"{estado} ({fecha})" for estado, fecha in cur.fetchall()]

    riesgo = _riesgo(fila[13], fila[14])

    if riesgo:
        riesgo["modelo"] = fila[15]

    return {
        "codigo": fila[1],
        "estado": fila[2],
        "cliente": fila[3],
        "direccion": fila[4],
        "distancia_km": float(fila[5]) if fila[5] is not None else None,
        "ruta_estimada_min": fila[6],
        "tiempo_estimado_total_min": fila[7],
        "duracion_real_min": fila[8],
        "se_retraso": fila[9],
        "total_soles": float(fila[10] or 0),
        "metodo_pago": fila[11],
        "fecha_pedido": fila[12].strftime("%d/%m/%Y %H:%M") if fila[12] else None,
        "productos": productos,
        "riesgo_retraso": riesgo,
        "historial": historial,
    }


def simular_pedido(usuario, distancia_km, duracion_estimada_min,
                   cantidad_items, tiempo_preparacion_min):

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM pedidos p
                JOIN estados_pedido e
                    ON e.id = p.estado_id
                WHERE COALESCE(p.fuente_datos, 'REAL') = 'REAL'
                  AND e.codigo IN ('REGISTRADO', 'PREPARANDO', 'EN_RUTA');
            """)

            activos = cur.fetchone()[0]

    prediccion = predecir_retraso(
        distancia_km=max(float(distancia_km), 0.1),
        duracion_estimada_min=max(int(duracion_estimada_min), 1),
        tiempo_preparacion_estimado_min=max(int(tiempo_preparacion_min), 0),
        cantidad_items=max(int(cantidad_items), 1),
        pedidos_activos=activos,
    )

    return {
        "prediccion": prediccion["clase_predicha"],
        "probabilidad_retraso_pct": prediccion["probabilidad_porcentaje"],
        "modelo": f"{prediccion['modelo_nombre']} {prediccion['modelo_version']}",
        "pedidos_activos_ahora": activos,
    }


def estado_modelo(usuario):

    datos = obtener_datos_ml()
    metricas = datos.get("metricas") or {}
    historial = datos.get("historial") or []
    estado = datos.get("estado") or {}

    seleccionado = metricas.get("modelo_seleccionado")
    resultado = (metricas.get("resultados") or {}).get(seleccionado, {})
    ultimo = historial[-1] if historial else {}

    return {
        "modelo": seleccionado,
        "version": metricas.get("version_modelo"),
        "entrenado": metricas.get("fecha_entrenamiento_utc"),
        "f1_cv": resultado.get("f1_cv_promedio"),
        "accuracy": resultado.get("accuracy_test"),
        "precision": resultado.get("precision_test"),
        "recall": resultado.get("recall_test"),
        "roc_auc": resultado.get("roc_auc_test"),
        "registros_reales_kimbos": ultimo.get("registros_reales"),
        "ultimo_reentrenamiento": {
            "resultado": estado.get("resultado"),
            "mensaje": estado.get("mensaje"),
        },
    }


HERRAMIENTAS_ADMIN = {
    "pedidos_activos": (
        _funcion(
            "pedidos_activos",
            "Pedidos en curso (no entregados ni cancelados), ordenados "
            "por riesgo de retraso del modelo ML. Hasta 10.",
        ),
        pedidos_activos,
    ),
    "detalle_pedido": (
        _funcion(
            "detalle_pedido",
            "Detalle de un pedido por su codigo: estado, cliente, "
            "productos, tiempos, prediccion ML e historial de estados.",
            {
                "codigo": {
                    "type": "string",
                    "description": "Codigo del pedido, p. ej. 'KIM-20261003-0001'.",
                },
            },
        ),
        detalle_pedido,
    ),
    "simular_pedido": (
        _funcion(
            "simular_pedido",
            "Predice con el modelo ML si un pedido hipotetico llegaria "
            "tarde, usando la carga actual de pedidos activos.",
            {
                "distancia_km": {"type": "number", "description": "Distancia en km."},
                "duracion_estimada_min": {"type": "integer", "description": "Minutos de ruta estimados."},
                "cantidad_items": {"type": "integer", "description": "Cantidad de productos."},
                "tiempo_preparacion_min": {"type": "integer", "description": "Minutos de preparacion."},
            },
        ),
        simular_pedido,
    ),
    "estado_modelo": (
        _funcion(
            "estado_modelo",
            "Modelo ML vigente: version, metricas (F1 CV, accuracy, "
            "ROC-AUC) y resultado del ultimo reentrenamiento.",
        ),
        estado_modelo,
    ),
}
