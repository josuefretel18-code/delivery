import os
import time
from functools import wraps

import jwt
from flask import request, jsonify, g
from dotenv import load_dotenv

from db import get_connection


load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

# Datos del usuario de la sesion por unos segundos: evita consultar la
# BD en cada peticion. Un cambio de rol o una desactivacion se aplica
# como maximo despues de este tiempo.
CACHE_USUARIO_SEGUNDOS = 60
_CACHE_USUARIOS = {}


def _buscar_usuario(usuario_id):

    guardado = _CACHE_USUARIOS.get(usuario_id)

    if guardado and time.monotonic() - guardado[0] < CACHE_USUARIO_SEGUNDOS:
        return guardado[1]

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    nombre_completo,
                    correo,
                    rol,
                    activo
                FROM usuarios
                WHERE id = %s;
            """, (usuario_id,))

            usuario = cur.fetchone()

    _CACHE_USUARIOS[usuario_id] = (time.monotonic(), usuario)

    return usuario


def token_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):

        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({
                "ok": False,
                "mensaje": "Token de acceso requerido"
            }), 401

        token = auth_header.split(" ", 1)[1]

        try:
            payload = jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=["HS256"]
            )

            usuario_id = int(payload["sub"])

            usuario = _buscar_usuario(usuario_id)

            if not usuario:
                return jsonify({
                    "ok": False,
                    "mensaje": "Usuario no encontrado"
                }), 401

            if not usuario[4]:
                return jsonify({
                    "ok": False,
                    "mensaje": "Usuario inactivo"
                }), 403

            g.usuario = {
                "id": usuario[0],
                "nombre": usuario[1],
                "correo": usuario[2],
                "rol": usuario[3]
            }

        except jwt.ExpiredSignatureError:
            return jsonify({
                "ok": False,
                "mensaje": "La sesión ha expirado"
            }), 401

        except Exception:
            return jsonify({
                "ok": False,
                "mensaje": "Token inválido"
            }), 401

        return func(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    def decorador(func):

        @wraps(func)
        @token_required
        def wrapper(*args, **kwargs):

            if g.usuario["rol"] not in roles:
                return jsonify({
                    "ok": False,
                    "mensaje": "No tiene permisos para realizar esta acción"
                }), 403

            return func(*args, **kwargs)

        return wrapper

    return decorador