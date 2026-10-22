"""
Sistema multiagente con automatizacion.

B) Reporte diario (se dispara por HORARIO: Cloud Scheduler, 23:00).
   Cinco agentes trabajan coordinados sobre los indicadores del dia:

     0. Orquestador       -> PLANIFICA: enfoque del dia y un encargo
                             para cada agente de automatizacion.
     1. Analista de datos -> hallazgos del dia (puede comparar con los
                             ultimos dias y consultar el modelo ML).
     2. Estratega         -> recomendaciones y repartidores sugeridos
                             para manana.
     3. Redactor          -> titulo y resumen ejecutivo.
     4. Evaluador         -> califica a los agentes 1, 2 y 3 (1 a 10).
     0. Orquestador       -> DECIDE: aprueba el reporte o devuelve el
                             trabajo al agente con nota baja junto con
                             la observacion del evaluador (1 reintento).

   Las cifras las calcula el sistema con SQL; los agentes solo las
   interpretan (no pueden inventar numeros). Un dia sin pedidos no
   llama al LLM (costo 0).

Cada agente se registra en llm_uso (asistente = REPORTE) y respeta el
corte por presupuesto mensual.
"""

import json
import os
import time
from datetime import date
from decimal import Decimal

from db import get_connection
from backend.agentes_automaticos import (
    _ejecutar,
    _esquema,
    _notas,
    asegurar_tabla_alertas,
)
from backend.llm_agente import configuracion, gasto_mes_usd, llm_configurado
from backend.llm_herramientas import HERRAMIENTAS_ADMIN
from backend.repartidores import repartidores_en_turno


ZONA = "America/Lima"


def costo_empaque_pedido():
    """Costo de empaque por pedido preparado (S/). No hay costos en la
    BD: es un supuesto configurable (COSTO_EMPAQUE_PEDIDO) y el reporte
    lo muestra como tal."""

    try:
        return max(float(os.getenv("COSTO_EMPAQUE_PEDIDO", "1.00")), 0.0)
    except ValueError:
        return 1.0


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

    return metricas_periodo(fecha, fecha)


