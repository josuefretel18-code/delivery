import os
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from flask import Blueprint, jsonify, request, g
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_connection
from backend.decorators import token_required


load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth"
)


@auth_bp.post("/registro")
def registrar_cliente():

    datos = request.get_json(silent=True) or {}

    nombre = str(
        datos.get("nombre_completo", "")
    ).strip()

    correo = str(
        datos.get("correo", "")
    ).strip().lower()

    password = str(
        datos.get("password", "")
    )

    telefono = str(
        datos.get("telefono", "")
    ).strip()

    if not nombre or not correo or not password:
        return jsonify({
            "ok": False,
            "mensaje": "Nombre, correo y contraseña son obligatorios"
        }), 400

    if len(password) < 8:
        return jsonify({
            "ok": False,
            "mensaje": "La contraseña debe tener al menos 8 caracteres"
        }), 400

    password_hash = generate_password_hash(password)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO usuarios (
                        nombre_completo,
                        correo,
                        password_hash,
                        telefono,
                        rol
                    )
                    VALUES (%s, %s, %s, %s, 'CLIENTE')
                    RETURNING id;
                """, (
                    nombre,
                    correo,
                    password_hash,
                    telefono or None
                ))

                usuario_id = cur.fetchone()[0]

            conn.commit()

        return jsonify({
            "ok": True,
            "mensaje": "Cliente registrado correctamente",
            "usuario_id": usuario_id
        }), 201

    except Exception as error:

        if "usuarios_correo_key" in str(error):
            return jsonify({
                "ok": False,
                "mensaje": "El correo ya está registrado"
            }), 409

        return jsonify({
            "ok": False,
            "mensaje": "No se pudo registrar el usuario"
        }), 500


# =========================================================
# LIMITE DE INTENTOS DE INICIO DE SESION
#
# Tras 5 intentos fallidos se bloquea el ingreso por 1 minuto,
# por correo (protege la cuenta) y por IP (evita probar muchas
# cuentas desde el mismo equipo). En memoria del servidor.
# =========================================================

MAX_INTENTOS_FALLIDOS = 5
BLOQUEO_SEGUNDOS = 60

_INTENTOS = {}
_CANDADO_INTENTOS = threading.Lock()


def _ip_cliente():

    # Render pasa la IP real del visitante en X-Forwarded-For
    reenviada = request.headers.get("X-Forwarded-For", "")

    return (reenviada.split(",")[0].strip() or request.remote_addr or "?")


def _claves_intento(correo):

    return (f"correo:{correo}", f"ip:{_ip_cliente()}")


def _segundos_bloqueado(correo):

    ahora = time.monotonic()

    with _CANDADO_INTENTOS:
        restantes = [
            _INTENTOS[clave]["hasta"] - ahora
            for clave in _claves_intento(correo)
            if clave in _INTENTOS and _INTENTOS[clave].get("hasta", 0) > ahora
        ]

    return int(max(restantes) + 0.999) if restantes else 0


def _registrar_fallo(correo):

    ahora = time.monotonic()

    with _CANDADO_INTENTOS:
        for clave in _claves_intento(correo):

            registro = _INTENTOS.setdefault(clave, {"fallos": 0, "hasta": 0})

            # Un bloqueo ya vencido empieza de cero
            if registro["hasta"] and registro["hasta"] <= ahora:
                registro.update(fallos=0, hasta=0)

            registro["fallos"] += 1

            if registro["fallos"] >= MAX_INTENTOS_FALLIDOS:
                registro.update(fallos=0, hasta=ahora + BLOQUEO_SEGUNDOS)
                print(f"[SEGURIDAD] Ingreso bloqueado 1 min: {clave}", flush=True)


def _limpiar_intentos(correo):

    with _CANDADO_INTENTOS:
        _INTENTOS.pop(f"correo:{correo}", None)


def _respuesta_bloqueado(segundos):

    return jsonify({
        "ok": False,
        "mensaje": (
            f"Demasiados intentos fallidos. Espera {segundos} "
            f"segundos e inténtalo de nuevo."
        ),
        "espera_segundos": segundos
    }), 429


@auth_bp.post("/login")
def login():

    datos = request.get_json(silent=True) or {}

    correo = str(
        datos.get("correo", "")
    ).strip().lower()

    password = str(
        datos.get("password", "")
    )

    if not correo or not password:
        return jsonify({
            "ok": False,
            "mensaje": "Correo y contraseña son obligatorios"
        }), 400

    bloqueo = _segundos_bloqueado(correo)

    if bloqueo:
        return _respuesta_bloqueado(bloqueo)

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    id,
                    nombre_completo,
                    correo,
                    password_hash,
                    rol,
                    activo
                FROM usuarios
                WHERE correo = %s;
            """, (correo,))

            usuario = cur.fetchone()

    if not usuario or not check_password_hash(
        usuario[3],
        password
    ):
        _registrar_fallo(correo)

        bloqueo = _segundos_bloqueado(correo)

        if bloqueo:
            return _respuesta_bloqueado(bloqueo)

        return jsonify({
            "ok": False,
            "mensaje": "Credenciales incorrectas"
        }), 401

    _limpiar_intentos(correo)

    if not usuario[5]:
        return jsonify({
            "ok": False,
            "mensaje": "Usuario inactivo"
        }), 403

    ahora = datetime.now(timezone.utc)

    payload = {
        "sub": str(usuario[0]),
        "rol": usuario[4],
        "iat": ahora,
        "exp": ahora + timedelta(hours=4)
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm="HS256"
    )

    return jsonify({
        "ok": True,
        "mensaje": "Inicio de sesión correcto",
        "token": token,
        "usuario": {
            "id": usuario[0],
            "nombre": usuario[1],
            "correo": usuario[2],
            "rol": usuario[4]
        }
    })


@auth_bp.get("/me")
@token_required
def perfil():

    return jsonify({
        "ok": True,
        "usuario": g.usuario
    })