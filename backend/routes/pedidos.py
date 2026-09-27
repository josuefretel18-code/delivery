import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g

from db import get_connection
from backend.decorators import token_required, roles_required
from decimal import Decimal, ROUND_HALF_UP


pedidos_bp = Blueprint(
    "pedidos",
    __name__,
    url_prefix="/api/pedidos"
)


def generar_codigo_pedido():
    anio = datetime.now(timezone.utc).year
    aleatorio = secrets.token_hex(4).upper()

    return f"PED-{anio}-{aleatorio}"


def obtener_estado_id(codigo_estado):
    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM estados_pedido
                WHERE codigo = %s;
            """, (codigo_estado,))

            estado = cur.fetchone()

    if not estado:
        raise ValueError(
            f"No existe el estado {codigo_estado}"
        )

    return estado[0]

def obtener_sede_activa():
    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    negocio_nombre,
                    nombre,
                    direccion,
                    latitud,
                    longitud,
                    telefono
                FROM sedes
                WHERE activa = TRUE
                ORDER BY id DESC
                LIMIT 1;
            """)

            sede = cur.fetchone()

    if not sede:
        return None

    return {
        "id": sede[0],
        "negocio": sede[1],
        "nombre": sede[2],
        "direccion": sede[3],
        "latitud": sede[4],
        "longitud": sede[5],
        "telefono": sede[6]
    }


# =========================================================
# CREAR PEDIDO
# =========================================================

