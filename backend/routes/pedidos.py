import math
import os
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g

from db import get_connection
from backend.decorators import token_required, roles_required
from decimal import Decimal, ROUND_HALF_UP
from backend.ml_service import obtener_datos_ml, predecir_retraso
from backend.agentes_automaticos import (
    alertas_por_pedido,
    disparar_alerta_si_riesgo
)
from backend.repartidores import (
    estimar_espera_repartidor,
    repartidores_por_pedido
)
from backend.horario import mensaje_cerrado, tienda_abierta
from backend.ml_reentrenamiento import (
    iniciar_reentrenamiento_automatico,
    reentrenamiento_automatico_activo,
    reentrenar_manual
)


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

# Radio maximo de reparto (km) y velocidad maxima para validar rutas
RADIO_COBERTURA_POR_DEFECTO_KM = 10
VELOCIDAD_MAXIMA_KMH = 50


def radio_cobertura_km():

    try:
        return float(os.getenv(
            "RADIO_COBERTURA_KM",
            RADIO_COBERTURA_POR_DEFECTO_KM
        ))
    except ValueError:
        return float(RADIO_COBERTURA_POR_DEFECTO_KM)


def distancia_linea_recta_km(lat1, lon1, lat2, lon2):
    """Distancia en linea recta (formula de Haversine)."""

    radio_tierra_km = 6371.0

    fi1 = math.radians(lat1)
    fi2 = math.radians(lat2)
    delta_fi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_fi / 2) ** 2
        + math.cos(fi1) * math.cos(fi2) * math.sin(delta_lambda / 2) ** 2
    )

    return 2 * radio_tierra_km * math.asin(math.sqrt(a))


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
    # HORARIO DE ATENCION
    # =====================================================

    if not tienda_abierta():
        return jsonify({
            "ok": False,
            "cerrado": True,
            "mensaje": mensaje_cerrado()
        }), 409


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


    # =====================================================
    # VALIDAR LA DISTANCIA EN EL SERVIDOR
    #
    # La distancia de la ruta la calcula el navegador (Google
    # Maps) y define el costo del delivery: no se confia en ella.
    # Se compara con la distancia en linea recta entre la sede y
    # el destino (una ruta nunca es mas corta) y se aplica el
    # radio maximo de cobertura.
    # =====================================================

    distancia_recta_km = distancia_linea_recta_km(
        float(sede["latitud"]),
        float(sede["longitud"]),
        latitud_destino,
        longitud_destino
    )

    radio_maximo_km = radio_cobertura_km()

    if distancia_recta_km > radio_maximo_km:

        return jsonify({
            "ok": False,
            "mensaje": (
                f"Tu dirección está fuera de nuestra zona de "
                f"reparto (máximo {radio_maximo_km:g} km desde "
                f"la tienda)."
            )
        }), 400

    # Ruta menor que la linea recta = dato alterado: se corrige.
    if distancia_km < Decimal(str(round(distancia_recta_km, 2))):

        print(
            f"[SEGURIDAD] Distancia corregida para el usuario "
            f"{g.usuario['id']}: enviada {distancia_km} km, "
            f"linea recta {distancia_recta_km:.2f} km",
            flush=True
        )

        distancia_km = Decimal(
            str(round(distancia_recta_km, 2))
        )

    # Tiempo de ruta minimo razonable (como maximo ~50 km/h)
    duracion_minima_min = math.ceil(
        float(distancia_km) * 60 / VELOCIDAD_MAXIMA_KMH
    )

    if duracion_estimada_min < duracion_minima_min:
        duracion_estimada_min = duracion_minima_min


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


                # Si todos los repartidores estan en ruta, el pedido
                # espera a que uno vuelva: se suma al tiempo prometido.
                espera_repartidor = estimar_espera_repartidor(
                    tiempo_preparacion
                )["espera_min"]

                tiempo_estimado_total = (
                    tiempo_preparacion +
                    espera_repartidor +
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
                        espera_repartidor_min,

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

                        %s, %s, %s,

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
                    espera_repartidor,

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


                # Yape / Plin: numero de operacion que indica el cliente
                operacion = str(
                    datos.get("pago_operacion") or ""
                ).strip()[:30]

                if operacion and datos.get("metodo_pago") in ("YAPE", "PLIN"):
                    cur.execute("""
                        UPDATE pedidos
                        SET pago_operacion = %s
                        WHERE id = %s;
                    """, (
                        operacion,
                        pedido_id
                    ))

                                # =========================================
                # MACHINE LEARNING
                # =========================================

                # Contar pedidos reales que estaban activos
                # antes de este nuevo pedido.

                cur.execute("""
                    SELECT COUNT(*)

                    FROM pedidos p

                    JOIN estados_pedido e
                        ON e.id = p.estado_id

                    WHERE p.id <> %s

                      AND COALESCE(
                          p.fuente_datos,
                          'REAL'
                      ) = 'REAL'

                      AND e.codigo IN (
                          'REGISTRADO',
                          'PREPARANDO',
                          'EN_RUTA'
                      );
                """, (
                    pedido_id,
                ))

                pedidos_activos = (
                    cur.fetchone()[0]
                )


                # Guardar cuántos pedidos estaban activos
                # cuando se realizó este pedido.

                cur.execute("""
                    UPDATE pedidos

                    SET pedidos_activos_momento = %s

                    WHERE id = %s;
                """, (
                    pedidos_activos,
                    pedido_id
                ))


                # Obtener la fecha exacta registrada
                # por PostgreSQL.

                cur.execute("""
                    SELECT fecha_pedido

                    FROM pedidos

                    WHERE id = %s;
                """, (
                    pedido_id,
                ))

                fecha_pedido_ml = (
                    cur.fetchone()[0]
                )


                # Ejecutar modelo ML (API de ML en Google Cloud o modelo
                # local). Si falla, el pedido se registra igual sin
                # prediccion: la tienda no depende del servicio de ML.

                try:

                    prediccion_ml = predecir_retraso(

                        distancia_km=
                            distancia_km,

                        duracion_estimada_min=
                            duracion_estimada_min,

                        tiempo_preparacion_estimado_min=
                            tiempo_preparacion,

                        cantidad_items=
                            cantidad_items,

                        pedidos_activos=
                            pedidos_activos,

                        fecha_pedido=
                            fecha_pedido_ml
                    )

                except Exception as error:

                    print(
                        f"[ML] Pedido {pedido_id} sin prediccion: {error}",
                        flush=True
                    )

                    prediccion_ml = None


                if prediccion_ml is not None:

                    variables_ml = (
                        prediccion_ml[
                            "variables"
                        ]
                    )


                    # Guardar la predicción y las variables
                    # utilizadas por el modelo.

                    cur.execute("""
                        INSERT INTO predicciones_ml (

                            pedido_id,

                            modelo_version,
                            clase_predicha,
                            probabilidad_retraso,

                            distancia_km,
                            duracion_estimada_min,
                            tiempo_preparacion_estimado_min,
                            cantidad_items,

                            hora_pedido,
                            dia_semana,
                            hora_pico,
                            fin_semana,

                            pedidos_activos,
                            repartidores_disponibles,
                            carga_repartidor,

                            zona_origen,
                            zona_destino

                        )
                        VALUES (

                            %s,

                            %s,
                            %s,
                            %s,

                            %s,
                            %s,
                            %s,
                            %s,

                            %s,
                            %s,
                            %s,
                            %s,

                            %s,
                            %s,
                            %s,

                            %s,
                            %s
                        );
                    """, (

                        pedido_id,

                        prediccion_ml[
                            "modelo_version"
                        ],

                        prediccion_ml[
                            "clase_predicha"
                        ],

                        prediccion_ml[
                            "probabilidad_retraso"
                        ],

                        distancia_km,

                        duracion_estimada_min,

                        tiempo_preparacion,

                        cantidad_items,

                        variables_ml[
                            "hora_pedido"
                        ],

                        variables_ml[
                            "dia_semana"
                        ],

                        variables_ml[
                            "hora_pico"
                        ],

                        variables_ml[
                            "fin_semana"
                        ],

                        pedidos_activos,

                        variables_ml[
                            "repartidores"
                        ],

                        variables_ml[
                            "carga_repartidor"
                        ],

                        sede["nombre"],

                        datos.get(
                            "zona_destino"
                        )
                    ))


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


        # Sistema multiagente: si el modelo ML marca riesgo de
        # retraso, los agentes analizan el pedido en segundo plano.
        disparar_alerta_si_riesgo(
            pedido_id,
            prediccion_ml
        )


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
                    tiempo_estimado_total,

                "espera_repartidor_min":
                    espera_repartidor,

                "prediccion_ml": (
                    {

                        "clase":
                            prediccion_ml[
                                "clase_predicha"
                            ],

                        "probabilidad_retraso":
                            prediccion_ml[
                                "probabilidad_retraso"
                            ],

                        "probabilidad_porcentaje":
                            prediccion_ml[
                                "probabilidad_porcentaje"
                            ],

                        "modelo":
                            prediccion_ml[
                                "modelo_nombre"
                            ],

                        "version":
                            prediccion_ml[
                                "modelo_version"
                            ]
                    }

                    if prediccion_ml is not None

                    else None
                )
            }

        }), 201


    except Exception as error:

        # El detalle queda solo en el registro del servidor
        print(
            f"[ERROR] Crear pedido: {type(error).__name__}: {error}",
            flush=True
        )

        return jsonify({
            "ok": False,
            "mensaje": "No se pudo registrar el pedido. Inténtalo de nuevo."
        }), 500


