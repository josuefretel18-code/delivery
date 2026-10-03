import os

from flask import Flask, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv

from db import probar_conexion
from backend.decorators import roles_required
from backend.auth import auth_bp
from backend.routes.pedidos import pedidos_bp
from backend.routes.sedes import sedes_bp
from backend.routes.catalogo import catalogo_bp


load_dotenv()


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

@app.get("/")
def inicio():
    return render_template(
        "index.html",
        maps_api_key=os.getenv("MAPS_API_KEY", "")
    )

@app.get("/admin")
def panel_admin():
    return render_template("admin.html")


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