@pedidos_bp.post("")
@token_required
def crear_pedido():

    datos = request.get_json(silent=True) or {}

    # =====================================================
    # PERMISOS
    # =====================================================

    if g.usuario["rol"] not in (
        "CLIENTE",
        "ADMIN",
        "OPERADOR"
    ):
        return jsonify({
            "ok": False,
            "mensaje": "No tiene permisos para registrar pedidos"
        }), 403


    # =====================================================
    # CAMPOS OBLIGATORIOS
    # =====================================================

    campos_obligatorios = [
        "destinatario_nombre",
        "destinatario_telefono",
        "direccion_destino",
        "latitud_destino",
        "longitud_destino",
        "distancia_km",
        "duracion_estimada_min"
    ]

    faltantes = [
        campo
        for campo in campos_obligatorios
        if datos.get(campo) in (None, "")
    ]

    if faltantes:
        return jsonify({
            "ok": False,
            "mensaje": "Faltan datos obligatorios",
            "campos": faltantes
        }), 400


    items = datos.get("items")


    if not isinstance(items, list) or len(items) == 0:
        return jsonify({
            "ok": False,
            "mensaje": "El pedido debe contener al menos un producto"
        }), 400


    # =====================================================
    # VALIDAR UBICACIÓN Y RUTA
    # =====================================================

    try:

        latitud_destino = float(
            datos["latitud_destino"]
        )

        longitud_destino = float(
            datos["longitud_destino"]
        )

        distancia_km = Decimal(
            str(datos["distancia_km"])
        )

        duracion_estimada_min = int(
            datos["duracion_estimada_min"]
        )

    except (
        ValueError,
        TypeError
    ):

        return jsonify({
            "ok": False,
            "mensaje": "Los datos de ubicación o ruta son inválidos"
        }), 400


    if not (-90 <= latitud_destino <= 90):

        return jsonify({
            "ok": False,
            "mensaje": "Latitud de destino inválida"
        }), 400


    if not (-180 <= longitud_destino <= 180):

        return jsonify({
            "ok": False,
            "mensaje": "Longitud de destino inválida"
        }), 400


    if distancia_km <= 0:

        return jsonify({
            "ok": False,
            "mensaje": "La distancia debe ser mayor que cero"
        }), 400


    if duracion_estimada_min <= 0:

        return jsonify({
            "ok": False,
            "mensaje": "La duración estimada debe ser mayor que cero"
        }), 400


    # =====================================================
    # SEDE
    # =====================================================

    sede = obtener_sede_activa()


    if not sede:

        return jsonify({
            "ok": False,
            "mensaje": "No existe una sede activa"
        }), 409


    codigo = generar_codigo_pedido()

    estado_id = obtener_estado_id(
        "REGISTRADO"
    )


    try:

        with get_connection() as conn:

            with conn.cursor() as cur:

                # =========================================
                # VALIDAR PRODUCTOS DESDE POSTGRESQL
                # =========================================

                productos_pedido = []

                subtotal = Decimal(
                    "0.00"
                )

                cantidad_items = 0

                tiempo_preparacion = 0


                for item in items:

                    try:

                        producto_id = int(
                            item.get("producto_id")
                        )

                        cantidad = int(
                            item.get("cantidad")
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        return jsonify({
                            "ok": False,
                            "mensaje": "Producto o cantidad inválidos"
                        }), 400


                    if cantidad <= 0:

                        return jsonify({
                            "ok": False,
                            "mensaje": "La cantidad debe ser mayor que cero"
                        }), 400


                    cur.execute("""
                        SELECT
                            id,
                            nombre,
                            precio,
                            tiempo_preparacion_min,
                            disponible,
                            activo

                        FROM productos

                        WHERE id = %s;
                    """, (
                        producto_id,
                    ))


                    producto = cur.fetchone()


                    if not producto:

                        return jsonify({
                            "ok": False,
                            "mensaje": f"El producto {producto_id} no existe"
                        }), 404


                    if not producto[5]:

                        return jsonify({
                            "ok": False,
                            "mensaje": f"{producto[1]} ya no está activo"
                        }), 409


                    if not producto[4]:

                        return jsonify({
                            "ok": False,
                            "mensaje": f"{producto[1]} está agotado"
                        }), 409


                    precio = Decimal(
                        str(producto[2])
                    )


                    subtotal_producto = (
                        precio *
                        cantidad
                    ).quantize(
                        Decimal("0.01")
                    )


                    subtotal += (
                        subtotal_producto
                    )


                    cantidad_items += (
                        cantidad
                    )


                    tiempo_preparacion = max(
                        tiempo_preparacion,
                        producto[3]
                    )


                    productos_pedido.append({
                        "producto_id": producto[0],
                        "nombre": producto[1],
                        "precio": precio,
                        "cantidad": cantidad,
                        "subtotal": subtotal_producto
                    })


                # =========================================
                # COSTO DELIVERY
                #
                # S/ 3.00 base + S/ 1.20 por km
                # =========================================

                costo_base = Decimal(
                    "3.00"
                )

                costo_por_km = Decimal(
                    "1.20"
                )


                costo_delivery = (
                    costo_base +
                    (
                        distancia_km *
                        costo_por_km
                    )
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )


                subtotal = subtotal.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )


                total = (
                    subtotal +
                    costo_delivery
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )


                tiempo_estimado_total = (
                    tiempo_preparacion +
                    duracion_estimada_min
                )


                # =========================================
                # INSERTAR PEDIDO
                # =========================================

                cur.execute("""
                    INSERT INTO pedidos (

                        codigo,
                        cliente_id,
                        sede_id,
                        estado_id,

                        remitente_nombre,
                        remitente_telefono,

                        destinatario_nombre,
                        destinatario_telefono,

                        descripcion_paquete,

                        direccion_origen,
                        latitud_origen,
                        longitud_origen,
                        zona_origen,

                        direccion_destino,
                        latitud_destino,
                        longitud_destino,
                        zona_destino,

                        distancia_km,
                        duracion_estimada_min,

                        subtotal,
                        costo_delivery,
                        total,

                        cantidad_items,

                        tiempo_preparacion_estimado_min,
                        tiempo_estimado_total_min,

                        metodo_pago,
                        indicaciones_entrega,

                        observaciones

                    )
                    VALUES (

                        %s, %s, %s, %s,

                        %s, %s,

                        %s, %s,

                        %s,

                        %s, %s, %s, %s,

                        %s, %s, %s, %s,

                        %s, %s,

                        %s, %s, %s,

                        %s,

                        %s, %s,

                        %s, %s,

                        %s

                    )

                    RETURNING id;
                """, (

                    codigo,
                    g.usuario["id"],
                    sede["id"],
                    estado_id,

                    sede["negocio"],
                    sede["telefono"],

                    datos["destinatario_nombre"],
                    datos["destinatario_telefono"],

                    f"{cantidad_items} producto(s)",

                    sede["direccion"],
                    sede["latitud"],
                    sede["longitud"],
                    sede["nombre"],

                    datos["direccion_destino"],
                    latitud_destino,
                    longitud_destino,
                    datos.get("zona_destino"),

                    distancia_km,
                    duracion_estimada_min,

                    subtotal,
                    costo_delivery,
                    total,

                    cantidad_items,

                    tiempo_preparacion,
                    tiempo_estimado_total,

                    datos.get(
                        "metodo_pago"
                    ),

                    datos.get(
                        "indicaciones_entrega"
                    ),

                    datos.get(
                        "observaciones"
                    )
                ))


                pedido_id = cur.fetchone()[0]


                # =========================================
                # DETALLE DEL PEDIDO
                # =========================================

                for producto in productos_pedido:

                    cur.execute("""
                        INSERT INTO detalle_pedido (

                            pedido_id,
                            producto_id,
                            nombre_producto,
                            precio_unitario,
                            cantidad,
                            subtotal

                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s
                        );
                    """, (

                        pedido_id,

                        producto[
                            "producto_id"
                        ],

                        producto[
                            "nombre"
                        ],

                        producto[
                            "precio"
                        ],

                        producto[
                            "cantidad"
                        ],

                        producto[
                            "subtotal"
                        ]
                    ))


                # =========================================
                # HISTORIAL
                # =========================================

                cur.execute("""
                    INSERT INTO historial_pedido (

                        pedido_id,
                        estado_id,
                        observacion,
                        usuario_id

                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s
                    );
                """, (

                    pedido_id,
                    estado_id,
                    "Pedido registrado",
                    g.usuario["id"]

                ))


            conn.commit()


        return jsonify({

            "ok": True,

            "mensaje":
                "Pedido registrado correctamente",

            "pedido": {

                "id":
                    pedido_id,

                "codigo":
                    codigo,

                "estado":
                    "REGISTRADO",

                "cantidad_items":
                    cantidad_items,

                "subtotal":
                    float(subtotal),

                "costo_delivery":
                    float(costo_delivery),

                "total":
                    float(total),

                "distancia_km":
                    float(distancia_km),

                "duracion_estimada_min":
                    duracion_estimada_min,

                "tiempo_preparacion_estimado_min":
                    tiempo_preparacion,

                "tiempo_estimado_total_min":
                    tiempo_estimado_total
            }

        }), 201


    except Exception as error:

        return jsonify({
            "ok": False,
            "mensaje": "No se pudo registrar el pedido",
            "detalle": str(error)
        }), 500