def metricas_periodo(desde, hasta):
    """Indicadores de un periodo (desde y hasta incluidos, hora de Lima),
    solo pedidos reales. Un dia: desde = hasta. Lo usan el reporte diario
    y las consultas a los agentes ("esta semana", "ayer", ...)."""

    dias = (hasta - desde).days + 1

    filtro = f"""
        COALESCE(p.fuente_datos, 'REAL') = 'REAL'
        AND (p.fecha_pedido AT TIME ZONE '{ZONA}')::date BETWEEN %s AND %s
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
            """, (desde, hasta))

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
            """, (desde, hasta))

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
            """, (desde, hasta))

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
            """, (desde, hasta))

            ml_evaluados, ml_aciertos, riesgo_prom = cur.fetchone()

            cur.execute(f"""
                SELECT a.nivel, COUNT(*)
                FROM alertas_pedido a
                JOIN pedidos p ON p.id = a.pedido_id
                WHERE {filtro} AND a.estado = 'LISTA'
                GROUP BY 1;
            """, (desde, hasta))

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
            """, (desde, hasta))

            por_repartidor = [
                {
                    "repartidor": fila[0],
                    "entregas": fila[1],
                    "retrasos": fila[2],
                    "tiempo_real_promedio_min": _numero(fila[3]),
                }
                for fila in cur.fetchall()
            ]

            cur.execute(f"""
                SELECT ROUND(AVG(COALESCE(p.espera_repartidor_min, 0))::numeric, 1)
                FROM pedidos p
                WHERE {filtro};
            """, (desde, hasta))

            espera_prom = cur.fetchone()[0]

            cur.execute(f"""
                SELECT p.codigo, a.nivel, a.accion, a.minutos_extra
                FROM alertas_pedido a
                JOIN pedidos p ON p.id = a.pedido_id
                WHERE {filtro} AND a.estado = 'LISTA'
                ORDER BY a.probabilidad_retraso DESC NULLS LAST
                LIMIT 10;
            """, (desde, hasta))

            alertas_detalle = [
                {
                    "pedido": fila[0],
                    "nivel": fila[1],
                    "accion": fila[2],
                    "minutos_extra": fila[3],
                }
                for fila in cur.fetchall()
            ]

            # Resumen sintetico: caja, cancelacion, merma y empaques.
            # "Preparado" = el pedido llego a cocina (paso por PREPARANDO
            # o EN_RUTA, o ya se entrego).
            cur.execute(f"""
                WITH dia AS (
                    SELECT
                        p.total,
                        p.subtotal,
                        p.pago_estado,
                        e.codigo AS estado,
                        EXISTS (
                            SELECT 1
                            FROM historial_pedido h
                            JOIN estados_pedido eh ON eh.id = h.estado_id
                            WHERE h.pedido_id = p.id
                              AND eh.codigo IN ('PREPARANDO', 'EN_RUTA')
                        ) AS paso_por_cocina
                    FROM pedidos p
                    JOIN estados_pedido e ON e.id = p.estado_id
                    WHERE {filtro}
                )
                SELECT
                    COALESCE(SUM(total) FILTER (WHERE estado = 'ENTREGADO'), 0),
                    COALESCE(SUM(total) FILTER (WHERE estado = 'ENTREGADO' AND pago_estado = 'PAGADO'), 0),
                    COUNT(*) FILTER (WHERE estado = 'ENTREGADO' AND pago_estado <> 'PAGADO'),
                    COUNT(*) FILTER (WHERE estado = 'ENTREGADO' OR paso_por_cocina),
                    COUNT(*) FILTER (WHERE estado = 'CANCELADO' AND paso_por_cocina),
                    COALESCE(SUM(subtotal) FILTER (WHERE estado = 'CANCELADO' AND paso_por_cocina), 0)
                FROM dia;
            """, (desde, hasta))

            (vendido_entregado, cobrado, sin_confirmar, preparados,
             cancelados_en_cocina, merma) = cur.fetchone()

            # Comparacion: un dia contra el dia anterior y los 7 previos;
            # un periodo contra el periodo anterior de igual duracion.
            dia_anterior = _resumen_rango(cur, desde, 1, 1) if dias == 1 else None
            semana_previa = _resumen_rango(cur, desde, 1 if dias > 1 else 7, dias if dias > 1 else 7)

            # Detalle por dia (solo periodos de varios dias)
            por_dia = []

            if dias > 1:
                cur.execute(f"""
                    SELECT
                        (p.fecha_pedido AT TIME ZONE '{ZONA}')::date,
                        COUNT(*),
                        COALESCE(SUM(p.total) FILTER (WHERE e.codigo <> 'CANCELADO'), 0),
                        COUNT(*) FILTER (WHERE p.retraso IS TRUE)
                    FROM pedidos p
                    JOIN estados_pedido e ON e.id = p.estado_id
                    WHERE {filtro}
                    GROUP BY 1
                    ORDER BY 1;
                """, (desde, hasta))

                por_dia = [
                    {
                        "dia": fila[0].isoformat(),
                        "pedidos": fila[1],
                        "ventas_soles": float(fila[2]),
                        "retrasos": fila[3],
                    }
                    for fila in cur.fetchall()
                ]

    vendidos = total - cancelados

    hora_pico = (
        max(por_hora.items(), key=lambda item: item[1])[0]
        if por_hora else None
    )

    return {
        "fecha": hasta.isoformat(),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "dias": dias,
        "por_dia": por_dia,
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
        "alertas_detalle": alertas_detalle,
        "entregas_por_repartidor": por_repartidor,
        "repartidores_disponibles": repartidores_en_turno(),
        "hora_pico": hora_pico,
        "espera_repartidor_promedio_min": _numero(espera_prom),
        "comparacion": (
            {
                "dia_anterior": dia_anterior,
                "promedio_diario_7_dias_previos": semana_previa,
            }
            if dias == 1 else
            {
                "promedio_diario_periodo": {
                    "pedidos": round(total / dias, 1),
                    "ventas_soles": round(float(ventas) / dias, 2),
                },
                "promedio_diario_periodo_anterior": semana_previa,
            }
        ),
        "resumen_sintetico": _resumen_sintetico(
            total, cancelados, float(ventas), vendidos,
            float(vendido_entregado), float(cobrado), sin_confirmar,
            preparados, cancelados_en_cocina, float(merma),
        ),
    }


def _resumen_sintetico(total, cancelados, ventas, vendidos, vendido_entregado,
                       cobrado, sin_confirmar, preparados,
                       cancelados_en_cocina, merma):
    """Cuatro indicadores para cerrar el reporte (calculados aqui; el
    Redactor solo escribe su lectura)."""

    empaque = costo_empaque_pedido()
    costo_empaques = round(preparados * empaque, 2)

    return {
        "ticket_promedio": {
            "valor_soles": round(ventas / vendidos, 2) if vendidos else 0,
            "detalle": f"S/ {ventas:.2f} en {vendidos} pedido(s) no cancelado(s)",
        },
        "diferencia_caja": {
            # Vendido en pedidos entregados menos lo cobrado y confirmado
            # (efectivo al entregar; Yape/Plin confirmados por el admin)
            "valor_soles": round(vendido_entregado - cobrado, 2),
            "vendido_entregado_soles": round(vendido_entregado, 2),
            "cobrado_confirmado_soles": round(cobrado, 2),
            "pedidos_sin_confirmar": sin_confirmar,
        },
        "tasa_cancelacion": {
            "valor_pct": _porcentaje(cancelados, total),
            "cancelados": cancelados,
            "pedidos": total,
        },
        "merma_y_empaques": {
            "valor_soles": round(costo_empaques + merma, 2),
            "empaques_soles": costo_empaques,
            "pedidos_preparados": preparados,
            "costo_empaque_por_pedido_soles": empaque,
            "merma_soles": round(merma, 2),
            "cancelados_despues_de_cocina": cancelados_en_cocina,
            "supuesto": (
                f"Empaque estimado en S/ {empaque:.2f} por pedido; merma = comida de "
                "pedidos cancelados despues de entrar a cocina, a precio de venta."
            ),
        },
    }


