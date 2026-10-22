"""
Sistema multiagente con automatizacion.

C) Consulta a los agentes (se dispara por PREGUNTA del administrador).
   El administrador escribe una pregunta ("¿como nos fue esta semana?",
   "¿por que hubo retrasos ayer?") y trabajan 5 agentes, uno por paso:

     0. Orquestador -> entiende la pregunta: periodo (desde/hasta),
                       enfoque y un encargo para cada agente. Si la
                       pregunta no es del negocio, responde y termina.
     1. Datos       -> el sistema calcula los indicadores del periodo
                       con SQL (sin LLM).
     2. Analista    -> hallazgos que responden a la pregunta.
     3. Estratega   -> acciones recomendadas.
     4. Redactor    -> respuesta directa a la pregunta.
     5. Evaluador   -> califica a los agentes 2, 3 y 4 (1 a 10) y el
                       Orquestador aprueba o devuelve el trabajo al
                       agente con nota baja (1 reintento).

   Los agentes son los del reporte diario (backend/agente_reporte.py)
   con instrucciones adicionales para responder la pregunta. El
   resultado tiene la misma forma que un reporte, asi el panel lo
   muestra igual. Cada llamada se registra en llm_uso como REPORTE
   (mismo presupuesto de automatizacion).
"""

import json
import os
import re
import time
from datetime import date, timedelta
from decimal import Decimal

from db import get_connection
from backend.agentes_automaticos import _ejecutar, _esquema, _notas
from backend.agente_reporte import (
    AGENTE_ANALISTA_DATOS,
    AGENTE_ESTRATEGA,
    AGENTE_EVALUADOR_REPORTE,
    AGENTE_ORQUESTADOR_CIERRE,
    AGENTE_REDACTOR,
    AGENTES_REPORTE,
    PasoFueraDeOrden,
    ZONA,
    _decision_coherente,
    _json,
    _numero,
    _verificar_llm,
    fecha_hoy_lima,
    metricas_periodo,
)


PASOS = ("orquestador", "datos", "analista", "estratega", "redactor", "evaluador")
ULTIMO_PASO = len(PASOS) - 1

# Periodo maximo que se puede consultar (dias hacia atras)
DIAS_MAXIMOS = 90


def consultas_diarias_maximas():
    try:
        return max(int(os.getenv("LLM_CONSULTAS_DIARIAS", "20")), 1)
    except ValueError:
        return 20


# =========================================================
# TABLA
# =========================================================

_TABLA_LISTA = {"ok": False}


def asegurar_tabla_consultas():

    if _TABLA_LISTA["ok"]:
        return

    ruta = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sql",
        "agregar_consultas_agentes.sql",
    )

    with open(ruta, encoding="utf-8") as archivo:
        script = archivo.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(script)

    _TABLA_LISTA["ok"] = True


# =========================================================
# AGENTES (los del reporte, con la pregunta como objetivo)
# =========================================================