# =========================================================
# MIS PEDIDOS
# =========================================================

@pedidos_bp.get("/mis-pedidos")
@token_required
def mis_pedidos():

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    p.id,
                    p.codigo,

                    e.codigo,
                    e.nombre,

                    p.cantidad_items,

                    p.subtotal,
                    p.costo_delivery,
                    p.total,

                    p.distancia_km,
                    p.duracion_estimada_min,
                    p.tiempo_preparacion_estimado_min,
                    p.tiempo_estimado_total_min,

                    p.metodo_pago,

                    p.destinatario_nombre,
                    p.direccion_destino,

                    p.fecha_pedido,
                    p.fecha_entrega

                FROM pedidos p

                JOIN estados_pedido e
                    ON e.id = p.estado_id

                WHERE p.cliente_id = %s

                ORDER BY p.fecha_pedido DESC;
            """, (
                g.usuario["id"],
            ))

            filas = cur.fetchall()

            pedidos = []

            for fila in filas:

                pedido_id = fila[0]

                # =========================================
                # PRODUCTOS
                # =========================================

                cur.execute("""
                    SELECT
                        producto_id,
                        nombre_producto,
                        precio_unitario,
                        cantidad,
                        subtotal

                    FROM detalle_pedido

                    WHERE pedido_id = %s

                    ORDER BY id;
                """, (
                    pedido_id,
                ))

                productos = []

                for producto in cur.fetchall():

                    productos.append({
                        "producto_id": producto[0],
                        "nombre": producto[1],
                        "precio_unitario": float(producto[2]),
                        "cantidad": producto[3],
                        "subtotal": float(producto[4])
                    })


                # =========================================
                # HISTORIAL
                # =========================================

                cur.execute("""
                    SELECT
                        e.codigo,
                        e.nombre,
                        h.observacion,
                        h.fecha

                    FROM historial_pedido h

                    JOIN estados_pedido e
                        ON e.id = h.estado_id

                    WHERE h.pedido_id = %s

                    ORDER BY h.fecha;
                """, (
                    pedido_id,
                ))

                historial = []

                for estado in cur.fetchall():

                    historial.append({
                        "codigo": estado[0],
                        "nombre": estado[1],
                        "observacion": estado[2],
                        "fecha": (
                            estado[3].isoformat()
                            if estado[3]
                            else None
                        )
                    })


                pedidos.append({

                    "id": fila[0],
                    "codigo": fila[1],

                    "estado": {
                        "codigo": fila[2],
                        "nombre": fila[3]
                    },

                    "cantidad_items": fila[4],

                    "subtotal": (
                        float(fila[5])
                        if fila[5] is not None
                        else 0
                    ),

                    "costo_delivery": (
                        float(fila[6])
                        if fila[6] is not None
                        else 0
                    ),

                    "total": (
                        float(fila[7])
                        if fila[7] is not None
                        else 0
                    ),

                    "distancia_km": (
                        float(fila[8])
                        if fila[8] is not None
                        else None
                    ),

                    "duracion_estimada_min": fila[9],

                    "tiempo_preparacion_estimado_min":
                        fila[10],

                    "tiempo_estimado_total_min":
                        fila[11],

                    "metodo_pago": fila[12],

                    "destinatario_nombre": fila[13],
                    "direccion_destino": fila[14],

                    "fecha_pedido": (
                        fila[15].isoformat()
                        if fila[15]
                        else None
                    ),

                    "fecha_entrega": (
                        fila[16].isoformat()
                        if fila[16]
                        else None
                    ),

                    "productos": productos,

                    "historial": historial
                })


    return jsonify({
        "ok": True,
        "total": len(pedidos),
        "pedidos": pedidos
    })


# =========================================================
# LISTAR TODOS
# ADMIN / OPERADOR
# =========================================================

@pedidos_bp.get("")
@roles_required("ADMIN", "OPERADOR")
def listar_pedidos():

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    p.id,
                    p.codigo,

                    e.codigo,
                    e.nombre,

                    p.destinatario_nombre,
                    p.destinatario_telefono,
                    p.direccion_destino,

                    p.cantidad_items,

                    p.subtotal,
                    p.costo_delivery,
                    p.total,

                    p.distancia_km,
                    p.duracion_estimada_min,
                    p.tiempo_preparacion_estimado_min,
                    p.tiempo_estimado_total_min,

                    p.metodo_pago,
                    p.indicaciones_entrega,

                    p.fecha_pedido,
                    p.fecha_entrega,
                    p.latitud_destino,
                    p.longitud_destino

                FROM pedidos p

                JOIN estados_pedido e
                    ON e.id = p.estado_id

                ORDER BY p.fecha_pedido DESC;
            """)

            filas = cur.fetchall()

            pedidos = []

            for fila in filas:

                pedido_id = fila[0]

                cur.execute("""
                    SELECT
                        producto_id,
                        nombre_producto,
                        precio_unitario,
                        cantidad,
                        subtotal

                    FROM detalle_pedido

                    WHERE pedido_id = %s

                    ORDER BY id;
                """, (
                    pedido_id,
                ))

                productos = []

                for producto in cur.fetchall():

                    productos.append({
                        "producto_id": producto[0],
                        "nombre": producto[1],
                        "precio_unitario": float(producto[2]),
                        "cantidad": producto[3],
                        "subtotal": float(producto[4])
                    })

                pedidos.append({

                    "id": fila[0],
                    "codigo": fila[1],

                    "estado": {
                        "codigo": fila[2],
                        "nombre": fila[3]
                    },

                    "destinatario_nombre": fila[4],
                    "destinatario_telefono": fila[5],
                    "direccion_destino": fila[6],

                    "cantidad_items": fila[7],

                    "subtotal": (
                        float(fila[8])
                        if fila[8] is not None
                        else 0
                    ),

                    "costo_delivery": (
                        float(fila[9])
                        if fila[9] is not None
                        else 0
                    ),

                    "total": (
                        float(fila[10])
                        if fila[10] is not None
                        else 0
                    ),

                    "distancia_km": (
                        float(fila[11])
                        if fila[11] is not None
                        else None
                    ),

                    "duracion_estimada_min": fila[12],

                    "tiempo_preparacion_estimado_min":
                        fila[13],

                    "tiempo_estimado_total_min":
                        fila[14],

                    "metodo_pago": fila[15],

                    "indicaciones_entrega": fila[16],

                    "fecha_pedido": (
                        fila[17].isoformat()
                        if fila[17]
                        else None
                    ),

                    "fecha_entrega": (
                        fila[18].isoformat()
                        if fila[18]
                        else None
                    ),
                    "latitud_destino": (
                        float(fila[19])
                        if fila[19] is not None
                        else None
                    ),

                    "longitud_destino": (
                        float(fila[20])
                        if fila[20] is not None
                        else None
                    ),

                    "productos": productos
                })

    return jsonify({
        "ok": True,
        "total": len(pedidos),
        "pedidos": pedidos
    })
