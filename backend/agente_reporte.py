"""
Sistema multiagente con automatizacion.

B) Reporte diario (se dispara por HORARIO: Cloud Scheduler, 23:00).
   Tres agentes trabajan en cadena sobre los indicadores del dia:

     1. Analista de datos -> hallazgos del dia (puede comparar con los
                             ultimos dias y consultar el modelo ML).
     2. Estratega         -> recomendaciones y repartidores sugeridos
                             para manana.
     3. Redactor          -> titulo y resumen ejecutivo.

   Las cifras las calcula el sistema con SQL; los agentes solo las
   interpretan (no pueden inventar numeros). Un dia sin pedidos no
   llama al LLM (costo 0).

Cada agente se registra en llm_uso (asistente = REPORTE) y respeta el
corte por presupuesto mensual.
"""

import json
import os
import time
from decimal import Decimal

from db import get_connection
from backend.agentes_automaticos import (
    _ejecutar,
    _esquema,
    asegurar_tabla_alertas,
)
from backend.llm_agente import configuracion, gasto_mes_usd, llm_configurado
from backend.llm_herramientas import HERRAMIENTAS_ADMIN
from backend.repartidores import repartidores_en_turno


ZONA = "America/Lima"


# =========================================================
# TABLA
# =========================================================

_TABLA_LISTA = {"ok": False}


def asegurar_tabla_reportes():

    if _TABLA_LISTA["ok"]:
        return

    ruta = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sql",
        "agregar_reportes_diarios.sql",
    )

    with open(ruta, encoding="utf-8") as archivo:
        script = archivo.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(script)

    _TABLA_LISTA["ok"] = True


# =========================================================
# INDICADORES DEL DIA (calculados por el sistema)
# =========================================================

def fecha_hoy_lima():

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT (NOW() AT TIME ZONE '{ZONA}')::date;")
            return cur.fetchone()[0]


def _porcentaje(parte, total):

    return round(parte * 100 / total, 1) if total else None


def _numero(valor):

    return float(valor) if valor is not None else None