# =========================================================
# ESPERA DE REPARTIDOR
# =========================================================

def esperas_por_pedido(pedido_ids):

    if not pedido_ids:
        return {}

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, espera_repartidor_min
                    FROM pedidos
                    WHERE id = ANY(%s);
                """, (list(pedido_ids),))

                return {fila[0]: fila[1] or 0 for fila in cur.fetchall()}

    except Exception:
        # Antes de la migracion la columna puede no existir.
        return {}


@pedidos_bp.get("/espera-estimada")
@token_required
def espera_estimada():
    """Vista previa para el resumen del pedido: cuanto esperaria a un
    repartidor libre con la preparacion indicada."""

    try:
        preparacion = max(int(request.args.get("preparacion", 0)), 0)
    except ValueError:
        preparacion = 0

    return jsonify({
        "ok": True,
        **estimar_espera_repartidor(preparacion)
    })


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


    # Aviso de los agentes si el pedido tiene riesgo de retraso
    avisos = alertas_por_pedido(
        [pedido["id"] for pedido in pedidos],
        solo_cliente=True
    )

    repartidores = repartidores_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    esperas = esperas_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    cancelaciones = cancelaciones_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    pagos = pagos_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    for pedido in pedidos:
        pedido["aviso"] = avisos.get(pedido["id"])
        pedido["espera_repartidor_min"] = esperas.get(pedido["id"], 0)
        pedido["cancelacion"] = cancelaciones.get(pedido["id"])
        pedido["pago"] = pagos.get(pedido["id"])

        repartidor = repartidores.get(pedido["id"])

        # Al cliente solo el nombre y el vehiculo de quien lo lleva.
        pedido["repartidor"] = (
            {
                "nombre": repartidor["nombre"],
                "tipo_vehiculo": repartidor["tipo_vehiculo"]
            }
            if repartidor
            else None
        )


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

    # Filtro por paso (estados) y paginacion. Sin parametros devuelve
    # todo, como antes. ?estados=ENTREGADO&limite=30&desde=0
    estados = [
        estado.strip().upper()
        for estado in request.args.get("estados", "").split(",")
        if estado.strip()
    ] or None

    try:
        limite = max(min(int(request.args.get("limite", 0)), 200), 0) or None
        desde = max(int(request.args.get("desde", 0)), 0)
    except ValueError:
        limite, desde = None, 0

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
                    p.longitud_destino,

                    pm.modelo_version,
                    pm.clase_predicha,
                    pm.probabilidad_retraso,
                    pm.fecha_prediccion,
                    p.duracion_real_min,
                    p.retraso,
                    COALESCE(
                        p.fuente_datos,
                        'REAL'
                    )

                FROM pedidos p

                JOIN estados_pedido e
                    ON e.id = p.estado_id

                LEFT JOIN LATERAL (

                SELECT
                    modelo_version,
                    clase_predicha,
                    probabilidad_retraso,
                    fecha_prediccion

                FROM predicciones_ml

                WHERE pedido_id = p.id

                ORDER BY id DESC

                LIMIT 1

            ) pm ON TRUE

                -- Los registros sinteticos (SINTETICO_ML) quedan
                -- en la BD pero no se muestran ni se usan.
                WHERE COALESCE(
                    p.fuente_datos,
                    'REAL'
                ) = 'REAL'

                  AND (
                      %(estados)s::text[] IS NULL
                      OR e.codigo = ANY(%(estados)s)
                  )

                ORDER BY p.fecha_pedido DESC

                LIMIT %(limite)s
                OFFSET %(desde)s;
            """, {
                "estados": estados,
                "limite": limite,
                "desde": desde
            })

            filas = cur.fetchall()


            # Productos de todos los pedidos en una sola
            # consulta (evita una consulta por pedido).

            cur.execute("""
                SELECT
                    pedido_id,
                    producto_id,
                    nombre_producto,
                    precio_unitario,
                    cantidad,
                    subtotal

                FROM detalle_pedido

                WHERE pedido_id = ANY(%s)

                ORDER BY pedido_id, id;
            """, (
                [fila[0] for fila in filas],
            ))

            productos_por_pedido = {}

            for producto in cur.fetchall():

                productos_por_pedido.setdefault(
                    producto[0],
                    []
                ).append({
                    "producto_id": producto[1],
                    "nombre": producto[2],
                    "precio_unitario": float(producto[3]),
                    "cantidad": producto[4],
                    "subtotal": float(producto[5])
                })

            pedidos = []

            for fila in filas:

                productos = productos_por_pedido.get(
                    fila[0],
                    []
                )

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

                    "prediccion_ml": (
                        {
                            "version": fila[21],

                            "clase": fila[22],

                            "probabilidad_retraso": (
                                float(fila[23])
                                if fila[23] is not None
                                else None
                            ),

                            "probabilidad_porcentaje": (
                                round(
                                    float(fila[23]) * 100,
                                    2
                                )
                                if fila[23] is not None
                                else None
                            ),

                            "fecha_prediccion": (
                                fila[24].isoformat()
                                if fila[24]
                                else None
                            )
                        }

                        if fila[22] is not None

                        else None
                    ),
                    "resultado_real": (
                    {
                        "duracion_real_min":
                            fila[25],

                        "retraso":
                            fila[26],

                        "clase": (
                            "RETRASADO"
                            if fila[26]
                            else "A_TIEMPO"
                        )
                    }

                    if fila[25] is not None
                    and fila[26] is not None

                    else None
                ),

                    "fuente_datos": fila[27],

                    "productos": productos
                })

    # Analisis del sistema multiagente (pedidos en riesgo)
    alertas = alertas_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    repartidores = repartidores_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    esperas = esperas_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    cancelaciones = cancelaciones_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    pagos = pagos_por_pedido(
        [pedido["id"] for pedido in pedidos]
    )

    for pedido in pedidos:
        pedido["alerta"] = alertas.get(pedido["id"])
        pedido["repartidor"] = repartidores.get(pedido["id"])
        pedido["espera_repartidor_min"] = esperas.get(pedido["id"], 0)
        pedido["cancelacion"] = cancelaciones.get(pedido["id"])
        pedido["pago"] = pagos.get(pedido["id"])

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

    return cambiar_estado_pedido(
        pedido_id,
        request.get_json(silent=True) or {}
    )


