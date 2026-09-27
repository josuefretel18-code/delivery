import os
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

    if not usuario:
        return jsonify({
            "ok": False,
            "mensaje": "Credenciales incorrectas"
        }), 401

    if not check_password_hash(
        usuario[3],
        password
    ):
        return jsonify({
            "ok": False,
            "mensaje": "Credenciales incorrectas"
        }), 401

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