def metricas_del_dia(fecha):
    """Indicadores del dia (hora de Lima), solo pedidos reales."""

    filtro = f"""
        COALESCE(p.fuente_datos, 'REAL') = 'REAL'
        AND (p.fecha_pedido AT TIME ZONE '{ZONA}')::date = %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(f"""
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (WHERE e.codigo = 'ENTREGADO'),
                    COUNT(*) FILTER (WHERE e.codigo = 'CANCELADO'),
                    COALESCE(SUM(p.total) FILTER (WHERE e.codigo <> 'CANCELADO'), 0),
                    COUNT(*) FILTER (WHERE p.retraso IS TRUE),
                    COUNT(*) FILTER (WHERE p.retraso IS NOT NULL),
                    ROUND(AVG(p.duracion_real_min)::numeric, 1),
                    ROUND(AVG(p.tiempo_estimado_total_min)::numeric, 1),
                    ROUND(AVG(p.distancia_km)::numeric, 2)
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE {filtro};
            """, (fecha,))

            (total, entregados, cancelados, ventas, retrasados, evaluados,
             real_prom, estimado_prom, distancia_prom) = cur.fetchone()

            cur.execute(f"""
                SELECT d.nombre_producto, SUM(d.cantidad)
                FROM detalle_pedido d
                JOIN pedidos p ON p.id = d.pedido_id
                JOIN estados_pedido e ON e.id = p.estado_id
                WHERE {filtro} AND e.codigo <> 'CANCELADO'
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 5;
            """, (fecha,))

            productos = [
                {"producto": fila[0], "unidades": int(fila[1])}
                for fila in cur.fetchall()
            ]

            cur.execute(f"""
                SELECT
                    EXTRACT(HOUR FROM p.fecha_pedido AT TIME ZONE '{ZONA}')::int,
                    COUNT(*)
                FROM pedidos p
                WHERE {filtro}
                GROUP BY 1
                ORDER BY 1;
            """, (fecha,))

            por_hora = {f"{fila[0]:02d}h": fila[1] for fila in cur.fetchall()}

            # Prediccion del modelo ML frente al resultado real
            cur.execute(f"""
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (
                        WHERE (pm.clase_predicha = 'RETRASADO') = p.retraso
                    ),
                    ROUND(AVG(pm.probabilidad_retraso)::numeric * 100, 1)
                FROM pedidos p
                JOIN LATERAL (
                    SELECT clase_predicha, probabilidad_retraso
                    FROM predicciones_ml
                    WHERE pedido_id = p.id
                    ORDER BY id DESC
                    LIMIT 1
                ) pm ON TRUE
                WHERE {filtro} AND p.retraso IS NOT NULL;
            """, (fecha,))

            ml_evaluados, ml_aciertos, riesgo_prom = cur.fetchone()

            cur.execute(f"""
                SELECT a.nivel, COUNT(*)
                FROM alertas_pedido a
                JOIN pedidos p ON p.id = a.pedido_id
                WHERE {filtro} AND a.estado = 'LISTA'
                GROUP BY 1;
            """, (fecha,))

            alertas = {fila[0]: fila[1] for fila in cur.fetchall()}

            cur.execute(f"""
                SELECT
                    u.nombre_completo,
                    COUNT(*) FILTER (WHERE e.codigo = 'ENTREGADO'),
                    COUNT(*) FILTER (WHERE p.retraso IS TRUE),
                    ROUND(AVG(p.duracion_real_min)::numeric, 1)
                FROM pedidos p
                JOIN estados_pedido e ON e.id = p.estado_id
                JOIN repartidores r ON r.id = p.repartidor_id
                JOIN usuarios u ON u.id = r.usuario_id
                WHERE {filtro}
                GROUP BY 1
                ORDER BY 2 DESC;
            """, (fecha,))

            por_repartidor = [
                {
                    "repartidor": fila[0],
                    "entregas": fila[1],
                    "retrasos": fila[2],
                    "tiempo_real_promedio_min": _numero(fila[3]),
                }
                for fila in cur.fetchall()
            ]

    vendidos = total - cancelados

    return {
        "fecha": fecha.isoformat(),
        "pedidos": total,
        "entregados": entregados,
        "cancelados": cancelados,
        "ventas_soles": float(ventas),
        "ticket_promedio_soles": round(float(ventas) / vendidos, 2) if vendidos else 0,
        "entregas_evaluadas": evaluados,
        "entregas_con_retraso": retrasados,
        "porcentaje_retrasos": _porcentaje(retrasados, evaluados),
        "tiempo_real_promedio_min": _numero(real_prom),
        "tiempo_estimado_promedio_min": _numero(estimado_prom),
        "distancia_promedio_km": _numero(distancia_prom),
        "productos_mas_vendidos": productos,
        "pedidos_por_hora": por_hora,
        "modelo_ml": {
            "predicciones_evaluadas": ml_evaluados,
            "aciertos": ml_aciertos,
            "porcentaje_acierto": _porcentaje(ml_aciertos, ml_evaluados),
            "riesgo_promedio_pct": _numero(riesgo_prom),
        },
        "alertas_multiagente": alertas,
        "entregas_por_repartidor": por_repartidor,
        "repartidores_disponibles": repartidores_en_turno(),
    }


def resumen_ultimos_dias(usuario, dias=7):
    """Herramienta del Analista: totales por dia para comparar."""

    dias = max(1, min(int(dias or 7), 14))

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    (p.fecha_pedido AT TIME ZONE '{ZONA}')::date,
                    COUNT(*),
                    COALESCE(SUM(p.total), 0),
                    COUNT(*) FILTER (WHERE p.retraso IS TRUE),
                    COUNT(*) FILTER (WHERE p.retraso IS NOT NULL)
                FROM pedidos p
                WHERE COALESCE(p.fuente_datos, 'REAL') = 'REAL'
                  AND p.fecha_pedido >= NOW() - make_interval(days => %s)
                GROUP BY 1
                ORDER BY 1;
            """, (dias,))

            filas = cur.fetchall()

    return {
        "dias": [
            {
                "dia": fila[0].isoformat(),
                "pedidos": fila[1],
                "ventas_soles": float(fila[2]),
                "retrasos": fila[3],
                "entregas_evaluadas": fila[4],
            }
            for fila in filas
        ]
    }


# =========================================================
# AGENTES
# =========================================================