def cambiar_estado_pedido(pedido_id, datos):
    """Avanza el estado de un pedido. La usan el panel admin y el
    panel del repartidor (este solo para marcar ENTREGADO sus propios
    pedidos). El historial y la auditoria quedan a nombre de g.usuario."""

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
                    e.codigo,
                    p.repartidor_id
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

            # La entrega la confirma el repartidor desde su panel. El
            # admin solo puede marcarla si el pedido salio sin
            # repartidor asignado (si no, quedaria atascado).
            if (
                nuevo_estado == "ENTREGADO"
                and pedido[2] is not None
                and g.usuario["rol"] != "REPARTIDOR"
            ):
                return jsonify({
                    "ok": False,
                    "mensaje": (
                        "La entrega la marca el repartidor "
                        "desde su panel"
                    )
                }), 403

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

                # El admin confirma el repartidor (el panel sugiere al
                # que esta en turno con menos pedidos activos). Si aun
                # no hay repartidores registrados, se envia sin asignar.

                cur.execute("""
                    SELECT COUNT(*)
                    FROM repartidores
                    WHERE activo = TRUE;
                """)

                hay_repartidores = cur.fetchone()[0] > 0

                repartidor_id = datos.get("repartidor_id")

                if hay_repartidores and not repartidor_id:
                    return jsonify({
                        "ok": False,
                        "mensaje": "Selecciona el repartidor que llevará el pedido"
                    }), 400

                if repartidor_id:

                    cur.execute("""
                        SELECT u.nombre_completo
                        FROM repartidores r
                        JOIN usuarios u
                            ON u.id = r.usuario_id
                        WHERE r.id = %s
                          AND r.activo = TRUE;
                    """, (
                        repartidor_id,
                    ))

                    repartidor = cur.fetchone()

                    if not repartidor:
                        return jsonify({
                            "ok": False,
                            "mensaje": "El repartidor no existe o está inactivo"
                        }), 400

                    nombre_repartidor = repartidor[0]

                cur.execute("""
                    UPDATE pedidos
                    SET
                        estado_id = %s,
                        fecha_recojo = CURRENT_TIMESTAMP,
                        repartidor_id = %s,
                        fecha_asignacion = CASE
                            WHEN %s::bigint IS NULL THEN fecha_asignacion
                            ELSE CURRENT_TIMESTAMP
                        END
                    WHERE id = %s;
                """, (
                    nuevo_estado_id,
                    repartidor_id,
                    repartidor_id,
                    pedido_id
                ))

            elif nuevo_estado == "ENTREGADO":

                cur.execute("""
                    UPDATE pedidos

                    SET
                        estado_id = %s,

                        fecha_entrega =
                            CURRENT_TIMESTAMP,

                        duracion_real_min =
                            CEIL(
                                EXTRACT(
                                    EPOCH FROM (
                                        CURRENT_TIMESTAMP
                                        - fecha_pedido
                                    )
                                ) / 60.0
                            )::integer,

                        retraso = (
                            EXTRACT(
                                EPOCH FROM (
                                    CURRENT_TIMESTAMP
                                    - fecha_pedido
                                )
                            ) / 60.0
                            >
                            (
                                COALESCE(
                                    tiempo_estimado_total_min,
                                    duracion_estimada_min,
                                    0
                                )
                                + 5
                            )
                        ),

                        -- Efectivo: el repartidor lo cobra al entregar
                        pago_estado = CASE
                            WHEN metodo_pago = 'EFECTIVO' THEN 'PAGADO'
                            ELSE pago_estado
                        END,

                        fecha_pago = CASE
                            WHEN metodo_pago = 'EFECTIVO' THEN CURRENT_TIMESTAMP
                            ELSE fecha_pago
                        END

                    WHERE id = %s;
                """, (
                    nuevo_estado_id,
                    pedido_id
                ))

            mensajes = {
                "PREPARANDO": "Pedido en preparación",
                "EN_RUTA": (
                    f"Pedido en camino con {nombre_repartidor}"
                    if nuevo_estado == "EN_RUTA"
                    and datos.get("repartidor_id")
                    else "Pedido en camino"
                ),
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

    # Un pedido entregado aporta un resultado real nuevo:
    # reentrenar en segundo plano (no retrasa esta respuesta).
    if (
        nuevo_estado == "ENTREGADO"
        and reentrenamiento_automatico_activo()
    ):
        iniciar_reentrenamiento_automatico()

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

# =========================================================
# DASHBOARD ML
# ADMIN / OPERADOR
# =========================================================

# v1.0 se entreno con datos sinteticos (descartado): sus
# predicciones no cuentan en el rendimiento con pedidos reales.
VERSIONES_DESCARTADAS = ("v1.0",)


def _dividir(numerador, denominador):

    return (
        round(numerador / denominador, 4)
        if denominador
        else None
    )


@pedidos_bp.get("/ml/resumen")
@roles_required("ADMIN", "OPERADOR")
def resumen_ml():

    # -----------------------------------------
    # Evaluación del modelo: API de ML (Google
    # Cloud) o archivos locales en desarrollo
    # -----------------------------------------

    try:

        datos_ml = obtener_datos_ml()

    except Exception as error:

        datos_ml = {
            "metricas": None,
            "historial": [],
            "estado": {
                "resultado": "ERROR",
                "mensaje": f"API de ML no disponible: {error}",
                "fin": None
            }
        }

    modelo = None

    metricas = datos_ml.get("metricas")

    if metricas:

        seleccionado = metricas[
            "modelo_seleccionado"
        ]

        resultado = metricas["resultados"][
            seleccionado
        ]

        modelo = {
            "nombre": seleccionado,
            "version": metricas.get("version_modelo"),
            "criterio": metricas.get("criterio_seleccion"),
            "fecha_entrenamiento": metricas.get(
                "fecha_entrenamiento_utc"
            ),
            "dataset": metricas.get("dataset"),
            "variables": metricas.get("variables", []),
            "fuente_dataset": metricas.get("fuente_dataset"),

            "accuracy": resultado["accuracy_test"],
            "precision": resultado["precision_test"],
            "recall": resultado["recall_test"],
            "f1": resultado["f1_test"],
            "roc_auc": resultado["roc_auc_test"],
            "matriz_confusion": resultado["matriz_confusion"],

            "comparacion": [
                {
                    "modelo": nombre,
                    "f1_cv": datos["f1_cv_promedio"],
                    "accuracy": datos["accuracy_test"],
                    "precision": datos["precision_test"],
                    "recall": datos["recall_test"],
                    "f1": datos["f1_test"],
                    "roc_auc": datos["roc_auc_test"]
                }
                for nombre, datos
                in metricas["resultados"].items()
            ]
        }


    # -----------------------------------------
    # Rendimiento en pedidos reales
    # -----------------------------------------

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    pm.clase_predicha,
                    p.retraso,
                    p.duracion_real_min,

                    p.codigo,
                    p.fecha_pedido,
                    pm.probabilidad_retraso,
                    pm.modelo_version,
                    p.tiempo_estimado_total_min

                FROM pedidos p

                LEFT JOIN LATERAL (

                    SELECT
                        clase_predicha,
                        probabilidad_retraso,
                        modelo_version

                    FROM predicciones_ml

                    WHERE pedido_id = p.id
                      AND modelo_version <> ALL(%s)

                    ORDER BY id DESC

                    LIMIT 1

                ) pm ON TRUE

                WHERE COALESCE(
                    p.fuente_datos,
                    'REAL'
                ) = 'REAL'

                ORDER BY p.fecha_pedido DESC;
            """, (
                list(VERSIONES_DESCARTADAS),
            ))

            filas = cur.fetchall()


    con_prediccion = [
        fila for fila in filas
        if fila[0] is not None
    ]

    evaluados = [
        fila for fila in con_prediccion
        if fila[1] is not None
        and fila[2] is not None
    ]

    # Filas = real (0 A_TIEMPO, 1 RETRASADO)
    # Columnas = predicho (0 A_TIEMPO, 1 RETRASADO)
    matriz = [[0, 0], [0, 0]]

    for fila in evaluados:

        real = 1 if fila[1] else 0
        predicho = 1 if fila[0] == "RETRASADO" else 0

        matriz[real][predicho] += 1


    # Pedido por pedido (los 20 más recientes con predicción).
    detalle = []

    for fila in con_prediccion[:20]:

        entregado = fila[1] is not None and fila[2] is not None

        resultado_real = (
            ("RETRASADO" if fila[1] else "A_TIEMPO")
            if entregado
            else None
        )

        detalle.append({
            "codigo": fila[3],
            "fecha_pedido": fila[4].isoformat() if fila[4] else None,
            "prediccion": fila[0],
            "probabilidad_porcentaje": (
                round(float(fila[5]) * 100, 2)
                if fila[5] is not None
                else None
            ),
            "modelo_version": fila[6],
            "tiempo_estimado_min": fila[7],
            "duracion_real_min": fila[2],
            "resultado_real": resultado_real,
            "acerto": (
                fila[0] == resultado_real
                if entregado
                else None
            )
        })

    vn, fp = matriz[0]
    fn, vp = matriz[1]

    correctas = vn + vp
    precision = _dividir(vp, vp + fp)
    recall = _dividir(vp, vp + fn)

    reales = {
        "pedidos_reales": len(filas),

        # Entregados con resultado real: los que entran
        # al dataset en un reentrenamiento.
        "entregados_con_resultado": sum(
            1 for fila in filas
            if fila[1] is not None
            and fila[2] is not None
        ),
        "con_prediccion": len(con_prediccion),
        "evaluados": len(evaluados),
        "pendientes": len(con_prediccion) - len(evaluados),

        "correctas": correctas,
        "incorrectas": len(evaluados) - correctas,

        "predichos_a_tiempo": vn + fn,
        "predichos_retrasado": fp + vp,
        "reales_a_tiempo": vn + fp,
        "reales_retrasados": fn + vp,

        "matriz_confusion": matriz,
        "detalle": detalle,

        "accuracy": _dividir(correctas, len(evaluados)),
        "precision": precision,
        "recall": recall,
        "f1": (
            _dividir(
                2 * vp,
                2 * vp + fp + fn
            )
            if precision is not None
            and recall is not None
            else None
        )
    }

    return jsonify({
        "ok": True,
        "modelo": modelo,
        "reales": reales,
        "reentrenamiento": datos_ml.get("estado", {}),
        "historial": datos_ml.get("historial", [])
    })


@pedidos_bp.post("/ml/reentrenar")
@roles_required("ADMIN")
def reentrenar_ml():

    resultado = reentrenar_manual()

    if resultado is None:

        return jsonify({
            "ok": False,
            "mensaje": "Ya hay un reentrenamiento en curso."
        }), 409

    if resultado["resultado"] == "ERROR":

        return jsonify({
            "ok": False,
            "mensaje": resultado["mensaje"],
            "detalle": resultado["detalle"]
        }), 500

    return jsonify({
        "ok": True,
        "resultado": resultado["resultado"],
        "mensaje": resultado["mensaje"]
    })



# =========================================================
# CANCELAR PEDIDO
#
# - Cliente: solo sus pedidos y mientras esten "Recibidos".
# - Admin / Operador: antes de enviarlos (Recibido o En
#   preparacion), con un motivo.
# =========================================================

_COLUMNAS_CANCELACION = {"ok": False}


def asegurar_columnas_cancelacion():
    """Columnas motivo_cancelacion y cancelado_por. Se llama al
    arrancar la app (nunca dentro de una operacion de pedido)."""

    if _COLUMNAS_CANCELACION["ok"]:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'pedidos'
                  AND column_name IN ('motivo_cancelacion', 'cancelado_por');
            """)

            if cur.fetchone()[0] < 2:
                ruta = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "sql",
                    "agregar_cancelacion.sql",
                )

                with open(ruta, encoding="utf-8") as archivo:
                    cur.execute(archivo.read())

    _COLUMNAS_CANCELACION["ok"] = True


