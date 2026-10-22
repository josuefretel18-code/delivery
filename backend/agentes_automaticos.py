"""
Sistema multiagente con automatizacion.

A) Alerta de pedido en riesgo (se dispara por EVENTO).
   Al crear un pedido que el modelo ML predice con riesgo de retraso,
   cinco agentes trabajan coordinados:

     0. Orquestador  -> PLANIFICA: asigna la prioridad y el encargo de
                        cada agente de automatizacion.
     1. Analista     -> identifica la causa del riesgo (consulta la
                        carga actual y puede simular con el modelo ML).
     2. Operaciones  -> recomienda una accion y estima minutos extra.
     3. Comunicador  -> redacta el aviso al cliente y el resumen
                        para el administrador.
     4. Evaluador    -> califica a los agentes 1, 2 y 3 (1 a 10) y
                        calcula la nota final.
     0. Orquestador  -> DECIDE con la evaluacion: publicar el aviso al
                        cliente, dejarlo solo para el admin o devolver
                        el trabajo a un agente con la observacion del
                        evaluador (1 reintento; luego se re-evalua).

   Los agentes PROPONEN: no cambian el pedido. El resultado queda en
   la tabla alertas_pedido y se muestra en el panel admin y en
   "Mis pedidos" del cliente (si el Orquestador lo publica).

Cada agente se registra en llm_uso (asistente = ALERTA) y respeta el
corte por presupuesto mensual.
"""

import json
import os
import threading
import time
from decimal import Decimal

from db import get_connection
from backend.llm_agente import (
    configuracion,
    ejecutar_agente,
    gasto_mes_usd,
    llm_configurado,
    nueva_traza,
    registrar_uso,
)
from backend.llm_herramientas import HERRAMIENTAS_ADMIN


USUARIO_SISTEMA = {"id": None, "nombre": "Automatizacion", "rol": "SISTEMA"}


def _umbral_alerta():

    try:
        return float(os.getenv("ALERTA_UMBRAL_RIESGO", "0.4"))
    except ValueError:
        return 0.4


# =========================================================
# TABLA
# =========================================================

_TABLA_LISTA = {"ok": False}


def asegurar_tabla_alertas():

    if _TABLA_LISTA["ok"]:
        return

    ruta = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sql",
        "agregar_alertas_pedido.sql",
    )

    with open(ruta, encoding="utf-8") as archivo:
        script = archivo.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(script)

    _TABLA_LISTA["ok"] = True


_COLUMNAS_ORQUESTACION = {"ok": False}


def asegurar_columnas_orquestacion():
    """Columnas del Orquestador y del Evaluador. Se llama al arrancar
    la app (nunca dentro de una peticion: ALTER TABLE bloquea)."""

    if _COLUMNAS_ORQUESTACION["ok"]:
        return

    asegurar_tabla_alertas()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'alertas_pedido'
                  AND column_name IN ('prioridad', 'orquestacion', 'evaluacion',
                                      'nota_final', 'publicar_cliente');
            """)

            if cur.fetchone()[0] < 5:
                ruta = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "sql",
                    "agregar_orquestador_evaluador.sql",
                )

                with open(ruta, encoding="utf-8") as archivo:
                    cur.execute(archivo.read())

    _COLUMNAS_ORQUESTACION["ok"] = True


# =========================================================
# AGENTES (instrucciones y formato de salida)
# =========================================================

def _esquema(nombre, propiedades):

    return {
        "name": nombre,
        "schema": {
            "type": "object",
            "properties": propiedades,
            "required": list(propiedades),
            "additionalProperties": False,
        },
    }


AGENTE_ANALISTA = {
    "nombre": "analista",
    "instrucciones": """Eres el Agente Analista de Kimbos, un delivery en Peru. Recibes un pedido que el modelo de Machine Learning marco con riesgo de retraso.

