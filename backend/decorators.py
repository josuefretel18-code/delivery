import os
from functools import wraps

import jwt
from flask import request, jsonify, g
from dotenv import load_dotenv

from db import get_connection


load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")


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