def cancelaciones_por_pedido(pedido_ids):

    if not pedido_ids:
        return {}

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.id, p.motivo_cancelacion, p.cancelado_por, p.fecha_cancelacion
                    FROM pedidos p
                    JOIN estados_pedido e ON e.id = p.estado_id
                    WHERE p.id = ANY(%s)
                      AND e.codigo = 'CANCELADO';
                """, (list(pedido_ids),))

                return {
                    fila[0]: {
                        "motivo": fila[1],
                        "por": fila[2],
                        "fecha": fila[3].isoformat() if fila[3] else None,
                    }
                    for fila in cur.fetchall()
                }

    except Exception:
        # Antes de la migracion las columnas pueden no existir.
        return {}


@pedidos_bp.post("/<int:pedido_id>/cancelar")
@token_required
def cancelar_pedido(pedido_id):

    datos = request.get_json(silent=True) or {}
    motivo = str(datos.get("motivo", "")).strip()[:200]
    rol = g.usuario["rol"]

    if rol not in ("CLIENTE", "ADMIN", "OPERADOR"):
        return jsonify({"ok": False, "mensaje": "No tiene permisos para cancelar pedidos"}), 403

    if rol != "CLIENTE" and len(motivo) < 3:
        return jsonify({"ok": False, "mensaje": "Indica el motivo de la cancelación"}), 400

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT p.codigo, p.cliente_id, e.codigo
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE p.id = %s
                FOR UPDATE OF p;
            """, (pedido_id,))

            pedido = cur.fetchone()

            if not pedido or (rol == "CLIENTE" and pedido[1] != g.usuario["id"]):
                return jsonify({"ok": False, "mensaje": "Pedido no encontrado"}), 404

            codigo_pedido, _, estado_actual = pedido

            permitidos = ("REGISTRADO",) if rol == "CLIENTE" else ("REGISTRADO", "PREPARANDO")

            if estado_actual not in permitidos:
                return jsonify({
                    "ok": False,
                    "mensaje": (
                        "Este pedido ya no se puede cancelar porque está en "
                        "preparación, en camino o finalizado. Comunícate con la tienda."
                        if rol == "CLIENTE"
                        else "Solo se pueden cancelar pedidos que aún no salieron a reparto"
                    )
                }), 409

            cur.execute("SELECT id FROM estados_pedido WHERE codigo = 'CANCELADO';")
            cancelado_id = cur.fetchone()[0]

            por = "CLIENTE" if rol == "CLIENTE" else "TIENDA"
            motivo = motivo or "Sin motivo indicado"

            cur.execute("""
                UPDATE pedidos
                SET estado_id = %s,
                    fecha_cancelacion = CURRENT_TIMESTAMP,
                    motivo_cancelacion = %s,
                    cancelado_por = %s
                WHERE id = %s;
            """, (cancelado_id, motivo, por, pedido_id))

            cur.execute("""
                INSERT INTO historial_pedido (pedido_id, estado_id, observacion, usuario_id)
                VALUES (%s, %s, %s, %s);
            """, (
                pedido_id,
                cancelado_id,
                f"Cancelado por {'el cliente' if por == 'CLIENTE' else 'la tienda'}: {motivo}",
                g.usuario["id"],
            ))

            cur.execute("""
                INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                VALUES (%s, 'CANCELAR_PEDIDO', 'pedidos', %s, %s);
            """, (g.usuario["id"], pedido_id, f"{estado_actual} -> CANCELADO: {motivo}"))

        conn.commit()

    return jsonify({
        "ok": True,
        "mensaje": f"Pedido {codigo_pedido} cancelado",
        "pedido": {"id": pedido_id, "codigo": codigo_pedido, "estado": "CANCELADO"}
    })