Tu tarea: identificar la causa principal del riesgo.
- Variables del modelo: carga_repartidor (pedidos activos / repartidores; la mas influyente), duracion_estimada_min (ruta), cantidad_items, hora_pico (12-14 y 19-21), fin_semana.
- espera_repartidor_min: minutos que el pedido esperara a un repartidor libre (ya sumados al tiempo estimado). Si es mayor a 0, todos los repartidores estan ocupados.
- Puedes consultar pedidos_activos para ver la carga real ahora, y simular_pedido para comparar escenarios. Usa como maximo una herramienta.
- Nivel segun la probabilidad del modelo: ALTO desde 65 %, MEDIO de 40 a 64 %, BAJO menos de 40 %.
- Escribe los factores en lenguaje simple con su valor, p. ej. "Ruta de 14 min" o "2.5 pedidos por repartidor".
- Si recibes "encargo" del Orquestador, enfoca tu analisis en eso.
- Si recibes "observacion_evaluador", corrige lo que se te observo.
- No inventes datos. Responde en espanol, frases cortas.""",
    "herramientas": {
        nombre: HERRAMIENTAS_ADMIN[nombre]
        for nombre in ("pedidos_activos", "simular_pedido")
    },
    "formato": _esquema("analisis_riesgo", {
        "nivel": {"type": "string", "enum": ["ALTO", "MEDIO", "BAJO"]},
        "causa_principal": {"type": "string", "description": "Una frase."},
        "factores": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Hasta 3 factores concretos con sus valores.",
        },
    }),
    "max_pasos": 2,
}

AGENTE_OPERACIONES = {
    "nombre": "operaciones",
    "instrucciones": """Eres el Agente de Operaciones de Kimbos. Recibes un pedido en riesgo de retraso y el analisis del Agente Analista.

Tu tarea: recomendar UNA accion al administrador y estimar cuantos minutos extra podria tardar.
Acciones posibles:
- PRIORIZAR_PREPARACION: preparar este pedido primero (pocos items o preparacion larga).
- ASIGNAR_REPARTIDOR_EXTRA: la carga por repartidor es alta.
- AJUSTAR_TIEMPO_ESTIMADO: el retraso es dificil de evitar (ruta larga, hora pico); avisar un nuevo tiempo.
- MONITOREAR: riesgo moderado, solo vigilar.
Si el nivel es BAJO, usa MONITOREAR con 0 minutos extra.
Los minutos extra deben ser realistas (0 a 30). No cambias el pedido: solo recomiendas.
Si recibes "encargo" del Orquestador, tenlo en cuenta. Si recibes "observacion_evaluador", corrige lo que se te observo. Responde en espanol.""",
    "herramientas": {},
    "formato": _esquema("recomendacion", {
        "accion": {
            "type": "string",
            "enum": [
                "PRIORIZAR_PREPARACION",
                "ASIGNAR_REPARTIDOR_EXTRA",
                "AJUSTAR_TIEMPO_ESTIMADO",
                "MONITOREAR",
            ],
        },
        "minutos_extra": {"type": "integer"},
        "justificacion": {"type": "string", "description": "Una o dos frases."},
    }),
    "max_pasos": 1,
}

AGENTE_COMUNICADOR = {
    "nombre": "comunicador",
    "instrucciones": """Eres el Agente Comunicador de Kimbos. Recibes un pedido en riesgo, el analisis y la recomendacion de operaciones.

Redacta:
- mensaje_cliente: aviso amable para el cliente, maximo 2 frases, en espanol de Peru, tuteando. Menciona el codigo del pedido y la demora aproximada si minutos_extra > 0. Sin tecnicismos (no hables de modelos ni porcentajes) y sin prometer descuentos.
- Si minutos_extra es 0, el mensaje confirma que el pedido va segun lo previsto (sin hablar de demoras).
- resumen_admin: una frase para el administrador con la causa y la accion recomendada.
- Si recibes "encargo" del Orquestador, tenlo en cuenta. Si recibes "observacion_evaluador", corrige lo que se te observo.""",
    "herramientas": {},
    "formato": _esquema("comunicacion", {
        "mensaje_cliente": {"type": "string"},
        "resumen_admin": {"type": "string"},
    }),
    "max_pasos": 1,
}


NOMBRES_AGENTES = ["analista", "operaciones", "comunicador"]

AGENTE_ORQUESTADOR = {
    "nombre": "orquestador",
    "instrucciones": """Eres el Agente Orquestador del sistema multiagente de Kimbos (delivery en Peru). Coordinas a tres agentes de automatizacion: Analista (encuentra la causa del riesgo), Operaciones (recomienda una accion y minutos extra) y Comunicador (redacta el aviso al cliente y el resumen al admin). Al final, el Agente Evaluador califica su trabajo.