def _resumen_rango(cur, fecha, desde_dias, cantidad_dias):
    """Promedio diario de los `cantidad_dias` dias que empiezan
    `desde_dias` antes de `fecha` (para comparar con el dia)."""

    cur.execute(f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(p.total) FILTER (WHERE e.codigo <> 'CANCELADO'), 0),
            COUNT(*) FILTER (WHERE p.retraso IS TRUE),
            COUNT(*) FILTER (WHERE p.retraso IS NOT NULL)
        FROM pedidos p
        JOIN estados_pedido e ON e.id = p.estado_id
        WHERE COALESCE(p.fuente_datos, 'REAL') = 'REAL'
          AND (p.fecha_pedido AT TIME ZONE '{ZONA}')::date
              BETWEEN %s::date - %s AND %s::date - %s;
    """, (fecha, desde_dias + cantidad_dias - 1, fecha, desde_dias))

    pedidos, ventas, retrasos, evaluadas = cur.fetchone()

    return {
        "pedidos": round(pedidos / cantidad_dias, 1),
        "ventas_soles": round(float(ventas) / cantidad_dias, 2),
        "porcentaje_retrasos": _porcentaje(retrasos, evaluadas),
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

Tu tarea: escribir de 4 a 6 hallazgos concretos del dia.
- Cada hallazgo: tipo (POSITIVO, ALERTA o NEUTRO), un titulo corto (maximo 8 palabras) y un detalle con cifras exactas.
- Compara con el dia anterior y con el promedio diario de los 7 dias previos (vienen en "comparacion"), por ejemplo "5 pedidos, +3 frente a ayer".
- Revisa: ventas y ticket, hora pico, productos mas vendidos, retrasos reales y tiempo real vs prometido, espera por falta de repartidor, entregas por repartidor, aciertos del modelo de Machine Learning y alertas de los agentes.
- Puedes usar estado_modelo para el modelo ML vigente y resumen_ultimos_dias para mas detalle. Usa como maximo una herramienta.
- Si hay menos de 5 pedidos, incluye un hallazgo NEUTRO indicando que las conclusiones son preliminares.
- Si recibes "encargo" del Orquestador, cubre ese punto. Si recibes "observacion_evaluador", corrige lo que se te observo.
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
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": ["POSITIVO", "ALERTA", "NEUTRO"]},
                    "titulo": {"type": "string"},
                    "detalle": {"type": "string"},
                },
                "required": ["tipo", "titulo", "detalle"],
                "additionalProperties": False,
            },
            "description": "De 4 a 6 hallazgos con cifras.",
        },
    }),
    "max_pasos": 2,
    "max_tokens": 1000,
}

AGENTE_ESTRATEGA = {
    "nombre": "estratega",
    "instrucciones": """Eres el Agente Estratega de Kimbos. Recibes los indicadores del dia y los hallazgos del Agente Analista de Datos.

Tu tarea: proponer 3 recomendaciones especificas para manana.
Cada recomendacion debe tener:
- titulo: corto.
- accion: que hacer exactamente (por ejemplo "Tener 2 hamburguesas BBQ pre-armadas a las 17:30"), apoyada en un hallazgo o cifra.
- responsable: ADMINISTRADOR, COCINA, REPARTIDORES o ATENCION_AL_CLIENTE.
- horario: cuando hacerlo (por ejemplo "17:00 a 19:00" o "Todo el dia").
- meta: un indicador medible para comprobar si funciono (por ejemplo "0 retrasos en la hora pico" o "Ticket promedio mayor a S/ 30").
- prioridad: ALTA si afecta claramente retrasos o ventas; si no, MEDIA o BAJA.
Ademas:
- repartidores_sugeridos: entero entre 1 y 6, segun los repartidores disponibles, la carga, la espera y los retrasos.
- franja_refuerzo: franja horaria en la que mas se necesitan repartidores (segun la hora pico), por ejemplo "17:00 a 19:00".
Si recibes "encargo" del Orquestador, tenlo en cuenta. Si recibes "observacion_evaluador", corrige lo que se te observo.
Lo lee el dueno del negocio: sin codigos internos (nada como ASIGNAR_REPARTIDOR_EXTRA o MEDIO en mayusculas) ni jerga tecnica ("ML", "modelo"); di "alertas de riesgo" o "pedidos con riesgo de retraso".
Espanol, frases cortas.""",
    "herramientas": {},
    "formato": _esquema("estrategia", {
        "recomendaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "accion": {"type": "string"},
                    "responsable": {
                        "type": "string",
                        "enum": ["ADMINISTRADOR", "COCINA", "REPARTIDORES", "ATENCION_AL_CLIENTE"],
                    },
                    "horario": {"type": "string"},
                    "meta": {"type": "string"},
                    "prioridad": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
                },
                "required": ["titulo", "accion", "responsable", "horario", "meta", "prioridad"],
                "additionalProperties": False,
            },
        },
        "repartidores_sugeridos": {"type": "integer"},
        "franja_refuerzo": {"type": "string"},
    }),
    "max_pasos": 1,
    "max_tokens": 1000,
}

AGENTE_REDACTOR = {
    "nombre": "redactor",
    "instrucciones": """Eres el Agente Redactor de Kimbos, un delivery en Peru. Recibes los indicadores, los hallazgos y el plan del dia. Escribes el informe operativo que lee el dueno del negocio: alguien ocupado que no es tecnico y decide en un minuto.