AGENTE_ORQUESTADOR_CONSULTA = {
    "nombre": "orquestador",
    "instrucciones": """Eres el Agente Orquestador de Kimbos, un delivery en Peru. El administrador hace una pregunta sobre el negocio. Coordinas a tres agentes: Analista de datos (hallazgos con cifras), Estratega (acciones) y Redactor (respuesta final). Al final el Agente Evaluador califica su trabajo.

Recibes la pregunta, la fecha de hoy y desde cuando hay datos. Decide:
- en_alcance: true si la pregunta es sobre la operacion de Kimbos (pedidos, ventas, productos, horarios, retrasos, repartidores, clientes, cancelaciones, caja, prediccion de retrasos). false si no (por ejemplo el clima, politica o temas personales).
- respuesta_fuera_de_alcance: si en_alcance es false, una frase amable explicando que solo puedes responder sobre la operacion de Kimbos; si es true, cadena vacia.
- desde y hasta (AAAA-MM-DD): el periodo que responde la pregunta. "hoy" = hoy; "ayer" = ayer; "esta semana" = desde el lunes de esta semana hasta hoy; "la semana pasada" = lunes a domingo anteriores; "este mes" = desde el dia 1 hasta hoy; un dia de la semana ("el sabado") = el ultimo con esa fecha. Si la pregunta no indica periodo, los ultimos 7 dias hasta hoy. Nunca despues de hoy.
- enfoque: el tema de la pregunta en pocas palabras.
- prioridad: ALTA, MEDIA o BAJA segun la urgencia del tema.
- Un encargo corto para cada agente sobre que buscar para responder la pregunta.
- razon: por que ese periodo y enfoque, en una frase.
Responde en espanol.""",
    "herramientas": {},
    "formato": _esquema("plan_consulta", {
        "en_alcance": {"type": "boolean"},
        "respuesta_fuera_de_alcance": {"type": "string"},
        "desde": {"type": "string"},
        "hasta": {"type": "string"},
        "enfoque": {"type": "string"},
        "prioridad": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]},
        "encargo_analista": {"type": "string"},
        "encargo_estratega": {"type": "string"},
        "encargo_redactor": {"type": "string"},
        "razon": {"type": "string"},
    }),
    "max_pasos": 1,
    "max_tokens": 700,
}

_PREFIJO = """IMPORTANTE: esta vez no es el reporte de un dia. El administrador hizo una PREGUNTA (campo "pregunta") y los indicadores son del PERIODO que eligio el Orquestador (desde/hasta; "por_dia" trae el detalle diario). Donde las instrucciones digan "del dia", entiende "del periodo"; donde digan "manana", entiende "los proximos dias". Enfoca todo tu trabajo en responder esa pregunta y cumple el encargo del Orquestador.

"""


def _con_pregunta(agente, extra=""):
    """El mismo agente del reporte, orientado a responder la pregunta."""
    return {**agente, "instrucciones": _PREFIJO + agente["instrucciones"] + extra}


AGENTE_ANALISTA_CONSULTA = _con_pregunta(AGENTE_ANALISTA_DATOS)
AGENTE_ESTRATEGA_CONSULTA = _con_pregunta(AGENTE_ESTRATEGA)
AGENTE_REDACTOR_CONSULTA = _con_pregunta(
    AGENTE_REDACTOR,
    """

En una consulta: el titulo resume la RESPUESTA a la pregunta; la primera frase del resumen responde la pregunta de forma directa (si/no, cuanto, cual, por que) y las siguientes la sustentan con cifras. La calificacion es del periodo consultado.""",
)
AGENTE_EVALUADOR_CONSULTA = _con_pregunta(
    AGENTE_EVALUADOR_REPORTE,
    """

En una consulta, ademas: la utilidad y la claridad del Redactor dependen de que RESPONDA DIRECTAMENTE la pregunta; si no la responde, su nota debe ser menor a 6.""",
)

AGENTES_TRABAJO = {
    "analista": AGENTE_ANALISTA_CONSULTA,
    "estratega": AGENTE_ESTRATEGA_CONSULTA,
    "redactor": AGENTE_REDACTOR_CONSULTA,
}


# =========================================================
# GUARDAR Y LEER
# =========================================================

_COLUMNAS = """
    id, fecha_creacion, fecha_generacion, pregunta, estado, etapa,
    desde, hasta, metricas, hallazgos, recomendaciones,
    repartidores_sugeridos, franja_refuerzo, titulo, calificacion,
    resumen, conclusion, puntos, orquestacion, evaluacion, nota_final,
    costo_usd, duracion_ms, error
"""


