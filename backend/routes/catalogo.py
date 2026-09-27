from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request

from db import get_connection
from backend.decorators import roles_required


catalogo_bp = Blueprint(
    "catalogo",
    __name__,
    url_prefix="/api/catalogo"
)


# =========================================================
# CATÁLOGO PÚBLICO
# =========================================================

@catalogo_bp.get("")
def obtener_catalogo():

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    c.id,
                    c.nombre,
                    c.descripcion,

                    p.id,
                    p.nombre,
                    p.descripcion,
                    p.precio,
                    p.tiempo_preparacion_min,
                    p.imagen_url,
                    p.disponible

                FROM categorias_producto c

                LEFT JOIN productos p
                    ON p.categoria_id = c.id
                    AND p.activo = TRUE

                WHERE c.activa = TRUE

                ORDER BY
                    c.orden,
                    c.nombre,
                    p.nombre;
            """)

            filas = cur.fetchall()

    categorias = {}

    for fila in filas:

        categoria_id = fila[0]

        if categoria_id not in categorias:
            categorias[categoria_id] = {
                "id": categoria_id,
                "nombre": fila[1],
                "descripcion": fila[2],
                "productos": []
            }

        if fila[3] is not None:
            categorias[categoria_id]["productos"].append({
                "id": fila[3],
                "nombre": fila[4],
                "descripcion": fila[5],
                "precio": float(fila[6]),
                "tiempo_preparacion_min": fila[7],
                "imagen_url": fila[8],
                "disponible": fila[9]
            })

    return jsonify({
        "ok": True,
        "categorias": list(categorias.values())
    })


# =========================================================
# CREAR CATEGORÍA
# ADMIN
# =========================================================

@catalogo_bp.post("/categorias")
@roles_required("ADMIN")
def crear_categoria():

    datos = request.get_json(silent=True) or {}

    nombre = str(
        datos.get("nombre", "")
    ).strip()

    descripcion = str(
        datos.get("descripcion", "")
    ).strip()

    orden = datos.get("orden", 0)

    if not nombre:
        return jsonify({
            "ok": False,
            "mensaje": "El nombre de la categoría es obligatorio"
        }), 400

    try:
        orden = int(orden)

    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "mensaje": "El orden debe ser un número entero"
        }), 400

    try:

        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO categorias_producto (
                        nombre,
                        descripcion,
                        orden
                    )
                    VALUES (%s, %s, %s)
                    RETURNING id;
                """, (
                    nombre,
                    descripcion or None,
                    orden
                ))

                categoria_id = cur.fetchone()[0]

            conn.commit()

        return jsonify({
            "ok": True,
            "mensaje": "Categoría creada correctamente",
            "categoria_id": categoria_id
        }), 201

    except Exception as error:

        if "categorias_producto_nombre_key" in str(error):
            return jsonify({
                "ok": False,
                "mensaje": "Ya existe una categoría con ese nombre"
            }), 409

        return jsonify({
            "ok": False,
            "mensaje": "No se pudo crear la categoría"
        }), 500


# =========================================================
# CREAR PRODUCTO
# ADMIN
# =========================================================

@catalogo_bp.post("/productos")
@roles_required("ADMIN")
def crear_producto():

    datos = request.get_json(silent=True) or {}

    nombre = str(
        datos.get("nombre", "")
    ).strip()

    descripcion = str(
        datos.get("descripcion", "")
    ).strip()

    categoria_id = datos.get(
        "categoria_id"
    )

    precio_texto = datos.get(
        "precio"
    )

    tiempo_preparacion = datos.get(
        "tiempo_preparacion_min",
        10
    )

    imagen_url = str(
        datos.get("imagen_url", "")
    ).strip()

    if not nombre:
        return jsonify({
            "ok": False,
            "mensaje": "El nombre del producto es obligatorio"
        }), 400

    if categoria_id is None:
        return jsonify({
            "ok": False,
            "mensaje": "La categoría es obligatoria"
        }), 400

    try:
        categoria_id = int(
            categoria_id
        )

        precio = Decimal(
            str(precio_texto)
        )

        tiempo_preparacion = int(
            tiempo_preparacion
        )

    except (
        ValueError,
        TypeError,
        InvalidOperation
    ):
        return jsonify({
            "ok": False,
            "mensaje": "Precio, categoría o tiempo de preparación inválidos"
        }), 400

    if precio < 0:
        return jsonify({
            "ok": False,
            "mensaje": "El precio no puede ser negativo"
        }), 400

    if tiempo_preparacion < 0:
        return jsonify({
            "ok": False,
            "mensaje": "El tiempo de preparación no puede ser negativo"
        }), 400

    try:

        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    SELECT id
                    FROM categorias_producto
                    WHERE id = %s
                    AND activa = TRUE;
                """, (
                    categoria_id,
                ))

                categoria = cur.fetchone()

                if not categoria:
                    return jsonify({
                        "ok": False,
                        "mensaje": "La categoría seleccionada no existe"
                    }), 404

                cur.execute("""
                    INSERT INTO productos (
                        categoria_id,
                        nombre,
                        descripcion,
                        precio,
                        tiempo_preparacion_min,
                        imagen_url,
                        disponible,
                        activo
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        TRUE,
                        TRUE
                    )
                    RETURNING id;
                """, (
                    categoria_id,
                    nombre,
                    descripcion or None,
                    precio,
                    tiempo_preparacion,
                    imagen_url or None
                ))

                producto_id = cur.fetchone()[0]

            conn.commit()

        return jsonify({
            "ok": True,
            "mensaje": "Producto creado correctamente",
            "producto_id": producto_id
        }), 201

    except Exception as error:

        return jsonify({
            "ok": False,
            "mensaje": "No se pudo crear el producto",
            "detalle": str(error)
        }), 500


# =========================================================
# CAMBIAR DISPONIBILIDAD
# ADMIN / OPERADOR
# =========================================================

@catalogo_bp.patch("/productos/<int:producto_id>/disponibilidad")
@roles_required(
    "ADMIN",
    "OPERADOR"
)
def cambiar_disponibilidad(
    producto_id
):

    datos = request.get_json(
        silent=True
    ) or {}

    disponible = datos.get(
        "disponible"
    )

    if not isinstance(
        disponible,
        bool
    ):
        return jsonify({
            "ok": False,
            "mensaje": "El campo disponible debe ser true o false"
        }), 400

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                UPDATE productos
                SET
                    disponible = %s,
                    fecha_actualizacion =
                        CURRENT_TIMESTAMP
                WHERE id = %s
                AND activo = TRUE
                RETURNING
                    id,
                    nombre,
                    disponible;
            """, (
                disponible,
                producto_id
            ))

            producto = cur.fetchone()

        conn.commit()

    if not producto:
        return jsonify({
            "ok": False,
            "mensaje": "Producto no encontrado"
        }), 404

    return jsonify({
        "ok": True,
        "mensaje": (
            "Producto disponible"
            if producto[2]
            else "Producto marcado como agotado"
        ),
        "producto": {
            "id": producto[0],
            "nombre": producto[1],
            "disponible": producto[2]
        }
    })