Redacta:
- titulo: maximo 10 palabras, la idea principal del dia sin la fecha (ya se muestra aparte). Ejemplo: "Ventas en alza y entregas a tiempo".
- calificacion: BUENO si no hubo retrasos importantes y las ventas estan estables o en alza (0 % de retrasos y ventas en alza siempre es BUENO, aunque haya pocos pedidos); REGULAR si hubo algun problema puntual; CRITICO si hubo retrasos frecuentes o una caida fuerte de ventas.
- resumen: resumen ejecutivo de 2 o 3 frases (maximo 60 palabras): que paso, la cifra que mas importa y como se compara con ayer. Si hubo menos de 10 pedidos, termina indicando que las conclusiones son preliminares por el bajo volumen.
- lo_que_funciono: de 1 a 3 puntos, cada uno una frase corta con su cifra.
- a_vigilar: de 1 a 3 puntos con riesgos o problemas, cada uno una frase corta con su cifra. Si no hubo problemas, un punto preventivo (por ejemplo la hora pico).
- conclusion: la prioridad numero uno para manana en una frase que empiece con un verbo (por ejemplo "Tener 2 repartidores en turno de 17:30 a 19:30").
- resumen_sintetico: cierre del informe con EXACTAMENTE 4 indicadores, uno por cada clave de "resumen_sintetico" de los indicadores (TICKET_PROMEDIO, DIFERENCIA_CAJA, TASA_CANCELACION, MERMA_Y_EMPAQUES). Para cada uno: estado (BIEN, ATENCION o CRITICO) y lectura (una frase con la cifra y que significa para el negocio). Criterios: diferencia de caja 0 es BIEN; mayor a 0 es ATENCION (hay pagos por confirmar; indica cuantos). Cancelacion hasta 5 % BIEN, hasta 15 % ATENCION, mas CRITICO. Merma y empaques: el estado depende SOLO de la merma (el empaque es un costo normal de cada pedido): merma 0 es BIEN; si hay merma, ATENCION. En la lectura aclara que el empaque es un costo estimado.

Estilo:
- Espanol de Peru, tono profesional y directo, en tercera persona.
- Sin jerga tecnica: no digas "ML", "modelo", "F1" ni "predicciones"; di "el sistema de prediccion de retrasos acerto en 5 de 5 pedidos".
- Montos como S/ 176.97 y porcentajes redondeados. Sin signos de exclamacion ni emojis.
- No repitas tablas ni listes todas las cifras: solo lo que ayuda a decidir.
Si recibes "encargo" del Orquestador, tenlo en cuenta. Si recibes "observacion_evaluador", corrige lo que se te observo.""",
    "herramientas": {},
    "formato": _esquema("reporte", {
        "titulo": {"type": "string"},
        "calificacion": {"type": "string", "enum": ["BUENO", "REGULAR", "CRITICO"]},
        "resumen": {"type": "string"},
        "lo_que_funciono": {"type": "array", "items": {"type": "string"}},
        "a_vigilar": {"type": "array", "items": {"type": "string"}},
        "conclusion": {"type": "string"},
        "resumen_sintetico": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "indicador": {
                        "type": "string",
                        "enum": ["TICKET_PROMEDIO", "DIFERENCIA_CAJA",
                                 "TASA_CANCELACION", "MERMA_Y_EMPAQUES"],
                    },
                    "estado": {"type": "string", "enum": ["BIEN", "ATENCION", "CRITICO"]},
                    "lectura": {"type": "string"},
                },
                "required": ["indicador", "estado", "lectura"],
                "additionalProperties": False,
            },
        },
    }),
    "max_pasos": 1,
    "max_tokens": 1300,
}


AGENTES_REPORTE = ["analista", "estratega", "redactor"]

AGENTE_ORQUESTADOR_REPORTE = {
    "nombre": "orquestador",
    "instrucciones": """Eres el Agente Orquestador del reporte diario de Kimbos (delivery en Peru). Coordinas a tres agentes de automatizacion: Analista de datos (hallazgos con cifras), Estratega (plan para manana) y Redactor (resumen ejecutivo). Al final, el Agente Evaluador califica su trabajo.

Recibes los indicadores del dia. Planifica:
- enfoque: el tema principal del dia en pocas palabras (por ejemplo "Retrasos en la hora pico" o "Dia de ventas altas").
- prioridad: ALTA si hubo retrasos frecuentes, caida fuerte de ventas o espera por falta de repartidores; MEDIA si hubo algun problema puntual; BAJA si fue un dia normal.
- Un encargo corto y concreto para cada agente segun los datos (que revisar o en que fijarse). Una frase cada uno.
- razon: por que ese enfoque, en una frase con una cifra.
No inventes datos. Responde en espanol.""",
    "herramientas": {},
    "formato": _esquema("plan_reporte", {
        "enfoque": {"type": "string"},
        "prioridad": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "encargo_analista": {"type": "string"},
        "encargo_estratega": {"type": "string"},
        "encargo_redactor": {"type": "string"},
        "razon": {"type": "string"},
    }),
    "max_pasos": 1,
    "max_tokens": 600,
}

AGENTE_EVALUADOR_REPORTE = {
    "nombre": "evaluador",
    "instrucciones": """Eres el Agente Evaluador del reporte diario de Kimbos. Recibes los indicadores del dia (calculados por el sistema), el plan del Orquestador y el trabajo de tres agentes: Analista de datos (hallazgos), Estratega (recomendaciones) y Redactor (titulo, calificacion y resumen).