# =========================================================
# ACTUALIZAR ESTADO DEL PEDIDO
# ADMIN / OPERADOR
# =========================================================

@pedidos_bp.patch("/<int:pedido_id>/estado")
@roles_required("ADMIN", "OPERADOR")
def actualizar_estado_pedido(pedido_id):

    datos = request.get_json(silent=True) or {}

    nuevo_estado = str(
        datos.get("estado", "")
    ).strip().upper()

    transiciones = {
        "REGISTRADO": "PREPARANDO",
        "PREPARANDO": "EN_RUTA",
        "EN_RUTA": "ENTREGADO"
    }

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    p.codigo,
                    e.codigo
                FROM pedidos p
                JOIN estados_pedido e
                    ON e.id = p.estado_id
                WHERE p.id = %s;
            """, (
                pedido_id,
            ))

            pedido = cur.fetchone()

            if not pedido:
                return jsonify({
                    "ok": False,
                    "mensaje": "Pedido no encontrado"
                }), 404

            codigo_pedido = pedido[0]
            estado_actual = pedido[1]

            if estado_actual == "ENTREGADO":
                return jsonify({
                    "ok": False,
                    "mensaje": "El pedido ya fue entregado"
                }), 409

            siguiente_estado = transiciones.get(
                estado_actual
            )

            if not siguiente_estado:
                return jsonify({
                    "ok": False,
                    "mensaje": (
                        f"No existe transición desde "
                        f"{estado_actual}"
                    )
                }), 409

            if nuevo_estado != siguiente_estado:
                return jsonify({
                    "ok": False,
                    "mensaje": (
                        f"El siguiente estado permitido es "
                        f"{siguiente_estado}"
                    )
                }), 409

            cur.execute("""
                SELECT id, nombre
                FROM estados_pedido
                WHERE codigo = %s;
            """, (
                nuevo_estado,
            ))

            estado = cur.fetchone()

            if not estado:
                return jsonify({
                    "ok": False,
                    "mensaje": "El estado solicitado no existe"
                }), 404

            nuevo_estado_id = estado[0]
            nuevo_estado_nombre = estado[1]

            if nuevo_estado == "PREPARANDO":

                cur.execute("""
                    UPDATE pedidos
                    SET
                        estado_id = %s,
                        fecha_confirmacion = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (
                    nuevo_estado_id,
                    pedido_id
                ))

            elif nuevo_estado == "EN_RUTA":

                cur.execute("""
                    UPDATE pedidos
                    SET
                        estado_id = %s,
                        fecha_recojo = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (
                    nuevo_estado_id,
                    pedido_id
                ))

            elif nuevo_estado == "ENTREGADO":

                cur.execute("""
                    UPDATE pedidos
                    SET
                        estado_id = %s,
                        fecha_entrega = CURRENT_TIMESTAMP
                    WHERE id = %s;
                """, (
                    nuevo_estado_id,
                    pedido_id
                ))

            mensajes = {
                "PREPARANDO": "Pedido en preparación",
                "EN_RUTA": "Pedido en camino",
                "ENTREGADO": "Pedido entregado"
            }

            cur.execute("""
                INSERT INTO historial_pedido (
                    pedido_id,
                    estado_id,
                    observacion,
                    usuario_id
                )
                VALUES (%s, %s, %s, %s);
            """, (
                pedido_id,
                nuevo_estado_id,
                mensajes[nuevo_estado],
                g.usuario["id"]
            ))

            cur.execute("""
                INSERT INTO auditoria (
                    usuario_id,
                    accion,
                    entidad,
                    entidad_id,
                    detalle
                )
                VALUES (%s, %s, %s, %s, %s);
            """, (
                g.usuario["id"],
                "CAMBIO_ESTADO_PEDIDO",
                "pedidos",
                pedido_id,
                f"{estado_actual} -> {nuevo_estado}"
            ))

        conn.commit()

    return jsonify({
        "ok": True,
        "mensaje": "Estado actualizado correctamente",
        "pedido": {
            "id": pedido_id,
            "codigo": codigo_pedido,
            "estado": {
                "codigo": nuevo_estado,
                "nombre": nuevo_estado_nombre
            }
        }
    })