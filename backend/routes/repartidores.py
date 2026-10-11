import secrets

from flask import Blueprint, g, jsonify, request
from werkzeug.security import generate_password_hash

from db import get_connection
from backend.decorators import roles_required
from backend.repartidores import (
    asegurar_columna_turno,
    listar_repartidores,
    sugerir_repartidor,
)


repartidores_bp = Blueprint(
    "repartidores",
    __name__,
    url_prefix="/api/repartidores"
)


VEHICULOS = ("MOTO", "BICICLETA", "AUTO", "CAMIONETA", "OTRO")


@repartidores_bp.get("")
@roles_required("ADMIN", "OPERADOR")
def obtener_repartidores():

    repartidores = listar_repartidores()
    sugerido = sugerir_repartidor(repartidores)

    return jsonify({
        "ok": True,
        "repartidores": repartidores,
        "sugerido_id": sugerido["id"] if sugerido else None
    })


@repartidores_bp.post("")
@roles_required("ADMIN")
def crear_repartidor():
    """Registra un repartidor. Por ahora no inicia sesion (el admin le
    asigna los pedidos y marca las entregas): se crea su usuario con
    rol REPARTIDOR y una contrasena aleatoria."""

    datos = request.get_json(silent=True) or {}

    nombre = str(datos.get("nombre", "")).strip()
    telefono = str(datos.get("telefono", "")).strip() or None
    vehiculo = str(datos.get("tipo_vehiculo", "MOTO")).strip().upper()
    placa = str(datos.get("placa", "")).strip().upper() or None

    if len(nombre) < 3:
        return jsonify({"ok": False, "mensaje": "Ingresa el nombre del repartidor"}), 400

    if vehiculo not in VEHICULOS:
        return jsonify({"ok": False, "mensaje": "Tipo de vehiculo no valido"}), 400

    asegurar_columna_turno()

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM repartidores;")
            numero = cur.fetchone()[0]
            codigo = f"REP-{numero:03d}"

            cur.execute("""
                INSERT INTO usuarios (
                    nombre_completo, correo, password_hash, telefono, rol
                )
                VALUES (%s, %s, %s, %s, 'REPARTIDOR')
                RETURNING id;
            """, (
                nombre,
                f"{codigo.lower()}.{secrets.token_hex(3)}@repartidores.kimbos",
                generate_password_hash(secrets.token_urlsafe(16)),
                telefono,
            ))

            usuario_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO repartidores (
                    usuario_id, codigo, tipo_vehiculo, placa, en_turno
                )
                VALUES (%s, %s, %s, %s, TRUE)
                RETURNING id;
            """, (usuario_id, codigo, vehiculo, placa))

            repartidor_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                VALUES (%s, 'CREAR', 'repartidores', %s, %s);
            """, (g.usuario["id"], repartidor_id, f"Repartidor {codigo}: {nombre}"))

        conn.commit()

    return jsonify({
        "ok": True,
        "mensaje": f"Repartidor {nombre} registrado ({codigo})",
        "id": repartidor_id
    }), 201


@repartidores_bp.patch("/<int:repartidor_id>")
@roles_required("ADMIN", "OPERADOR")
def actualizar_repartidor(repartidor_id):
    """Turno (ADMIN u OPERADOR) y datos/activo (solo ADMIN)."""

    datos = request.get_json(silent=True) or {}

    cambios_repartidor = {}
    cambios_usuario = {}

    if "en_turno" in datos:
        cambios_repartidor["en_turno"] = bool(datos["en_turno"])

    solo_admin = {"activo", "tipo_vehiculo", "placa", "nombre", "telefono"}

    if solo_admin & set(datos) and g.usuario["rol"] != "ADMIN":
        return jsonify({"ok": False, "mensaje": "Solo el administrador puede editar repartidores"}), 403

    if "activo" in datos:
        cambios_repartidor["activo"] = bool(datos["activo"])

        # Un repartidor inactivo no queda en turno.
        if not datos["activo"]:
            cambios_repartidor["en_turno"] = False

    if "tipo_vehiculo" in datos:
        vehiculo = str(datos["tipo_vehiculo"]).strip().upper()

        if vehiculo not in VEHICULOS:
            return jsonify({"ok": False, "mensaje": "Tipo de vehiculo no valido"}), 400

        cambios_repartidor["tipo_vehiculo"] = vehiculo

    if "placa" in datos:
        cambios_repartidor["placa"] = str(datos["placa"]).strip().upper() or None

    if "nombre" in datos:
        nombre = str(datos["nombre"]).strip()

        if len(nombre) < 3:
            return jsonify({"ok": False, "mensaje": "Nombre no valido"}), 400

        cambios_usuario["nombre_completo"] = nombre

    if "telefono" in datos:
        cambios_usuario["telefono"] = str(datos["telefono"]).strip() or None

    if not cambios_repartidor and not cambios_usuario:
        return jsonify({"ok": False, "mensaje": "No hay cambios"}), 400

    asegurar_columna_turno()

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT usuario_id FROM repartidores WHERE id = %s;",
                (repartidor_id,),
            )
            fila = cur.fetchone()

            if not fila:
                return jsonify({"ok": False, "mensaje": "Repartidor no encontrado"}), 404

            if cambios_repartidor:
                columnas = ", ".join(f"{c} = %s" for c in cambios_repartidor)
                cur.execute(
                    f"UPDATE repartidores SET {columnas} WHERE id = %s;",
                    [*cambios_repartidor.values(), repartidor_id],
                )

            if cambios_usuario:
                columnas = ", ".join(f"{c} = %s" for c in cambios_usuario)
                cur.execute(
                    f"UPDATE usuarios SET {columnas} WHERE id = %s;",
                    [*cambios_usuario.values(), fila[0]],
                )

        conn.commit()

    return jsonify({"ok": True, "mensaje": "Repartidor actualizado"})