Recibes un pedido que el modelo de Machine Learning marco con riesgo de retraso. Planifica el trabajo:
- prioridad: URGENTE si la probabilidad es 65 % o mas o hay espera de repartidor; NORMAL de 40 a 64 %; BAJA si es menor.
- Un encargo corto y concreto para cada agente, segun los datos del pedido (que revisar o en que fijarse). Una frase cada uno.
- razon: por que esa prioridad, en una frase.
No inventes datos. Responde en espanol.""",
    "herramientas": {},
    "formato": _esquema("plan_orquestador", {
        "prioridad": {"type": "string", "enum": ["URGENTE", "NORMAL", "BAJA"]},
        "encargo_analista": {"type": "string"},
        "encargo_operaciones": {"type": "string"},
        "encargo_comunicador": {"type": "string"},
        "razon": {"type": "string"},
    }),
    "max_pasos": 1,
    "max_tokens": 500,
}

AGENTE_EVALUADOR = {
    "nombre": "evaluador",
    "instrucciones": """Eres el Agente Evaluador del sistema multiagente de Kimbos. Recibes el pedido con los datos del modelo de Machine Learning, el plan del Orquestador y el trabajo de tres agentes: Analista, Operaciones y Comunicador.

Califica a CADA uno de los tres agentes con enteros del 1 al 10 en:
- precision: usa los datos reales del pedido, sin inventar (p. ej. el nivel coincide con la probabilidad: ALTO desde 65 %, MEDIO 40-64 %, BAJO menos de 40 %).
- coherencia: es consistente con el agente anterior y con el encargo del Orquestador (p. ej. riesgo BAJO -> MONITOREAR con 0 min; si minutos_extra es 0, el mensaje no habla de demoras).
- utilidad: sirve para actuar (al admin o al cliente).
- claridad: frases cortas y entendibles; el mensaje al cliente sin tecnicismos ni porcentajes.
Se exigente pero justo: 9-10 solo si no hay nada que mejorar. En observacion escribe en una frase que corregir (o "Sin observaciones").
comentario_general: una frase sobre el trabajo en conjunto. Responde en espanol.""",
    "herramientas": {},
    "formato": _esquema("evaluacion", {
        "calificaciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agente": {"type": "string", "enum": NOMBRES_AGENTES},
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
    "max_tokens": 900,
}

AGENTE_ORQUESTADOR_DECISION = {
    "nombre": "orquestador",
    "instrucciones": """Eres el Agente Orquestador de Kimbos. Ya trabajaron el Analista, Operaciones y el Comunicador, y el Agente Evaluador califico su trabajo (notas de 1 a 10).