AGENTE_ANALISTA_DATOS = {
    "nombre": "analista_datos",
    "instrucciones": """Eres el Agente Analista de Datos de Kimbos, un delivery en Peru. Recibes los indicadores del dia, ya calculados por el sistema.

Tu tarea: escribir de 3 a 5 hallazgos concretos del dia, con cifras.
- Revisa ventas, pedidos por hora (picos), productos mas vendidos, retrasos reales, tiempo real vs estimado, entregas por repartidor y aciertos del modelo de Machine Learning.
- Puedes usar resumen_ultimos_dias para comparar con dias anteriores y estado_modelo para el modelo ML vigente. Usa como maximo dos herramientas.
- Si hay pocos datos (menos de 5 pedidos), dilo en un hallazgo: las conclusiones son preliminares.
- Usa solo las cifras recibidas o de las herramientas; no inventes. Espanol, frases cortas.""",
    "herramientas": {
        "resumen_ultimos_dias": (
            {
                "type": "function",
                "name": "resumen_ultimos_dias",
                "description": "Totales por dia (pedidos, ventas, retrasos) de los ultimos dias, para comparar.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dias": {"type": "integer", "description": "Cantidad de dias (1 a 14)."},
                    },
                    "required": ["dias"],
                    "additionalProperties": False,
                },
            },
            resumen_ultimos_dias,
        ),
        "estado_modelo": HERRAMIENTAS_ADMIN["estado_modelo"],
    },
    "formato": _esquema("hallazgos_dia", {
        "hallazgos": {
            "type": "array",
            "items": {"type": "string"},
            "description": "De 3 a 5 hallazgos con cifras.",
        },
    }),
    "max_pasos": 3,
}

AGENTE_ESTRATEGA = {
    "nombre": "estratega",
    "instrucciones": """Eres el Agente Estratega de Kimbos. Recibes los indicadores del dia y los hallazgos del Agente Analista de Datos.

Tu tarea: proponer hasta 3 recomendaciones accionables para manana (personal, horarios, productos, tiempos de entrega) y sugerir cuantos repartidores tener.
- Cada recomendacion debe apoyarse en un hallazgo o cifra.
- repartidores_sugeridos: entero entre 1 y 6, segun los repartidores disponibles hoy, la carga y los retrasos.
- Prioridad ALTA si afecta claramente retrasos o ventas; si no, MEDIA o BAJA.
Espanol, frases cortas.""",
    "herramientas": {},
    "formato": _esquema("estrategia", {
        "recomendaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "detalle": {"type": "string"},
                    "prioridad": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
                },
                "required": ["titulo", "detalle", "prioridad"],
                "additionalProperties": False,
            },
        },
        "repartidores_sugeridos": {"type": "integer"},
    }),
    "max_pasos": 1,
}

AGENTE_REDACTOR = {
    "nombre": "redactor",
    "instrucciones": """Eres el Agente Redactor de Kimbos. Recibes los indicadores, los hallazgos y las recomendaciones del dia.

Redacta para el administrador:
- titulo: corto, con la fecha (dd/mm) y la idea principal del dia.
- resumen: 2 o 3 frases (resumen ejecutivo) con las cifras mas importantes y la recomendacion principal.
No repitas todo: lo demas ya se muestra en tablas. Espanol de Peru, tono profesional.""",
    "herramientas": {},
    "formato": _esquema("reporte", {
        "titulo": {"type": "string"},
        "resumen": {"type": "string"},
    }),
    "max_pasos": 1,
}


# =========================================================
# GENERAR Y LEER REPORTES
# =========================================================