Califica a CADA uno de los tres agentes con enteros del 1 al 10 en:
- precision: las cifras coinciden con los indicadores; nada inventado.
- coherencia: es consistente con el agente anterior y cumple el encargo del Orquestador (p. ej. la calificacion del dia del Redactor concuerda con los retrasos).
- utilidad: sirve al administrador para decidir (acciones concretas, con responsable, horario y meta).
- claridad: frases cortas y entendibles.
Se exigente pero justo: 9-10 solo si no hay nada que mejorar. En observacion escribe en una frase que corregir (o "Sin observaciones").
comentario_general: una frase sobre el reporte en conjunto. Responde en espanol.""",
    "herramientas": {},
    "formato": _esquema("evaluacion_reporte", {
        "calificaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agente": {"type": "string", "enum": AGENTES_REPORTE},
                    "precision": {"type": "integer"},
                    "coherencia": {"type": "integer"},
                    "utilidad": {"type": "integer"},
                    "claridad": {"type": "integer"},
                    "observacion": {"type": "string"},
                },
                "required": ["agente", "precision", "coherencia",
                             "utilidad", "claridad", "observacion"],
                "additionalProperties": False,
            },
        },
        "comentario_general": {"type": "string"},
    }),
    "max_pasos": 1,
    "max_tokens": 1000,
}

AGENTE_ORQUESTADOR_CIERRE = {
    "nombre": "orquestador",
    "instrucciones": """Eres el Agente Orquestador del reporte diario de Kimbos. Ya trabajaron el Analista de datos, el Estratega y el Redactor, y el Agente Evaluador califico su trabajo (notas de 1 a 10).

Decide como cierra el flujo aplicando estas reglas EN ORDEN (la primera que se cumpla):
1. REINTENTAR: algun agente tiene nota menor a 6 y su observacion se puede corregir. Indica cual en agente_reintento (el de nota mas baja); volvera a trabajar con la observacion del evaluador.
2. APROBAR: en cualquier otro caso. El reporte queda listo para el administrador.
Si es APROBAR, agente_reintento = "ninguno". motivo: una frase que cite la regla aplicada. Responde en espanol.""",
    "herramientas": {},
    # El motivo va primero: el modelo razona la regla y luego decide.
    "formato": _esquema("cierre_reporte", {
        "motivo": {"type": "string"},
        "decision": {"type": "string", "enum": ["APROBAR", "REINTENTAR"]},
        "agente_reintento": {"type": "string", "enum": AGENTES_REPORTE + ["ninguno"]},
    }),
    "max_pasos": 1,
    "max_tokens": 400,
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


# =========================================================
# FLUJO SECUENCIAL EN 6 PASOS
#
#   0. datos       -> el sistema calcula los indicadores (SQL)
#   1. orquestador -> Agente Orquestador: enfoque y encargos
#   2. analista    -> Agente Analista de datos: hallazgos (JSON)
#   3. estratega   -> Agente Estratega: plan con prioridades y horarios
#   4. redactor    -> Agente Redactor: titulo, calificacion y resumen
#   5. evaluador   -> Agente Evaluador: notas; el Orquestador aprueba
#                     o devuelve el trabajo a un agente (1 reintento)
#
# Cada paso lee de la BD lo que dejo el anterior y guarda su
# resultado; el servidor rechaza un paso si el anterior no termino.
# El panel los llama uno por uno (muestra el progreso) y Cloud
# Scheduler los ejecuta en orden con generar_reporte_diario().
# =========================================================

PASOS = ("datos", "orquestador", "analista", "estratega", "redactor", "evaluador")
ULTIMO_PASO = len(PASOS) - 1


class PasoFueraDeOrden(Exception):
    """Se pidio un paso antes de terminar el anterior."""


def _actualizar_reporte(fecha, costo=0.0, duracion_ms=0, **campos):
    """Actualiza un reporte existente y suma costo y duracion del paso."""

    columnas = ", ".join(f"{columna} = %s" for columna in campos)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE reportes_diarios
                SET {columnas}{", " if columnas else ""}
                    costo_usd = COALESCE(costo_usd, 0) + %s,
                    duracion_ms = COALESCE(duracion_ms, 0) + %s,
                    fecha_generacion = NOW()
                WHERE fecha_reporte = %s;
            """, [*campos.values(), Decimal(str(round(costo, 6))), int(duracion_ms), fecha])


def _verificar_llm():

    if not llm_configurado():
        raise RuntimeError("Falta OPENAI_API_KEY: no se puede generar el reporte.")

    if gasto_mes_usd() >= configuracion()["corte_automatizacion_usd"]:
        raise RuntimeError("Presupuesto mensual del LLM alcanzado: reporte omitido.")