def _fila_a_consulta(fila):

    estado = fila[4]

    return {
        "id": fila[0],
        "tipo": "CONSULTA",
        "creado": fila[1].isoformat() if fila[1] else None,
        "generado": fila[2].isoformat() if fila[2] else None,
        "pregunta": fila[3],
        "estado": estado,
        "etapa": ULTIMO_PASO if estado in ("LISTO", "SIN_DATOS", "FUERA_DE_ALCANCE") else fila[5],
        "desde": fila[6].isoformat() if fila[6] else None,
        "hasta": fila[7].isoformat() if fila[7] else None,
        # "fecha" para el panel (igual que un reporte): fin del periodo
        "fecha": (fila[7] or fila[1].date()).isoformat() if (fila[7] or fila[1]) else None,
        "origen": "CONSULTA",
        "metricas": json.loads(fila[8]) if fila[8] else None,
        "hallazgos": json.loads(fila[9]) if fila[9] else [],
        "recomendaciones": json.loads(fila[10]) if fila[10] else [],
        "repartidores_sugeridos": fila[11],
        "franja_refuerzo": fila[12],
        "titulo": fila[13],
        "calificacion": fila[14],
        "resumen": fila[15],
        "conclusion": fila[16],
        "puntos": json.loads(fila[17]) if fila[17] else None,
        "orquestacion": json.loads(fila[18]) if fila[18] else None,
        "evaluacion": json.loads(fila[19]) if fila[19] else None,
        "nota_final": _numero(fila[20]),
        "costo_usd": _numero(fila[21]),
        "duracion_ms": fila[22],
        "error": fila[23],
    }


def obtener_consulta(consulta_id):

    asegurar_tabla_consultas()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNAS} FROM consultas_agentes WHERE id = %s;",
                (consulta_id,),
            )
            fila = cur.fetchone()

    return _fila_a_consulta(fila) if fila else None


def listar_consultas(limite=10):

    asegurar_tabla_consultas()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNAS} FROM consultas_agentes "
                "ORDER BY fecha_creacion DESC LIMIT %s;",
                (limite,),
            )
            return [_fila_a_consulta(fila) for fila in cur.fetchall()]


def _actualizar(consulta_id, costo=0.0, duracion_ms=0, **campos):
    """Actualiza la consulta y suma costo y duracion del paso."""

    columnas = ", ".join(f"{columna} = %s" for columna in campos)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE consultas_agentes
                SET {columnas}{", " if columnas else ""}
                    costo_usd = COALESCE(costo_usd, 0) + %s,
                    duracion_ms = COALESCE(duracion_ms, 0) + %s,
                    fecha_generacion = NOW()
                WHERE id = %s;
            """, [*campos.values(), Decimal(str(round(costo, 6))), int(duracion_ms), consulta_id])


# =========================================================
# CREAR Y EJECUTAR PASOS
# =========================================================

def crear_consulta(pregunta, usuario_id):
    """Registra la pregunta (aun sin agentes). Limita las consultas por
    dia para cuidar el presupuesto del LLM."""

    asegurar_tabla_consultas()
    _verificar_llm()

    pregunta = re.sub(r"\s+", " ", str(pregunta or "")).strip()[:300]

    if len(pregunta) < 5:
        raise ValueError("Escribe una pregunta un poco más completa.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT COUNT(*)
                FROM consultas_agentes
                WHERE (fecha_creacion AT TIME ZONE '{ZONA}')::date
                      = (NOW() AT TIME ZONE '{ZONA}')::date;
            """)

            if cur.fetchone()[0] >= consultas_diarias_maximas():
                raise ValueError(
                    f"Se alcanzó el límite de {consultas_diarias_maximas()} consultas por día. "
                    "Inténtalo mañana."
                )

            cur.execute("""
                INSERT INTO consultas_agentes (usuario_id, pregunta, estado, etapa, costo_usd, duracion_ms)
                VALUES (%s, %s, 'PROCESANDO', -1, 0, 0)
                RETURNING id;
            """, (usuario_id, pregunta))

            consulta_id = cur.fetchone()[0]

    return obtener_consulta(consulta_id)


def _consulta_para_paso(consulta_id, paso):

    consulta = obtener_consulta(consulta_id)
    numero = PASOS.index(paso)

    if not consulta:
        raise PasoFueraDeOrden("La consulta no existe.")

    if consulta["estado"] not in ("PROCESANDO", "ERROR"):
        raise PasoFueraDeOrden("Esta consulta ya terminó. Haz una pregunta nueva.")

    etapa = consulta["etapa"] if consulta["etapa"] is not None else -1

    if etapa < numero - 1:
        raise PasoFueraDeOrden(
            f"El paso {numero} necesita que termine el paso {numero - 1} ({PASOS[numero - 1]})."
        )

    return consulta


def _ejecutar_paso(consulta_id, paso, agente, datos):

    _verificar_llm()

    costos = []
    inicio = time.monotonic()

    try:
        resultado = _ejecutar(agente, datos, costos, "REPORTE")

    except Exception as error:
        _actualizar(
            consulta_id,
            costo=sum(costos),
            duracion_ms=(time.monotonic() - inicio) * 1000,
            estado="ERROR",
            error=f"Paso {PASOS.index(paso)} ({paso}): {type(error).__name__}: {error}"[:300],
        )
        raise

    return resultado, sum(costos), (time.monotonic() - inicio) * 1000


def _con_flujo(consulta, agente, duracion, detalle=None, **extra):

    orquestacion = dict(consulta.get("orquestacion") or {})
    orquestacion.update(extra)
    orquestacion["flujo"] = list(orquestacion.get("flujo") or []) + [{
        "agente": agente,
        "detalle": detalle,
        "ms": int(duracion),
    }]

    return orquestacion


def _encargo(consulta, agente):
    return ((consulta.get("orquestacion") or {}).get("plan") or {}).get(f"encargo_{agente}", "")


def _fecha_valida(texto, hoy, defecto):

    try:
        valor = date.fromisoformat(str(texto)[:10])
    except ValueError:
        return defecto

    return min(max(valor, hoy - timedelta(days=DIAS_MAXIMOS)), hoy)


def _primer_dia_con_datos():

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT MIN((fecha_pedido AT TIME ZONE '{ZONA}')::date)
                FROM pedidos
                WHERE COALESCE(fuente_datos, 'REAL') = 'REAL';
            """)
            fila = cur.fetchone()

    return fila[0].isoformat() if fila and fila[0] else None


DIAS_SEMANA = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def paso_orquestador(consulta_id):
    """Paso 0: entiende la pregunta y elige el periodo."""

    consulta = _consulta_para_paso(consulta_id, "orquestador")
    hoy = fecha_hoy_lima()

    plan, costo, duracion = _ejecutar_paso(consulta_id, "orquestador", AGENTE_ORQUESTADOR_CONSULTA, {
        "pregunta": consulta["pregunta"],
        "hoy": hoy.isoformat(),
        "dia_de_la_semana_hoy": DIAS_SEMANA[hoy.weekday()],
        "datos_disponibles_desde": _primer_dia_con_datos(),
    })

    # El periodo lo propone el LLM; el codigo lo valida
    hasta = _fecha_valida(plan.get("hasta"), hoy, hoy)
    desde = _fecha_valida(plan.get("desde"), hoy, hasta - timedelta(days=6))

    if desde > hasta:
        desde, hasta = hasta, desde

    plan["desde"], plan["hasta"] = desde.isoformat(), hasta.isoformat()

    orquestacion = _json(_con_flujo(
        consulta, "orquestador", duracion, "Entiende la pregunta y elige el periodo", plan=plan,
    ))

    if not plan.get("en_alcance", True):
        _actualizar(
            consulta_id, costo=costo, duracion_ms=duracion,
            estado="FUERA_DE_ALCANCE",
            etapa=ULTIMO_PASO,
            orquestacion=orquestacion,
            titulo="Pregunta fuera del alcance",
            resumen=(plan.get("respuesta_fuera_de_alcance")
                     or "Solo puedo responder preguntas sobre la operación de Kimbos.")[:600],
            error=None,
        )
        return obtener_consulta(consulta_id)

    _actualizar(
        consulta_id, costo=costo, duracion_ms=duracion,
        estado="PROCESANDO",
        etapa=PASOS.index("orquestador"),
        desde=desde,
        hasta=hasta,
        orquestacion=orquestacion,
        error=None,
    )

    return obtener_consulta(consulta_id)


def paso_datos(consulta_id):
    """Paso 1: indicadores del periodo (SQL, sin LLM)."""

    consulta = _consulta_para_paso(consulta_id, "datos")
    inicio = time.monotonic()

    metricas = metricas_periodo(
        date.fromisoformat(consulta["desde"]),
        date.fromisoformat(consulta["hasta"]),
    )

    campos = {
        "metricas": _json(metricas),
        "etapa": PASOS.index("datos"),
        "estado": "PROCESANDO",
        "error": None,
    }

    # Sin pedidos en el periodo no hay nada que analizar (sin LLM)
    if metricas["pedidos"] == 0:
        campos.update(
            estado="SIN_DATOS",
            etapa=ULTIMO_PASO,
            titulo="Sin pedidos en el periodo",
            resumen=(
                f"No hubo pedidos reales entre el {consulta['desde']} y el {consulta['hasta']}, "
                "así que no hay datos para responder la pregunta."
            ),
        )

    _actualizar(consulta_id, duracion_ms=(time.monotonic() - inicio) * 1000, **campos)

    return obtener_consulta(consulta_id)


def _entrada(consulta, agente, observacion=None):

    base = {
        "pregunta": consulta["pregunta"],
        "periodo": {"desde": consulta["desde"], "hasta": consulta["hasta"]},
        "indicadores_del_dia": consulta["metricas"],
        "encargo": _encargo(consulta, agente),
    }

    if agente in ("estratega", "redactor"):
        base["hallazgos"] = consulta["hallazgos"]

    if agente == "redactor":
        base.update(
            fecha=f"{consulta['desde']} a {consulta['hasta']}",
            recomendaciones=consulta["recomendaciones"],
            repartidores_sugeridos=consulta["repartidores_sugeridos"],
            franja_refuerzo=consulta["franja_refuerzo"],
        )

    if observacion:
        base["observacion_evaluador"] = observacion

    return base


def _trabajo(consulta_id, consulta, agente, observacion=None):
    """Trabajo de un agente de automatizacion -> columnas a guardar."""

    resultado, costo, duracion = _ejecutar_paso(
        consulta_id, agente, AGENTES_TRABAJO[agente], _entrada(consulta, agente, observacion),
    )

    if agente == "analista":
        campos = {"hallazgos": _json(resultado["hallazgos"][:6])}

    elif agente == "estratega":
        campos = {
            "recomendaciones": _json(resultado["recomendaciones"][:3]),
            "repartidores_sugeridos": max(1, min(int(resultado["repartidores_sugeridos"]), 6)),
            "franja_refuerzo": (resultado.get("franja_refuerzo") or "")[:60] or None,
        }

    else:
        campos = {
            "titulo": resultado["titulo"][:200],
            "calificacion": resultado["calificacion"],
            "resumen": resultado["resumen"],
            "conclusion": resultado["conclusion"],
            "puntos": _json({
                "lo_que_funciono": [str(p)[:200] for p in resultado.get("lo_que_funciono", [])[:3]],
                "a_vigilar": [str(p)[:200] for p in resultado.get("a_vigilar", [])[:3]],
                "resumen_sintetico": [
                    {"indicador": x["indicador"], "estado": x["estado"], "lectura": str(x["lectura"])[:300]}
                    for x in resultado.get("resumen_sintetico", [])[:4]
                ],
            }),
        }

    return campos, costo, duracion


def _paso_agente(consulta_id, agente):

    consulta = _consulta_para_paso(consulta_id, agente)

    campos, costo, duracion = _trabajo(consulta_id, consulta, agente)

    _actualizar(
        consulta_id, costo=costo, duracion_ms=duracion,
        estado="PROCESANDO",
        etapa=PASOS.index(agente),
        orquestacion=_json(_con_flujo(consulta, agente, duracion)),
        error=None,
        **campos,
    )

    return obtener_consulta(consulta_id)


def _evaluar(consulta_id, consulta):

    evaluacion, costo, duracion = _ejecutar_paso(consulta_id, "evaluador", AGENTE_EVALUADOR_CONSULTA, {
        "pregunta": consulta["pregunta"],
        "periodo": {"desde": consulta["desde"], "hasta": consulta["hasta"]},
        "indicadores_del_dia": consulta["metricas"],
        "plan_orquestador": (consulta.get("orquestacion") or {}).get("plan"),
        "analista": {"hallazgos": consulta["hallazgos"]},
        "estratega": {
            "recomendaciones": consulta["recomendaciones"],
            "repartidores_sugeridos": consulta["repartidores_sugeridos"],
            "franja_refuerzo": consulta["franja_refuerzo"],
        },
        "redactor": {
            "titulo": consulta["titulo"],
            "calificacion": consulta["calificacion"],
            "resumen": consulta["resumen"],
            **(consulta.get("puntos") or {}),
            "conclusion": consulta["conclusion"],
        },
    })

    return _notas(evaluacion, AGENTES_REPORTE), costo, duracion


def paso_evaluador(consulta_id):
    """Paso 5: el Evaluador califica y el Orquestador decide (1 reintento
    del agente con nota baja y de los que dependen de el)."""

    consulta = _consulta_para_paso(consulta_id, "evaluador")
    costo_total = 0.0
    duracion_total = 0.0

    evaluacion, costo, duracion = _evaluar(consulta_id, consulta)
    costo_total += costo
    duracion_total += duracion
    orquestacion = _con_flujo(consulta, "evaluador", duracion)

    decision, costo, duracion = _ejecutar_paso(consulta_id, "evaluador", AGENTE_ORQUESTADOR_CIERRE, {
        "pregunta": consulta["pregunta"],
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
            (a["observacion"] for a in evaluacion["agentes"] if a["agente"] == reintento), "",
        )

        for agente in AGENTES_REPORTE[AGENTES_REPORTE.index(reintento):]:

            campos, costo, duracion = _trabajo(
                consulta_id, consulta, agente, observacion if agente == reintento else None,
            )
            costo_total += costo
            duracion_total += duracion

            for clave, valor in campos.items():
                consulta[clave] = (
                    json.loads(valor) if clave in ("hallazgos", "recomendaciones", "puntos") else valor
                )

            _actualizar(consulta_id, **campos)

            orquestacion = _con_flujo(
                {"orquestacion": orquestacion}, agente, duracion,
                "Reintento con la observación del evaluador" if agente == reintento
                else "Actualiza con el trabajo corregido",
            )

        consulta["orquestacion"] = orquestacion
        evaluacion, costo, duracion = _evaluar(consulta_id, consulta)
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

    _actualizar(
        consulta_id, costo=costo_total, duracion_ms=duracion_total,
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

    return obtener_consulta(consulta_id)


EJECUTAR_PASO = {
    "orquestador": paso_orquestador,
    "datos": paso_datos,
    "analista": lambda consulta_id: _paso_agente(consulta_id, "analista"),
    "estratega": lambda consulta_id: _paso_agente(consulta_id, "estratega"),
    "redactor": lambda consulta_id: _paso_agente(consulta_id, "redactor"),
    "evaluador": paso_evaluador,
}
