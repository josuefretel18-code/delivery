import os

from flask import Flask, jsonify, render_template
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
from backend.repartidores import asegurar_columna_turno


load_dotenv()

# Conexiones a la BD reutilizables entre peticiones (mucho mas rapido
# que abrir una conexion nueva en cada consulta).
usar_pool()


app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static"
)

CORS(app)

app.register_blueprint(auth_bp)
app.register_blueprint(pedidos_bp)
app.register_blueprint(sedes_bp)
app.register_blueprint(catalogo_bp)
app.register_blueprint(asistente_bp)
app.register_blueprint(automatizacion_bp)
app.register_blueprint(repartidores_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(repartidor_bp)


# Columnas de repartidores (turno y espera): se aplican al arrancar, no
# durante un pedido. Si la BD no responde, la app arranca igual.
try:
    asegurar_columna_turno()
except Exception as error:
    print(f"[REPARTIDORES] Migracion pendiente: {error}", flush=True)

@app.get("/")
def inicio():
    return render_template(
        "index.html",
        maps_api_key=os.getenv("MAPS_API_KEY", ""),
        # Horario de atencion (TIENDA_HORARIO); si no esta, no se muestra
        horario=os.getenv("TIENDA_HORARIO", "").strip()
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