def _reporte_para_paso(fecha, paso):
    """El reporte en curso, verificando que el paso anterior termino."""

    reporte = obtener_reporte(fecha)
    numero = PASOS.index(paso)

    if not reporte or reporte["estado"] in ("LISTO", "SIN_DATOS") or reporte["etapa"] is None:
        raise PasoFueraDeOrden("Primero genera los datos del día (paso 0).")

    if (reporte.get("etapa") if reporte.get("etapa") is not None else -1) < numero - 1:
        raise PasoFueraDeOrden(
            f"El paso {numero} necesita que termine el paso {numero - 1} ({PASOS[numero - 1]})."
        )

    return reporte


def _ejecutar_paso(fecha, paso, agente, datos):
    """Ejecuta un agente, guarda costo y duracion, y marca el error si
    falla (el paso se puede reintentar)."""

    _verificar_llm()

    costos = []
    inicio = time.monotonic()

    try:
        resultado = _ejecutar(agente, datos, costos, "REPORTE")

    except Exception as error:
        _actualizar_reporte(
            fecha,
            costo=sum(costos),
            duracion_ms=(time.monotonic() - inicio) * 1000,
            estado="ERROR",
            error=f"Paso {PASOS.index(paso)} ({paso}): {type(error).__name__}: {error}"[:300],
        )
        raise

    return resultado, sum(costos), (time.monotonic() - inicio) * 1000


def paso_datos(fecha=None, origen="MANUAL"):
    """Paso 0: indicadores del dia (sin LLM). Reinicia el reporte."""

    asegurar_tabla_alertas()
    asegurar_tabla_reportes()

    fecha = fecha or fecha_hoy_lima()
    metricas = metricas_del_dia(fecha)

    # Sin pedidos no hay nada que analizar: no se gasta en el LLM.
    if metricas["pedidos"] == 0:
        _guardar_reporte(
            fecha, origen,
            estado="SIN_DATOS",
            etapa=ULTIMO_PASO,
            metricas=_json(metricas),
            hallazgos=_json([{
                "tipo": "NEUTRO",
                "titulo": "Sin pedidos reales",
                "detalle": "No se registraron pedidos reales este dia.",
            }]),
            recomendaciones=_json([]),
            repartidores_sugeridos=None,
            franja_refuerzo=None,
            titulo=f"Reporte del {fecha:%d/%m}: sin pedidos",
            calificacion=None,
            resumen="No se registraron pedidos reales este dia.",
            conclusion=None,
            costo_usd=Decimal("0"),
            duracion_ms=0,
            error=None,
        )
        return obtener_reporte(fecha)

    _verificar_llm()

    # Se borran los resultados anteriores: los agentes los rehacen
    _guardar_reporte(
        fecha, origen,
        estado="PROCESANDO",
        etapa=0,
        metricas=_json(metricas),
        hallazgos=None,
        recomendaciones=None,
        repartidores_sugeridos=None,
        franja_refuerzo=None,
        titulo=None,
        calificacion=None,
        resumen=None,
        conclusion=None,
        puntos=None,
        orquestacion=None,
        evaluacion=None,
        nota_final=None,
        costo_usd=Decimal("0"),
        duracion_ms=0,
        error=None,
    )

    return obtener_reporte(fecha)


def _con_flujo(reporte, agente, duracion, detalle=None, **extra):
    """orquestacion (JSON) con un paso mas en el flujo."""

    orquestacion = dict(reporte.get("orquestacion") or {})
    orquestacion.update(extra)
    orquestacion["flujo"] = list(orquestacion.get("flujo") or []) + [{
        "agente": agente,
        "detalle": detalle,
        "ms": int(duracion),
    }]

    return orquestacion


def _encargo(reporte, agente):
    return ((reporte.get("orquestacion") or {}).get("plan") or {}).get(f"encargo_{agente}", "")


def paso_orquestador(fecha):
    """Paso 1: el Orquestador lee los indicadores y reparte el trabajo."""

    reporte = _reporte_para_paso(fecha, "orquestador")

    plan, costo, duracion = _ejecutar_paso(fecha, "orquestador", AGENTE_ORQUESTADOR_REPORTE, {
        "fecha": fecha.strftime("%d/%m/%Y"),
        "indicadores_del_dia": reporte["metricas"],
    })

    _actualizar_reporte(
        fecha, costo=costo, duracion_ms=duracion,
        estado="PROCESANDO",
        etapa=PASOS.index("orquestador"),
        orquestacion=_json(_con_flujo(
            reporte, "orquestador", duracion, "Planifica: enfoque y encargos", plan=plan,
        )),
        error=None,
    )

    return obtener_reporte(fecha)


# --- Trabajo de cada agente (se reutiliza en el reintento) ---

def _trabajo_analista(fecha, reporte, observacion=None):

    entrada = {
        "indicadores_del_dia": reporte["metricas"],
        "encargo": _encargo(reporte, "analista"),
    }

    if observacion:
        entrada["observacion_evaluador"] = observacion

    analisis, costo, duracion = _ejecutar_paso(fecha, "analista", AGENTE_ANALISTA_DATOS, entrada)

    return {"hallazgos": _json(analisis["hallazgos"][:6])}, costo, duracion


