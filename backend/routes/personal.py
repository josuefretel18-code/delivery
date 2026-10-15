"""
Gestion del personal (solo ADMIN): administradores y operadores.
Tambien la lista de clientes registrados (solo lectura).

Los repartidores se gestionan en /api/repartidores. Cualquier usuario
puede cambiar su propia contrasena en /api/auth/cambiar-password.
"""

from flask import Blueprint, g, jsonify, request
from werkzeug.security import generate_password_hash

from db import get_connection
from backend.decorators import invalidar_usuario, roles_required


personal_bp = Blueprint(
    "personal",
    __name__,
    url_prefix="/api/personal"
)


ROLES_PERSONAL = ("ADMIN", "OPERADOR")
LARGO_MINIMO_PASSWORD = 8


def _correo_valido(correo):
    return "@" in correo and "." in correo.split("@")[-1]


@personal_bp.get("")
@roles_required("ADMIN")
def listar_personal():

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, nombre_completo, correo, telefono, rol, activo, fecha_creacion
                FROM usuarios
                WHERE rol = ANY(%s)
                ORDER BY rol, nombre_completo;
            """, (list(ROLES_PERSONAL),))

            filas = cur.fetchall()

    return jsonify({
        "ok": True,
        "personal": [
            {
                "id": fila[0],
                "nombre": fila[1],
                "correo": fila[2],
                "telefono": fila[3],
                "rol": fila[4],
                "activo": fila[5],
                "creado": fila[6].isoformat() if fila[6] else None,
                "soy_yo": fila[0] == g.usuario["id"],
            }
            for fila in filas
        ]
    })


@personal_bp.post("")
@roles_required("ADMIN")
def crear_personal():

    datos = request.get_json(silent=True) or {}

    nombre = str(datos.get("nombre", "")).strip()
    correo = str(datos.get("correo", "")).strip().lower()
    telefono = str(datos.get("telefono", "")).strip() or None
    rol = str(datos.get("rol", "OPERADOR")).strip().upper()
    password = str(datos.get("password", ""))

    if len(nombre) < 3:
        return jsonify({"ok": False, "mensaje": "Ingresa el nombre"}), 400

    if not _correo_valido(correo):
        return jsonify({"ok": False, "mensaje": "Ingresa un correo válido"}), 400

    if rol not in ROLES_PERSONAL:
        return jsonify({"ok": False, "mensaje": "Rol no válido"}), 400

    if len(password) < LARGO_MINIMO_PASSWORD:
        return jsonify({
            "ok": False,
            "mensaje": f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres"
        }), 400

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("SELECT 1 FROM usuarios WHERE correo = %s;", (correo,))

            if cur.fetchone():
                return jsonify({"ok": False, "mensaje": "Ese correo ya está en uso"}), 409

            cur.execute("""
                INSERT INTO usuarios (nombre_completo, correo, password_hash, telefono, rol)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """, (nombre, correo, generate_password_hash(password), telefono, rol))

            usuario_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                VALUES (%s, 'CREAR_PERSONAL', 'usuarios', %s, %s);
            """, (g.usuario["id"], usuario_id, f"{rol}: {correo}"))

        conn.commit()

    return jsonify({
        "ok": True,
        "mensaje": f"{'Administrador' if rol == 'ADMIN' else 'Operador'} {nombre} creado. Ingresa en /acceso.",
        "id": usuario_id
    }), 201


def _buscar_personal(cur, usuario_id):

    cur.execute(
        "SELECT rol FROM usuarios WHERE id = %s AND rol = ANY(%s);",
        (usuario_id, list(ROLES_PERSONAL)),
    )

    return cur.fetchone()


@personal_bp.patch("/<int:usuario_id>")
@roles_required("ADMIN")
def activar_personal(usuario_id):

    datos = request.get_json(silent=True) or {}

    if "activo" not in datos:
        return jsonify({"ok": False, "mensaje": "No hay cambios"}), 400

    activo = bool(datos["activo"])

    if usuario_id == g.usuario["id"] and not activo:
        return jsonify({"ok": False, "mensaje": "No puedes desactivar tu propia cuenta"}), 400

    with get_connection() as conn:
        with conn.cursor() as cur:

            if not _buscar_personal(cur, usuario_id):
                return jsonify({"ok": False, "mensaje": "Usuario no encontrado"}), 404

            cur.execute("UPDATE usuarios SET activo = %s WHERE id = %s;", (activo, usuario_id))

            cur.execute("""
                INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                VALUES (%s, %s, 'usuarios', %s, NULL);
            """, (g.usuario["id"], "ACTIVAR_PERSONAL" if activo else "DESACTIVAR_PERSONAL", usuario_id))

        conn.commit()

    # Que el cambio se aplique de inmediato (no esperar la cache de sesion)
    invalidar_usuario(usuario_id)

    return jsonify({"ok": True, "mensaje": "Cuenta actualizada"})


@personal_bp.patch("/<int:usuario_id>/password")
@roles_required("ADMIN")
def restablecer_password(usuario_id):
    """El admin restablece la contrasena de un admin u operador que la
    olvido. (Los repartidores: en Repartidores > Acceso al panel.)"""

    password = str((request.get_json(silent=True) or {}).get("password", ""))

    if len(password) < LARGO_MINIMO_PASSWORD:
        return jsonify({
            "ok": False,
            "mensaje": f"La contraseña debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres"
        }), 400

    with get_connection() as conn:
        with conn.cursor() as cur:

            if not _buscar_personal(cur, usuario_id):
                return jsonify({"ok": False, "mensaje": "Usuario no encontrado"}), 404

            cur.execute(
                "UPDATE usuarios SET password_hash = %s WHERE id = %s;",
                (generate_password_hash(password), usuario_id),
            )

            cur.execute("""
                INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                VALUES (%s, 'RESTABLECER_PASSWORD', 'usuarios', %s, NULL);
            """, (g.usuario["id"], usuario_id))

        conn.commit()

    return jsonify({"ok": True, "mensaje": "Contraseña restablecida"})


# =========================================================
# CLIENTES REGISTRADOS (solo lectura)
# =========================================================

@personal_bp.get("/clientes")
@roles_required("ADMIN")
def listar_clientes():
    """Clientes registrados con su resumen de compras.
    ?buscar= filtra por nombre, correo o telefono."""

    buscar = request.args.get("buscar", "").strip()[:80]
    patron = f"%{buscar}%"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    u.id,
                    u.nombre_completo,
                    u.correo,
                    u.telefono,
                    u.activo,
                    u.fecha_creacion,
                    COUNT(p.id) FILTER (WHERE e.codigo <> 'CANCELADO'),
                    COUNT(p.id) FILTER (WHERE e.codigo = 'ENTREGADO'),
                    COALESCE(SUM(p.total) FILTER (WHERE e.codigo = 'ENTREGADO'), 0),
                    MAX(p.fecha_pedido)
                FROM usuarios u
                LEFT JOIN pedidos p ON p.cliente_id = u.id
                LEFT JOIN estados_pedido e ON e.id = p.estado_id
                WHERE u.rol = 'CLIENTE'
                  AND (
                      %s = ''
                      OR u.nombre_completo ILIKE %s
                      OR u.correo ILIKE %s
                      OR COALESCE(u.telefono, '') ILIKE %s
                  )
                GROUP BY u.id
                ORDER BY MAX(p.fecha_pedido) DESC NULLS LAST, u.fecha_creacion DESC
                LIMIT 300;
            """, (buscar, patron, patron, patron))

            filas = cur.fetchall()

            cur.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'CLIENTE';")
            total = cur.fetchone()[0]

    return jsonify({
        "ok": True,
        "total": total,
        "clientes": [
            {
                "id": fila[0],
                "nombre": fila[1],
                "correo": fila[2],
                "telefono": fila[3],
                "activo": fila[4],
                "registrado": fila[5].isoformat() if fila[5] else None,
                "pedidos": fila[6],
                "entregados": fila[7],
                "total_comprado": float(fila[8]),
                "ultimo_pedido": fila[9].isoformat() if fila[9] else None,
            }
            for fila in filas
        ]
    })