def _guardar_reporte(fecha, origen, **campos):

    columnas = ["fecha_reporte", "origen"] + list(campos)
    valores = [fecha, origen] + list(campos.values())

    actualizar = ", ".join(
        f"{columna} = EXCLUDED.{columna}"
        for columna in columnas[1:]
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO reportes_diarios ({", ".join(columnas)}, fecha_generacion)
                VALUES ({", ".join(["%s"] * len(valores))}, NOW())
                ON CONFLICT (fecha_reporte) DO UPDATE
                SET {actualizar}, fecha_generacion = NOW();
            """, valores)


def _json(valor):

    return json.dumps(valor, ensure_ascii=False)


def generar_reporte_diario(fecha=None, origen="PROGRAMADO"):
    """Genera (o regenera) el reporte de un dia y lo devuelve."""

    asegurar_tabla_alertas()
    asegurar_tabla_reportes()

    fecha = fecha or fecha_hoy_lima()
    metricas = metricas_del_dia(fecha)

    # Sin pedidos no hay nada que analizar: no se gasta en el LLM.
    if metricas["pedidos"] == 0:
        _guardar_reporte(
            fecha, origen,
            estado="SIN_DATOS",
            metricas=_json(metricas),
            hallazgos=_json(["No hubo pedidos reales este dia."]),
            recomendaciones=_json([]),
            repartidores_sugeridos=None,
            titulo=f"Reporte del {fecha:%d/%m}: sin pedidos",
            resumen="No se registraron pedidos reales este dia.",
            costo_usd=Decimal("0"),
            duracion_ms=0,
            error=None,
        )
        return obtener_reporte(fecha)

    if not llm_configurado():
        raise RuntimeError("Falta OPENAI_API_KEY: no se puede generar el reporte.")

    if gasto_mes_usd() >= configuracion()["corte_automatizacion_usd"]:
        raise RuntimeError("Presupuesto mensual del LLM alcanzado: reporte omitido.")

    _guardar_reporte(
        fecha, origen,
        estado="PROCESANDO",
        metricas=_json(metricas),
        error=None,
    )

    costos = []
    inicio = time.monotonic()

    try:
        analisis = _ejecutar(
            AGENTE_ANALISTA_DATOS,
            {"indicadores_del_dia": metricas},
            costos, "REPORTE",
        )

        estrategia = _ejecutar(AGENTE_ESTRATEGA, {
            "indicadores_del_dia": metricas,
            "hallazgos": analisis["hallazgos"],
        }, costos, "REPORTE")

        reporte = _ejecutar(AGENTE_REDACTOR, {
            "fecha": fecha.strftime("%d/%m/%Y"),
            "indicadores_del_dia": metricas,
            "hallazgos": analisis["hallazgos"],
            "recomendaciones": estrategia["recomendaciones"],
            "repartidores_sugeridos": estrategia["repartidores_sugeridos"],
        }, costos, "REPORTE")

    except Exception as error:
        _guardar_reporte(
            fecha, origen,
            estado="ERROR",
            costo_usd=Decimal(str(round(sum(costos), 6))),
            duracion_ms=int((time.monotonic() - inicio) * 1000),
            error=f"{type(error).__name__}: {error}"[:300],
        )
        raise

    _guardar_reporte(
        fecha, origen,
        estado="LISTO",
        hallazgos=_json(analisis["hallazgos"][:5]),
        recomendaciones=_json(estrategia["recomendaciones"][:3]),
        repartidores_sugeridos=max(1, min(int(estrategia["repartidores_sugeridos"]), 6)),
        titulo=reporte["titulo"][:200],
        resumen=reporte["resumen"],
        costo_usd=Decimal(str(round(sum(costos), 6))),
        duracion_ms=int((time.monotonic() - inicio) * 1000),
        error=None,
    )

    return obtener_reporte(fecha)


_COLUMNAS = """
    fecha_reporte, fecha_generacion, origen, estado, metricas,
    hallazgos, recomendaciones, repartidores_sugeridos, titulo,
    resumen, costo_usd, duracion_ms, error
"""


def _fila_a_reporte(fila):

    return {
        "fecha": fila[0].isoformat(),
        "generado": fila[1].isoformat() if fila[1] else None,
        "origen": fila[2],
        "estado": fila[3],
        "metricas": json.loads(fila[4]) if fila[4] else None,
        "hallazgos": json.loads(fila[5]) if fila[5] else [],
        "recomendaciones": json.loads(fila[6]) if fila[6] else [],
        "repartidores_sugeridos": fila[7],
        "titulo": fila[8],
        "resumen": fila[9],
        "costo_usd": _numero(fila[10]),
        "duracion_ms": fila[11],
        "error": fila[12],
    }


def obtener_reporte(fecha):

    asegurar_tabla_reportes()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNAS} FROM reportes_diarios WHERE fecha_reporte = %s;",
                (fecha,),
            )
            fila = cur.fetchone()

    return _fila_a_reporte(fila) if fila else None


def listar_reportes(limite=10):

    asegurar_tabla_reportes()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNAS} FROM reportes_diarios "
                "ORDER BY fecha_reporte DESC LIMIT %s;",
                (limite,),
            )
            return [_fila_a_reporte(fila) for fila in cur.fetchall()]