def _trabajo_estratega(fecha, reporte, observacion=None):

    entrada = {
        "hallazgos": reporte["hallazgos"],
        "indicadores_del_dia": reporte["metricas"],
        "encargo": _encargo(reporte, "estratega"),
    }

    if observacion:
        entrada["observacion_evaluador"] = observacion

    estrategia, costo, duracion = _ejecutar_paso(fecha, "estratega", AGENTE_ESTRATEGA, entrada)

    return {
        "recomendaciones": _json(estrategia["recomendaciones"][:3]),
        "repartidores_sugeridos": max(1, min(int(estrategia["repartidores_sugeridos"]), 6)),
        "franja_refuerzo": (estrategia.get("franja_refuerzo") or "")[:60] or None,
    }, costo, duracion


def _trabajo_redactor(fecha, reporte, observacion=None):

    entrada = {
        "fecha": fecha.strftime("%d/%m/%Y"),
        "indicadores_del_dia": reporte["metricas"],
        "hallazgos": reporte["hallazgos"],
        "recomendaciones": reporte["recomendaciones"],
        "repartidores_sugeridos": reporte["repartidores_sugeridos"],
        "franja_refuerzo": reporte["franja_refuerzo"],
        "encargo": _encargo(reporte, "redactor"),
    }

    if observacion:
        entrada["observacion_evaluador"] = observacion

    redaccion, costo, duracion = _ejecutar_paso(fecha, "redactor", AGENTE_REDACTOR, entrada)

    return {
        "titulo": redaccion["titulo"][:200],
        "calificacion": redaccion["calificacion"],
        "resumen": redaccion["resumen"],
        "conclusion": redaccion["conclusion"],
        "puntos": _json({
            "lo_que_funciono": [str(p)[:200] for p in redaccion.get("lo_que_funciono", [])[:3]],
            "a_vigilar": [str(p)[:200] for p in redaccion.get("a_vigilar", [])[:3]],
            # Lectura del Redactor de cada indicador del resumen sintetico
            "resumen_sintetico": [
                {
                    "indicador": x["indicador"],
                    "estado": x["estado"],
                    "lectura": str(x["lectura"])[:300],
                }
                for x in redaccion.get("resumen_sintetico", [])[:4]
            ],
        }),
    }, costo, duracion


TRABAJO = {
    "analista": _trabajo_analista,
    "estratega": _trabajo_estratega,
    "redactor": _trabajo_redactor,
}


def _paso_agente(fecha, agente):
    """Pasos 2, 3 y 4: un agente de automatizacion con su encargo."""

    reporte = _reporte_para_paso(fecha, agente)

    campos, costo, duracion = TRABAJO[agente](fecha, reporte)

    _actualizar_reporte(
        fecha, costo=costo, duracion_ms=duracion,
        estado="PROCESANDO",
        etapa=PASOS.index(agente),
        orquestacion=_json(_con_flujo(reporte, agente, duracion)),
        error=None,
        **campos,
    )

    return obtener_reporte(fecha)


def _evaluar(fecha, reporte):

    evaluacion, costo, duracion = _ejecutar_paso(fecha, "evaluador", AGENTE_EVALUADOR_REPORTE, {
        "indicadores_del_dia": reporte["metricas"],
        "plan_orquestador": (reporte.get("orquestacion") or {}).get("plan"),
        "analista": {"hallazgos": reporte["hallazgos"]},
        "estratega": {
            "recomendaciones": reporte["recomendaciones"],
            "repartidores_sugeridos": reporte["repartidores_sugeridos"],
            "franja_refuerzo": reporte["franja_refuerzo"],
        },
        "redactor": {
            "titulo": reporte["titulo"],
            "calificacion": reporte["calificacion"],
            "resumen": reporte["resumen"],
            **(reporte.get("puntos") or {}),
            "conclusion": reporte["conclusion"],
        },
    })

    return _notas(evaluacion, AGENTES_REPORTE), costo, duracion


def _decision_coherente(decision, evaluacion):
    """El LLM decide, pero la decision debe cuadrar con las notas: solo
    se reintenta a un agente con nota menor a 6 (el de nota mas baja);
    si ninguno la tiene, se aprueba."""

    notas = {a["agente"]: a["nota"] for a in evaluacion.get("agentes", [])}
    bajos = sorted((nota, agente) for agente, nota in notas.items() if nota < 6)

    if bajos and decision.get("agente_reintento") not in dict((a, n) for n, a in bajos):
        return {
            "decision": "REINTENTAR",
            "agente_reintento": bajos[0][1],
            "motivo": f"Regla 1: el agente {bajos[0][1]} tiene nota {bajos[0][0]} (menor a 6).",
        }

    if not bajos and decision.get("decision") != "APROBAR":
        return {
            "decision": "APROBAR",
            "agente_reintento": "ninguno",
            "motivo": "Regla 2: ningún agente tiene nota menor a 6; el reporte queda aprobado.",
        }

    return decision