# =========================================================
# CONTEO DE PEDIDOS POR ESTADO (modulos del panel)
# =========================================================

@pedidos_bp.get("/conteo")
@roles_required("ADMIN", "OPERADOR")
def conteo_pedidos():

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.codigo, COUNT(*)
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE COALESCE(p.fuente_datos, 'REAL') = 'REAL'
                GROUP BY e.codigo;
            """)

            conteo = dict(cur.fetchall())

    return jsonify({"ok": True, "conteo": conteo})



# =========================================================
# PAGOS (Yape / Plin: el admin confirma; Efectivo: al entregar)
# =========================================================

_COLUMNAS_PAGO = {"ok": False}


def asegurar_columnas_pago():
    """Columnas del estado del pago. Se llama al arrancar la app."""

    if _COLUMNAS_PAGO["ok"]:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'pedidos'
                  AND column_name IN ('pago_estado', 'pago_operacion',
                                      'pago_confirmado_por', 'fecha_pago');
            """)

            if cur.fetchone()[0] < 4:
                ruta = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "sql",
                    "agregar_pagos.sql",
                )

                with open(ruta, encoding="utf-8") as archivo:
                    cur.execute(archivo.read())

    _COLUMNAS_PAGO["ok"] = True


def pagos_por_pedido(pedido_ids):

    if not pedido_ids:
        return {}

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, metodo_pago, pago_estado, pago_operacion, fecha_pago
                    FROM pedidos
                    WHERE id = ANY(%s);
                """, (list(pedido_ids),))

                return {
                    fila[0]: {
                        "metodo": fila[1],
                        "estado": fila[2],
                        "operacion": fila[3],
                        "fecha": fila[4].isoformat() if fila[4] else None,
                    }
                    for fila in cur.fetchall()
                }

    except Exception:
        return {}


@pedidos_bp.post("/<int:pedido_id>/pago/confirmar")
@roles_required("ADMIN", "OPERADOR")
def confirmar_pago(pedido_id):
    """El admin vio el pago en su aplicacion Yape/Plin y lo confirma.
    Puede registrar el numero de operacion si el cliente no lo envio."""

    operacion = str((request.get_json(silent=True) or {}).get("operacion", "")).strip()[:30]

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT p.codigo, p.metodo_pago, p.pago_estado, e.codigo
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE p.id = %s;
            """, (pedido_id,))

            pedido = cur.fetchone()

            if not pedido:
                return jsonify({"ok": False, "mensaje": "Pedido no encontrado"}), 404

            if pedido[1] not in ("YAPE", "PLIN"):
                return jsonify({"ok": False, "mensaje": "El efectivo se cobra al entregar"}), 400

            if pedido[3] == "CANCELADO":
                return jsonify({"ok": False, "mensaje": "El pedido está cancelado"}), 409

            if pedido[2] == "PAGADO":
                return jsonify({"ok": True, "mensaje": "El pago ya estaba confirmado"})

            cur.execute("""
                UPDATE pedidos
                SET pago_estado = 'PAGADO',
                    fecha_pago = CURRENT_TIMESTAMP,
                    pago_confirmado_por = %s,
                    pago_operacion = COALESCE(NULLIF(%s, ''), pago_operacion)
                WHERE id = %s;
            """, (g.usuario["id"], operacion, pedido_id))

            cur.execute("""
                INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                VALUES (%s, 'CONFIRMAR_PAGO', 'pedidos', %s, %s);
            """, (g.usuario["id"], pedido_id, f"{pedido[1]} {operacion}".strip()))

        conn.commit()

    return jsonify({"ok": True, "mensaje": f"Pago del pedido {pedido[0]} confirmado"})


@pedidos_bp.post("/<int:pedido_id>/pago/operacion")
@token_required
def enviar_operacion(pedido_id):
    """El cliente envia el numero de operacion de Yape/Plin despues."""

    operacion = str((request.get_json(silent=True) or {}).get("operacion", "")).strip()[:30]

    if len(operacion) < 4:
        return jsonify({"ok": False, "mensaje": "Escribe el número de operación"}), 400

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT p.cliente_id, p.metodo_pago, p.pago_estado, e.codigo
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE p.id = %s;
            """, (pedido_id,))

            pedido = cur.fetchone()

            if not pedido or pedido[0] != g.usuario["id"]:
                return jsonify({"ok": False, "mensaje": "Pedido no encontrado"}), 404

            if pedido[1] not in ("YAPE", "PLIN") or pedido[2] == "PAGADO" or pedido[3] == "CANCELADO":
                return jsonify({"ok": False, "mensaje": "Este pedido no necesita número de operación"}), 409

            cur.execute(
                "UPDATE pedidos SET pago_operacion = %s WHERE id = %s;",
                (operacion, pedido_id),
            )

        conn.commit()

    return jsonify({"ok": True, "mensaje": "Número de operación enviado. La tienda confirmará tu pago."})
