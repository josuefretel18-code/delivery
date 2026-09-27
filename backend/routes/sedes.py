from flask import Blueprint, jsonify

from db import get_connection


sedes_bp = Blueprint(
    "sedes",
    __name__,
    url_prefix="/api/sedes"
)


@sedes_bp.get("/activa")
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
        return jsonify({
            "ok": False,
            "mensaje": "No existe una sede activa"
        }), 404

    return jsonify({
        "ok": True,
        "sede": {
            "id": sede[0],
            "negocio": sede[1],
            "nombre": sede[2],
            "direccion": sede[3],
            "latitud": float(sede[4]),
            "longitud": float(sede[5]),
            "telefono": sede[6]
        }
    })