def paso_evaluador(fecha):
    """Paso 5: el Evaluador califica y el Orquestador decide. Si un
    agente tiene nota baja, vuelve a trabajar con la observacion (y los
    agentes que dependen de el); luego se evalua otra vez."""

    reporte = _reporte_para_paso(fecha, "evaluador")
    costo_total = 0.0
    duracion_total = 0.0

    evaluacion, costo, duracion = _evaluar(fecha, reporte)
    costo_total += costo
    duracion_total += duracion
    orquestacion = _con_flujo(reporte, "evaluador", duracion)

    decision, costo, duracion = _ejecutar_paso(fecha, "evaluador", AGENTE_ORQUESTADOR_CIERRE, {
        "enfoque_del_dia": (orquestacion.get("plan") or {}).get("enfoque"),
        "evaluacion": evaluacion,
    })
    costo_total += costo
    duracion_total += duracion
    orquestacion = _con_flujo(
        {"orquestacion": orquestacion}, "orquestador", duracion, "Decide con la evaluación",
    )

    decision = _decision_coherente(decision, evaluacion)
    reintento = decision.get("agente_reintento")

    if decision["decision"] == "REINTENTAR" and reintento in AGENTES_REPORTE:

        observacion = next(
            (a["observacion"] for a in evaluacion["agentes"] if a["agente"] == reintento),
            "",
        )

        # El agente observado y los siguientes (dependen de su resultado)
        for agente in AGENTES_REPORTE[AGENTES_REPORTE.index(reintento):]:

            campos, costo, duracion = TRABAJO[agente](
                fecha, reporte, observacion if agente == reintento else None,
            )
            costo_total += costo
            duracion_total += duracion

            # Lo nuevo reemplaza a lo anterior para el siguiente agente
            for clave, valor in campos.items():
                reporte[clave] = (
                    json.loads(valor) if clave in ("hallazgos", "recomendaciones", "puntos") else valor
                )

            _actualizar_reporte(fecha, **campos)

            orquestacion = _con_flujo(
                {"orquestacion": orquestacion}, agente, duracion,
                "Reintento con la observación del evaluador" if agente == reintento
                else "Actualiza con el trabajo corregido",
            )

        reporte["orquestacion"] = orquestacion
        evaluacion, costo, duracion = _evaluar(fecha, reporte)
        costo_total += costo
        duracion_total += duracion
        orquestacion = _con_flujo(
            {"orquestacion": orquestacion}, "evaluador", duracion, "Segunda evaluación",
        )

        decision = {
            "decision": "APROBAR",
            "agente_reintento": reintento,
            "motivo": (
                f"Tras corregir al agente {reintento}, la nota final es "
                f"{evaluacion['nota_final']} ({evaluacion['veredicto'].lower()})."
            ),
        }

    orquestacion["decision"] = decision

    _actualizar_reporte(
        fecha, costo=costo_total, duracion_ms=duracion_total,
        estado="LISTO",
        etapa=ULTIMO_PASO,
        orquestacion=_json(orquestacion),
        evaluacion=_json(evaluacion),
        nota_final=(
            Decimal(str(evaluacion["nota_final"]))
            if evaluacion["nota_final"] is not None else None
        ),
        error=None,
    )

    return obtener_reporte(fecha)


def paso_analista(fecha):
    return _paso_agente(fecha, "analista")


def paso_estratega(fecha):
    return _paso_agente(fecha, "estratega")


def paso_redactor(fecha):
    return _paso_agente(fecha, "redactor")


EJECUTAR_PASO = {
    "orquestador": paso_orquestador,
    "analista": paso_analista,
    "estratega": paso_estratega,
    "redactor": paso_redactor,
    "evaluador": paso_evaluador,
}


def generar_reporte_diario(fecha=None, origen="PROGRAMADO"):
    """Los 6 pasos en orden (lo usa Cloud Scheduler a las 23:00)."""

    reporte = paso_datos(fecha, origen)

    if reporte["estado"] == "SIN_DATOS":
        return reporte

    fecha = date.fromisoformat(reporte["fecha"])

    for paso in PASOS[1:]:
        reporte = EJECUTAR_PASO[paso](fecha)

    return reporte


_COLUMNAS = """
    fecha_reporte, fecha_generacion, origen, estado, metricas,
    hallazgos, recomendaciones, repartidores_sugeridos, titulo,
    resumen, costo_usd, duracion_ms, error,
    calificacion, conclusion, franja_refuerzo, etapa,
    orquestacion, evaluacion, nota_final, puntos
"""


def _fila_a_reporte(fila):

    estado = fila[3]

    return {
        "fecha": fila[0].isoformat(),
        "generado": fila[1].isoformat() if fila[1] else None,
        "origen": fila[2],
        "estado": estado,
        "metricas": json.loads(fila[4]) if fila[4] else None,
        "hallazgos": json.loads(fila[5]) if fila[5] else [],
        "recomendaciones": json.loads(fila[6]) if fila[6] else [],
        "repartidores_sugeridos": fila[7],
        "titulo": fila[8],
        "resumen": fila[9],
        "costo_usd": _numero(fila[10]),
        "duracion_ms": fila[11],
        "error": fila[12],
        "calificacion": fila[13],
        "conclusion": fila[14],
        "franja_refuerzo": fila[15],
        # Un reporte terminado tiene todos los pasos hechos (los
        # anteriores al Orquestador guardaban etapa 3).
        "etapa": ULTIMO_PASO if estado in ("LISTO", "SIN_DATOS") else fila[16],
        "orquestacion": json.loads(fila[17]) if fila[17] else None,
        "evaluacion": json.loads(fila[18]) if fila[18] else None,
        "nota_final": _numero(fila[19]),
        "puntos": json.loads(fila[20]) if fila[20] else None,
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