Decide como cierra el flujo aplicando estas reglas EN ORDEN (la primera que se cumpla):
1. REINTENTAR: algun agente tiene nota menor a 6 y su observacion se puede corregir. Indica cual en agente_reintento (el de nota mas baja); volvera a trabajar con la observacion del evaluador.
2. SOLO_ADMIN: nivel BAJO y minutos_extra 0 (el pedido va bien: avisar al cliente no aporta), o la nota final es menor a 7. Solo lo ve el administrador.
3. PUBLICAR: en cualquier otro caso. El aviso llega al cliente y al admin.
Si no es REINTENTAR, agente_reintento = "ninguno". motivo: una frase que cite la regla aplicada. Responde en espanol.""",
    "herramientas": {},
    # El motivo va primero: el modelo razona la regla y luego decide.
    "formato": _esquema("decision_orquestador", {
        "motivo": {"type": "string"},
        "decision": {"type": "string", "enum": ["PUBLICAR", "REINTENTAR", "SOLO_ADMIN"]},
        "agente_reintento": {"type": "string", "enum": NOMBRES_AGENTES + ["ninguno"]},
    }),
    "max_pasos": 1,
    "max_tokens": 400,
}

CRITERIOS_EVALUACION = ("precision", "coherencia", "utilidad", "claridad")


def _notas(evaluacion, nombres=None):
    """Ordena las calificaciones, acota los valores a 1-10 y calcula la
    nota de cada agente y la final (promedios, en el backend: el LLM
    califica, el codigo hace la cuenta). nombres: agentes evaluados
    (por defecto los 3 de la alerta; el reporte diario pasa los suyos)."""

    por_agente = {
        calificacion.get("agente"): calificacion
        for calificacion in evaluacion.get("calificaciones", [])
    }

    agentes = []

    for nombre in nombres or NOMBRES_AGENTES:

        calificacion = por_agente.get(nombre)

        if not calificacion:
            continue

        criterios = {
            criterio: max(1, min(10, int(calificacion.get(criterio) or 1)))
            for criterio in CRITERIOS_EVALUACION
        }

        agentes.append({
            "agente": nombre,
            **criterios,
            "nota": round(sum(criterios.values()) / len(criterios), 1),
            "observacion": str(calificacion.get("observacion", ""))[:300],
        })

    nota_final = (
        round(sum(a["nota"] for a in agentes) / len(agentes), 1)
        if agentes else None
    )

    if nota_final is None:
        veredicto = "SIN_NOTA"
    elif nota_final >= 7 and min(a["nota"] for a in agentes) >= 6:
        veredicto = "APROBADO"
    elif nota_final >= 5:
        veredicto = "OBSERVADO"
    else:
        veredicto = "DESAPROBADO"

    return {
        "agentes": agentes,
        "nota_final": nota_final,
        "veredicto": veredicto,
        "comentario_general": str(evaluacion.get("comentario_general", ""))[:400],
    }


def _ejecutar(agente, datos, costos, tipo="ALERTA"):
    """Ejecuta un agente con salida JSON y registra su consumo en
    llm_uso (tipo = ALERTA o REPORTE)."""

    traza = nueva_traza()
    inicio = time.monotonic()
    modelo = configuracion()["modelo"]

    try:
        texto = ejecutar_agente(
            agente["instrucciones"],
            [{
                "role": "user",
                "content": json.dumps(datos, ensure_ascii=False, default=str),
            }],
            agente["herramientas"],
            USUARIO_SISTEMA,
            f"{tipo.lower()}-{agente['nombre']}",
            traza,
            formato=agente["formato"],
            max_pasos=agente["max_pasos"],
            max_tokens=agente.get("max_tokens", 600),
        )

        resultado = json.loads(texto)

    except Exception as error:
        registrar_uso(
            None, tipo, modelo, traza["uso"], traza["pasos"],
            [agente["nombre"]] + traza["herramientas"],
            int((time.monotonic() - inicio) * 1000),
            ok=False, error=f"{agente['nombre']}: {type(error).__name__}: {error}",
        )
        raise

    costos.append(registrar_uso(
        None, tipo, modelo, traza["uso"], traza["pasos"],
        [agente["nombre"]] + traza["herramientas"],
        int((time.monotonic() - inicio) * 1000),
    ))

    return resultado


# =========================================================
# A) ALERTA DE PEDIDO EN RIESGO
# =========================================================

def _datos_pedido(pedido_id):

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.codigo,
                    p.distancia_km,
                    p.duracion_estimada_min,
                    p.tiempo_preparacion_estimado_min,
                    p.tiempo_estimado_total_min,
                    p.cantidad_items,
                    COALESCE(p.espera_repartidor_min, 0),
                    pm.clase_predicha,
                    pm.probabilidad_retraso,
                    pm.modelo_version,
                    pm.hora_pedido,
                    pm.dia_semana,
                    pm.hora_pico,
                    pm.fin_semana,
                    pm.pedidos_activos,
                    pm.repartidores_disponibles,
                    pm.carga_repartidor
                FROM pedidos p
                JOIN LATERAL (
                    SELECT *
                    FROM predicciones_ml
                    WHERE pedido_id = p.id
                    ORDER BY id DESC
                    LIMIT 1
                ) pm ON TRUE
                WHERE p.id = %s;
            """, (pedido_id,))

            fila = cur.fetchone()

    if not fila:
        return None

    return {
        "codigo": fila[0],
        "distancia_km": float(fila[1]) if fila[1] is not None else None,
        "duracion_ruta_min": fila[2],
        "preparacion_min": fila[3],
        "tiempo_estimado_total_min": fila[4],
        "cantidad_items": fila[5],
        "espera_repartidor_min": fila[6],
        "prediccion_ml": {
            "clase": fila[7],
            "probabilidad_retraso_pct": round(float(fila[8]) * 100, 1),
            "modelo": fila[9],
        },
        "variables_modelo": {
            "hora_pedido": fila[10],
            "dia_semana": fila[11],
            "hora_pico": bool(fila[12]),
            "fin_semana": bool(fila[13]),
            "pedidos_activos": fila[14],
            "repartidores_disponibles": fila[15],
            "carga_repartidor": float(fila[16]) if fila[16] is not None else None,
        },
        "_probabilidad": float(fila[8]),
    }