# =========================================================
# DESACTIVAR PRODUCTO
# ADMIN
# =========================================================

@catalogo_bp.patch("/productos/<int:producto_id>/desactivar")
@roles_required("ADMIN")
def desactivar_producto(
    producto_id
):

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                UPDATE productos
                SET
                    activo = FALSE,
                    disponible = FALSE,
                    fecha_actualizacion =
                        CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, nombre;
            """, (
                producto_id,
            ))

            producto = cur.fetchone()

        conn.commit()

    if not producto:
        return jsonify({
            "ok": False,
            "mensaje": "Producto no encontrado"
        }), 404

    return jsonify({
        "ok": True,
        "mensaje": "Producto desactivado",
        "producto": {
            "id": producto[0],
            "nombre": producto[1]
        }
    })

# =========================================================
# EDITAR PRODUCTO
# ADMIN
# =========================================================

@catalogo_bp.patch("/productos/<int:producto_id>")
@roles_required("ADMIN")
def editar_producto(producto_id):

    datos = request.get_json(silent=True) or {}

    nombre = str(
        datos.get("nombre", "")
    ).strip()

    descripcion = str(
        datos.get("descripcion", "")
    ).strip()

    categoria_id = datos.get(
        "categoria_id"
    )

    precio_texto = datos.get(
        "precio"
    )

    tiempo_preparacion = datos.get(
        "tiempo_preparacion_min"
    )

    imagen_url = str(
        datos.get("imagen_url", "")
    ).strip()


    # =====================================================
    # VALIDACIONES
    # =====================================================

    if not nombre:

        return jsonify({
            "ok": False,
            "mensaje": "El nombre del producto es obligatorio"
        }), 400


    try:

        categoria_id = int(
            categoria_id
        )

        precio = Decimal(
            str(precio_texto)
        )

        tiempo_preparacion = int(
            tiempo_preparacion
        )

    except (
        ValueError,
        TypeError,
        InvalidOperation
    ):

        return jsonify({
            "ok": False,
            "mensaje":
                "Categoría, precio o tiempo de preparación inválidos"
        }), 400


    if precio < 0:

        return jsonify({
            "ok": False,
            "mensaje": "El precio no puede ser negativo"
        }), 400


    if tiempo_preparacion < 0:

        return jsonify({
            "ok": False,
            "mensaje":
                "El tiempo de preparación no puede ser negativo"
        }), 400


    try:

        with get_connection() as conn:
            with conn.cursor() as cur:

                # =========================================
                # VALIDAR CATEGORÍA
                # =========================================

                cur.execute("""
                    SELECT id
                    FROM categorias_producto
                    WHERE id = %s
                    AND activa = TRUE;
                """, (
                    categoria_id,
                ))

                categoria = cur.fetchone()


                if not categoria:

                    return jsonify({
                        "ok": False,
                        "mensaje":
                            "La categoría seleccionada no existe"
                    }), 404


                # =========================================
                # ACTUALIZAR PRODUCTO
                # =========================================

                cur.execute("""
                    UPDATE productos

                    SET
                        categoria_id = %s,
                        nombre = %s,
                        descripcion = %s,
                        precio = %s,
                        tiempo_preparacion_min = %s,
                        imagen_url = %s,
                        fecha_actualizacion =
                            CURRENT_TIMESTAMP

                    WHERE id = %s
                    AND activo = TRUE

                    RETURNING
                        id,
                        nombre,
                        precio,
                        disponible;
                """, (

                    categoria_id,
                    nombre,
                    descripcion or None,
                    precio,
                    tiempo_preparacion,
                    imagen_url or None,
                    producto_id

                ))


                producto = cur.fetchone()


                if not producto:

                    return jsonify({
                        "ok": False,
                        "mensaje":
                            "Producto no encontrado"
                    }), 404


            conn.commit()


        return jsonify({

            "ok": True,

            "mensaje":
                "Producto actualizado correctamente",

            "producto": {
                "id": producto[0],
                "nombre": producto[1],
                "precio": float(producto[2]),
                "disponible": producto[3]
            }

        })


    except Exception as error:

        return jsonify({
            "ok": False,
            "mensaje":
                "No se pudo actualizar el producto",
            "detalle":
                str(error)
        }), 500