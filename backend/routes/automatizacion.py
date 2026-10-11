import hmac
import os
from datetime import date

from flask import Blueprint, jsonify, request

from backend.decorators import roles_required
from backend.agentes_automaticos import generar_alerta_pedido
from backend.agente_reporte import generar_reporte_diario, listar_reportes
from backend.llm_agente import llm_configurado


automatizacion_bp = Blueprint(
    "automatizacion",
    __name__,
    url_prefix="/api/automatizacion"
)


@automatizacion_bp.post("/pedidos/<int:pedido_id>/alerta")
@roles_required("ADMIN", "OPERADOR")
def analizar_pedido(pedido_id):
    """Ejecuta los agentes sobre un pedido a pedido del admin (sin
    importar el umbral de riesgo). Tarda unos segundos."""

    if not llm_configurado():
        return jsonify({
            "ok": False,
            "mensaje": "Los agentes no estan configurados (falta OPENAI_API_KEY)."
        }), 503

    try:
        alerta = generar_alerta_pedido(pedido_id, "MANUAL")
    except Exception as error:
        print(f"[AGENTES] Analisis manual: {error}", flush=True)
        alerta = None

    if not alerta:
        return jsonify({
            "ok": False,
            "mensaje": (
                "No se pudo analizar el pedido (sin prediccion ML, "
                "presupuesto alcanzado o error de los agentes)."
            )
        }), 422

    return jsonify({"ok": True, "alerta": alerta})


# =========================================================
# REPORTE DIARIO
# =========================================================

@automatizacion_bp.post("/reporte-diario")
def reporte_programado():
    """Lo llama Cloud Scheduler todos los dias a las 23:00 (Lima).
    Protegido con la cabecera X-Automatizacion-Key."""

    clave = os.getenv("AUTOMATIZACION_KEY", "").strip()
    recibida = request.headers.get("X-Automatizacion-Key", "")

    if not clave:
        return jsonify({
            "ok": False,
            "mensaje": "AUTOMATIZACION_KEY no esta configurada"
        }), 503

    if not hmac.compare_digest(recibida, clave):
        return jsonify({"ok": False, "mensaje": "No autorizado"}), 401

    try:
        reporte = generar_reporte_diario(origen="PROGRAMADO")
    except Exception as error:
        print(f"[AGENTES] Reporte programado: {error}", flush=True)

        # 500: Cloud Scheduler lo marca como fallido y reintenta.
        return jsonify({"ok": False, "mensaje": str(error)}), 500

    return jsonify({
        "ok": True,
        "fecha": reporte["fecha"],
        "estado": reporte["estado"]
    })


@automatizacion_bp.post("/reportes/generar")
@roles_required("ADMIN", "OPERADOR")
def generar_reporte_manual():
    """Boton del panel: genera el reporte de hoy (o de una fecha)."""

    datos = request.get_json(silent=True) or {}

    try:
        fecha = (
            date.fromisoformat(datos["fecha"])
            if datos.get("fecha")
            else None
        )
    except ValueError:
        return jsonify({"ok": False, "mensaje": "Fecha invalida (AAAA-MM-DD)"}), 400

    try:
        reporte = generar_reporte_diario(fecha, origen="MANUAL")
    except Exception as error:
        print(f"[AGENTES] Reporte manual: {error}", flush=True)

        return jsonify({
            "ok": False,
            "mensaje": f"No se pudo generar el reporte: {error}"
        }), 500

    return jsonify({"ok": True, "reporte": reporte})


@automatizacion_bp.get("/reportes")
@roles_required("ADMIN", "OPERADOR")
def ver_reportes():

    try:
        return jsonify({"ok": True, "reportes": listar_reportes(10)})
    except Exception as error:
        return jsonify({
            "ok": False,
            "mensaje": f"No se pudieron leer los reportes: {error}"
        }), 500