def _guardar_alerta(pedido_id, origen, **campos):

    columnas = ["pedido_id", "origen"] + list(campos)
    valores = [pedido_id, origen] + list(campos.values())

    actualizar = ", ".join(
        f"{columna} = EXCLUDED.{columna}"
        for columna in columnas[1:]
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO alertas_pedido ({", ".join(columnas)}, fecha)
                VALUES ({", ".join(["%s"] * len(valores))}, NOW())
                ON CONFLICT (pedido_id) DO UPDATE
                SET {actualizar}, fecha = NOW();
            """, valores)


def generar_alerta_pedido(pedido_id, origen="AUTOMATICA"):
    """Ejecuta los 5 agentes sobre un pedido. Devuelve la alerta o None
    si no corresponde (sin prediccion, sin LLM o sin presupuesto)."""

    if not llm_configurado():
        return None

    if gasto_mes_usd() >= configuracion()["corte_automatizacion_usd"]:
        print("[AGENTES] Presupuesto del mes alcanzado: alerta omitida", flush=True)
        return None

    asegurar_tabla_alertas()

    pedido = _datos_pedido(pedido_id)

    if not pedido:
        return None

    probabilidad = pedido.pop("_probabilidad")

    _guardar_alerta(
        pedido_id, origen,
        estado="PROCESANDO",
        probabilidad_retraso=Decimal(str(round(probabilidad, 4))),
        error=None,
    )

    costos = []
    inicio = time.monotonic()
    flujo = []

    def paso(agente, datos, nombre=None, detalle=None):
        """Ejecuta un agente y anota el paso en el flujo."""
        comienzo = time.monotonic()
        resultado = _ejecutar(agente, datos, costos)
        flujo.append({
            "agente": nombre or agente["nombre"],
            "detalle": detalle,
            "ms": int((time.monotonic() - comienzo) * 1000),
        })
        return resultado

    try:
        # 0. Orquestador: planifica
        plan = paso(
            AGENTE_ORQUESTADOR, {"pedido": pedido},
            detalle="Planifica: prioridad y encargos",
        )

        encargos = {
            nombre: plan.get(f"encargo_{nombre}", "")
            for nombre in NOMBRES_AGENTES
        }

        observaciones = {}

        def trabajar(desde, intento=""):
            """Agentes de automatizacion desde `desde` en adelante
            (en un reintento, el agente observado y los siguientes,
            porque dependen de su resultado)."""

            nonlocal analisis, recomendacion, comunicacion

            orden = NOMBRES_AGENTES[NOMBRES_AGENTES.index(desde):]

            if "analista" in orden:
                analisis = paso(AGENTE_ANALISTA, {
                    "pedido": pedido,
                    "encargo": encargos["analista"],
                    **({"observacion_evaluador": observaciones["analista"]}
                       if "analista" in observaciones else {}),
                }, detalle=intento or None)

            if "operaciones" in orden:
                recomendacion = paso(AGENTE_OPERACIONES, {
                    "pedido": pedido,
                    "analisis": analisis,
                    "encargo": encargos["operaciones"],
                    **({"observacion_evaluador": observaciones["operaciones"]}
                       if "operaciones" in observaciones else {}),
                }, detalle=intento or None)

                recomendacion["minutos_extra"] = max(
                    0, min(int(recomendacion.get("minutos_extra") or 0), 60)
                )

            comunicacion = paso(AGENTE_COMUNICADOR, {
                "pedido": {
                    "codigo": pedido["codigo"],
                    "tiempo_estimado_total_min": pedido["tiempo_estimado_total_min"],
                },
                "analisis": analisis,
                "recomendacion": recomendacion,
                "encargo": encargos["comunicador"],
                **({"observacion_evaluador": observaciones["comunicador"]}
                   if "comunicador" in observaciones else {}),
            }, detalle=intento or None)

        def evaluar(detalle=None):
            return _notas(paso(AGENTE_EVALUADOR, {
                "pedido": pedido,
                "plan_orquestador": plan,
                "analista": analisis,
                "operaciones": recomendacion,
                "comunicador": comunicacion,
            }, detalle=detalle))

        analisis = recomendacion = comunicacion = None

        # 1-3. Agentes de automatizacion
        trabajar("analista")

        # 4. Evaluador
        evaluacion = evaluar()

        # 0. Orquestador: decide con la evaluacion
        decision = paso(AGENTE_ORQUESTADOR_DECISION, {
            "pedido": {
                "codigo": pedido["codigo"],
                "prediccion_ml": pedido["prediccion_ml"],
            },
            "nivel": analisis["nivel"],
            "minutos_extra": recomendacion["minutos_extra"],
            "evaluacion": evaluacion,
        }, detalle="Decide con la evaluación")

        # La decision debe cuadrar con las notas: solo se reintenta a un
        # agente con nota menor a 6 (el de nota mas baja).
        notas = {a["agente"]: a["nota"] for a in evaluacion["agentes"]}
        bajos = sorted((nota, agente) for agente, nota in notas.items() if nota < 6)

        if bajos and decision.get("agente_reintento") not in [a for _, a in bajos]:
            decision = {
                "decision": "REINTENTAR",
                "agente_reintento": bajos[0][1],
                "motivo": f"Regla 1: el agente {bajos[0][1]} tiene nota {bajos[0][0]} (menor a 6).",
            }
        elif not bajos and decision["decision"] == "REINTENTAR":
            decision = {
                "decision": "PUBLICAR" if evaluacion["veredicto"] == "APROBADO" else "SOLO_ADMIN",
                "agente_reintento": "ninguno",
                "motivo": "Ningún agente tiene nota menor a 6: no hace falta reintentar.",
            }

        reintento = decision.get("agente_reintento")

        if decision["decision"] == "REINTENTAR" and reintento in NOMBRES_AGENTES:

            observacion = next(
                (a["observacion"] for a in evaluacion["agentes"] if a["agente"] == reintento),
                "",
            )
            observaciones[reintento] = observacion

            # Un solo reintento; despues se vuelve a evaluar
            trabajar(reintento, intento="Reintento con la observación del evaluador")
            evaluacion = evaluar(detalle="Segunda evaluación")

            # Tras el reintento la decision es por la nota (sin otro ciclo)
            decision = {
                "decision": "PUBLICAR" if evaluacion["veredicto"] == "APROBADO" else "SOLO_ADMIN",
                "agente_reintento": reintento,
                "motivo": (
                    f"Tras corregir al agente {reintento}, la nota final es "
                    f"{evaluacion['nota_final']} ({evaluacion['veredicto'].lower()})."
                ),
            }

            flujo.append({
                "agente": "orquestador",
                "detalle": "Cierra el flujo tras el reintento",
                "ms": 0,
            })

        publicar = decision["decision"] == "PUBLICAR"

        # Regla fija del negocio (por si el LLM la pasa por alto): un
        # pedido sin riesgo ni demora no genera aviso al cliente.
        if (
            publicar and
            analisis["nivel"] == "BAJO" and
            recomendacion["minutos_extra"] == 0
        ):
            publicar = False
            decision["decision"] = "SOLO_ADMIN"
            decision["motivo"] = (
                "Riesgo bajo y sin minutos extra: el pedido va bien, "
                "el aviso queda solo para el administrador."
            )

    except Exception as error:
        print(f"[AGENTES] Alerta del pedido {pedido_id}: {error}", flush=True)

        _guardar_alerta(
            pedido_id, origen,
            estado="ERROR",
            costo_usd=Decimal(str(round(sum(costos), 6))),
            duracion_ms=int((time.monotonic() - inicio) * 1000),
            error=f"{type(error).__name__}: {error}"[:300],
        )
        return None

    orquestacion = {
        "plan": plan,
        "decision": decision,
        "flujo": flujo,
    }

    alerta = {
        "estado": "LISTA",
        "nivel": analisis["nivel"],
        "causa": analisis["causa_principal"][:300],
        "factores": json.dumps(analisis["factores"][:3], ensure_ascii=False),
        "accion": recomendacion["accion"],
        "minutos_extra": recomendacion["minutos_extra"],
        "justificacion": recomendacion["justificacion"][:400],
        "mensaje_cliente": comunicacion["mensaje_cliente"][:400],
        "resumen_admin": comunicacion["resumen_admin"][:400],
        "prioridad": plan["prioridad"],
        "orquestacion": json.dumps(orquestacion, ensure_ascii=False),
        "evaluacion": json.dumps(evaluacion, ensure_ascii=False),
        "nota_final": (
            Decimal(str(evaluacion["nota_final"]))
            if evaluacion["nota_final"] is not None else None
        ),
        "publicar_cliente": publicar,
        "costo_usd": Decimal(str(round(sum(costos), 6))),
        "duracion_ms": int((time.monotonic() - inicio) * 1000),
        "error": None,
    }

    _guardar_alerta(pedido_id, origen, **alerta)

    alerta["orquestacion"] = orquestacion
    alerta["evaluacion"] = evaluacion
    alerta["nota_final"] = evaluacion["nota_final"]
    alerta["factores"] = analisis["factores"][:3]
    alerta["costo_usd"] = float(alerta["costo_usd"])

    return alerta


def disparar_alerta_si_riesgo(pedido_id, prediccion):
    """Se llama al crear un pedido. Si el riesgo supera el umbral, los
    agentes trabajan en segundo plano: el cliente no espera."""

    if not prediccion or not llm_configurado():
        return

    if float(prediccion.get("probabilidad_retraso", 0)) < _umbral_alerta():
        return

    threading.Thread(
        target=_alerta_en_segundo_plano,
        args=(pedido_id,),
        daemon=True,
    ).start()


def _alerta_en_segundo_plano(pedido_id):

    try:
        generar_alerta_pedido(pedido_id, "AUTOMATICA")
    except Exception as error:
        print(f"[AGENTES] Error en alerta automatica: {error}", flush=True)


def alertas_por_pedido(pedido_ids, solo_cliente=False):
    """{pedido_id: alerta} para mostrar en el panel o en Mis pedidos.
    solo_cliente: solo el aviso de las alertas terminadas."""

    if not pedido_ids:
        return {}

    try:
        asegurar_tabla_alertas()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        pedido_id, estado, origen, nivel, causa, factores,
                        accion, minutos_extra, justificacion,
                        mensaje_cliente, resumen_admin, costo_usd,
                        duracion_ms, fecha,
                        prioridad, orquestacion, evaluacion, nota_final,
                        publicar_cliente
                    FROM alertas_pedido
                    WHERE pedido_id = ANY(%s);
                """, (list(pedido_ids),))

                filas = cur.fetchall()

    except Exception as error:
        print(f"[AGENTES] No se pudieron leer las alertas: {error}", flush=True)
        return {}

    alertas = {}

    for fila in filas:

        if solo_cliente:
            # Solo si el Orquestador decidio publicarlo al cliente
            if fila[1] == "LISTA" and fila[9] and fila[18] is not False:
                alertas[fila[0]] = {
                    "mensaje": fila[9],
                    "minutos_extra": fila[7],
                }
            continue

        alertas[fila[0]] = {
            "estado": fila[1],
            "origen": fila[2],
            "nivel": fila[3],
            "causa": fila[4],
            "factores": json.loads(fila[5]) if fila[5] else [],
            "accion": fila[6],
            "minutos_extra": fila[7],
            "justificacion": fila[8],
            "mensaje_cliente": fila[9],
            "resumen_admin": fila[10],
            "costo_usd": float(fila[11]) if fila[11] is not None else None,
            "duracion_ms": fila[12],
            "fecha": fila[13].isoformat() if fila[13] else None,
            "prioridad": fila[14],
            "orquestacion": json.loads(fila[15]) if fila[15] else None,
            "evaluacion": json.loads(fila[16]) if fila[16] else None,
            "nota_final": float(fila[17]) if fila[17] is not None else None,
            "publicar_cliente": fila[18],
        }

    return alertas
