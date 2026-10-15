import os

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from flask_cors import CORS
from dotenv import load_dotenv

from db import probar_conexion, usar_pool
from backend.decorators import roles_required
from backend.auth import auth_bp
from backend.routes.pedidos import pedidos_bp
from backend.routes.sedes import sedes_bp
from backend.routes.catalogo import catalogo_bp
from backend.routes.asistente import asistente_bp
from backend.routes.automatizacion import automatizacion_bp
from backend.routes.repartidores import repartidores_bp
from backend.routes.dashboard import dashboard_bp
from backend.routes.repartidor_panel import repartidor_bp
from backend.routes.personal import personal_bp
from backend.repartidores import asegurar_columna_turno
from backend.routes.pedidos import asegurar_columnas_cancelacion, asegurar_columnas_pago
from backend.horario import texto_horario


load_dotenv()

# Conexiones a la BD reutilizables entre peticiones (mucho mas rapido
# que abrir una conexion nueva en cada consulta).
usar_pool(maximo=10)


app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static"
)

# CORS: solo el dominio de la tienda y el entorno local pueden llamar a
# la API desde un navegador. (Cloud Scheduler llama servidor a servidor:
# no le afecta.) Se puede cambiar con CORS_ORIGENES, separados por coma.
ORIGENES_PERMITIDOS = [
    origen.strip()
    for origen in os.getenv(
        "CORS_ORIGENES",
        "https://kimbos-delivery.onrender.com,"
        "http://localhost:5000,"
        "http://127.0.0.1:5000"
    ).split(",")
    if origen.strip()
]

CORS(app, origins=ORIGENES_PERMITIDOS)

app.register_blueprint(auth_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(sedes_bp)
app.register_blueprint(catalogo_bp)
app.register_blueprint(asistente_bp)
app.register_blueprint(automatizacion_bp)
app.register_blueprint(repartidores_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(repartidor_bp)
app.register_blueprint(personal_bp)


# Las rutas /api siempre responden JSON, tambien cuando hay un error
# (sin esto Flask devuelve una pagina HTML y el navegador muestra
# "Unexpected token '<' ... is not valid JSON").
@app.errorhandler(HTTPException)
def error_http(error):

    if not request.path.startswith("/api/"):
        return error

    return jsonify({
        "ok": False,
        "mensaje": (
            "Recurso no encontrado." if error.code == 404
            else "Operación no permitida." if error.code == 405
            else "No se pudo procesar la solicitud."
        )
    }), error.code


@app.errorhandler(Exception)
def error_inesperado(error):

    print(f"[ERROR] {request.method} {request.path}: {error!r}", flush=True)

    if not request.path.startswith("/api/"):
        return "Error interno del servidor", 500

    return jsonify({
        "ok": False,
        "mensaje": "Ocurrió un error en el servidor. Intenta de nuevo en unos segundos."
    }), 500


# Columnas de repartidores (turno y espera): se aplican al arrancar, no
# durante un pedido. Si la BD no responde, la app arranca igual.
try:
    asegurar_columna_turno()
    asegurar_columnas_cancelacion()
    asegurar_columnas_pago()
except Exception as error:
    print(f"[MIGRACION] Pendiente: {error}", flush=True)

@app.get("/")
def inicio():
    return render_template(
        "index.html",
        maps_api_key=os.getenv("MAPS_API_KEY", ""),
        # Horario de atencion (TIENDA_APERTURA / TIENDA_CIERRE)
        horario=texto_horario()
    )


@app.get("/acceso")
def acceso_personal():
    return render_template("acceso.html")

@app.get("/admin")
def panel_admin():
    return render_template("admin.html")


@app.get("/repartidor")
def panel_repartidor():
    return render_template("repartidor.html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "servicio": "delivery-api",
        "estado": "activo"
    })


# Muestra datos internos de la BD: solo para ADMIN.
@app.get("/api/database")
@roles_required("ADMIN")
def database():
    try:
        datos = probar_conexion()

        return jsonify({
            "ok": True,
            "conexion": "correcta",
            "database": datos["database"],
            "usuario": datos["usuario"],
            "fecha_servidor": datos["fecha_servidor"]
        })

    except Exception as error:
        return jsonify({
            "ok": False,
            "conexion": "error",
            "mensaje": str(error)
        }), 500


if __name__ == "__main__":

    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )