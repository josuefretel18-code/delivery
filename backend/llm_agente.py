"""
Agente con LLM (OpenAI, API Responses) para los asistentes de Kimbos.

El modelo no accede a la BD: solo puede llamar a las herramientas que
le da cada asistente (backend/llm_herramientas.py), que ya filtran por
el usuario de la sesion.

Control de consumo (objetivo: menos de USD 10 al mes):
- Pocos pasos por mensaje (LLM_MAX_PASOS) y salida corta.
- Razonamiento minimo: el asistente consulta datos, no resuelve
  problemas complejos.
- Historial corto (ultimos mensajes, recortados).
- Herramientas que devuelven datos resumidos.
- Limite diario de mensajes por usuario.
- Corte por presupuesto mensual: primero se apaga el asistente del
  admin y despues el del cliente. La tienda sigue funcionando.
- Cada mensaje se registra en la tabla llm_uso (tokens y costo).
"""

import json
import os
import time
from decimal import Decimal

from db import get_connection


# USD por millon de tokens: (entrada, entrada en cache, salida).
# Los tokens de razonamiento se cobran como salida.
PRECIOS = {
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5-nano": (0.05, 0.005, 0.40),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
}

MODELO_POR_DEFECTO = "gpt-5-mini"

MAX_CARACTERES_MENSAJE = 500
MAX_MENSAJES_HISTORIAL = 6


class LimiteAlcanzado(Exception):
    """El asistente no puede responder (presupuesto, limite diario o
    sin configurar). El mensaje es apto para mostrar al usuario."""


def _float_env(nombre, defecto):

    try:
        return float(os.getenv(nombre, defecto))
    except ValueError:
        return float(defecto)


def configuracion():

    return {
        "modelo": os.getenv("LLM_MODELO", MODELO_POR_DEFECTO).strip(),
        "presupuesto_usd": _float_env("LLM_PRESUPUESTO_USD", 10),
        "corte_admin_usd": _float_env("LLM_CORTE_ADMIN_USD", 7),
        "corte_cliente_usd": _float_env("LLM_CORTE_CLIENTE_USD", 8),
        "mensajes_diarios": {
            "CLIENTE": int(_float_env("LLM_MENSAJES_DIARIOS_CLIENTE", 15)),
            "ADMIN": int(_float_env("LLM_MENSAJES_DIARIOS_ADMIN", 40)),
        },
        "max_pasos": int(_float_env("LLM_MAX_PASOS", 3)),
        "max_tokens_salida": int(_float_env("LLM_MAX_TOKENS_SALIDA", 700)),
    }


def llm_configurado():

    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def calcular_costo(modelo, entrada, cache, salida):

    precio_entrada, precio_cache, precio_salida = PRECIOS.get(
        modelo, PRECIOS[MODELO_POR_DEFECTO]
    )

    costo = (
        (entrada - cache) * precio_entrada
        + cache * precio_cache
        + salida * precio_salida
    ) / 1_000_000

    return round(costo, 6)


# =========================================================
# REGISTRO (tabla llm_uso)
# =========================================================

_TABLA_LISTA = {"ok": False}


def asegurar_tabla():

    if _TABLA_LISTA["ok"]:
        return

    ruta = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sql",
        "agregar_llm_uso.sql",
    )

    with open(ruta, encoding="utf-8") as archivo:
        script = archivo.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(script)

    _TABLA_LISTA["ok"] = True


def gasto_mes_usd():

    asegurar_tabla()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(costo_usd), 0)
                FROM llm_uso
                WHERE fecha >= date_trunc('month', NOW());
            """)

            return float(cur.fetchone()[0])


def mensajes_hoy(usuario_id, asistente):

    asegurar_tabla()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM llm_uso
                WHERE usuario_id = %s
                  AND asistente = %s
                  AND fecha >= date_trunc(
                      'day', NOW() AT TIME ZONE 'America/Lima'
                  ) AT TIME ZONE 'America/Lima';
            """, (usuario_id, asistente))

            return cur.fetchone()[0]


def disponibilidad(usuario_id, asistente):
    """{activo, motivo, restantes_hoy, limite_diario}"""

    config = configuracion()
    limite = config["mensajes_diarios"][asistente]

    if not llm_configurado():
        return {
            "activo": False,
            "motivo": "El asistente no esta configurado.",
            "restantes_hoy": 0,
            "limite_diario": limite,
        }

    corte = (
        config["corte_admin_usd"]
        if asistente == "ADMIN"
        else config["corte_cliente_usd"]
    )

    if gasto_mes_usd() >= corte:
        return {
            "activo": False,
            "motivo": (
                "El asistente esta en pausa hasta el proximo mes "
                "(limite de consumo alcanzado)."
            ),
            "restantes_hoy": 0,
            "limite_diario": limite,
        }

    restantes = max(limite - mensajes_hoy(usuario_id, asistente), 0)

    return {
        "activo": restantes > 0,
        "motivo": (
            None if restantes > 0
            else f"Alcanzaste el limite de {limite} mensajes por hoy."
        ),
        "restantes_hoy": restantes,
        "limite_diario": limite,
    }


def registrar_uso(usuario_id, asistente, modelo, uso, pasos,
                  herramientas, duracion_ms, ok=True, error=None):

    costo = calcular_costo(
        modelo, uso["entrada"], uso["cache"], uso["salida"]
    )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO llm_uso (
                        usuario_id, asistente, modelo,
                        tokens_entrada, tokens_cache,
                        tokens_salida, tokens_razonamiento,
                        pasos, herramientas, costo_usd,
                        duracion_ms, ok, error
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s);
                """, (
                    usuario_id, asistente, modelo,
                    uso["entrada"], uso["cache"],
                    uso["salida"], uso["razonamiento"],
                    pasos, ",".join(herramientas)[:200] or None,
                    Decimal(str(costo)), duracion_ms, ok,
                    (error or "")[:300] or None,
                ))
    except Exception as fallo:
        print(f"[LLM] No se pudo registrar el uso: {fallo}", flush=True)

    return costo


# =========================================================
# AGENTE
# =========================================================

_CLIENTE = {"instancia": None}


def _cliente_openai():

    if _CLIENTE["instancia"] is None:
        from openai import OpenAI

        _CLIENTE["instancia"] = OpenAI(timeout=40, max_retries=1)

    return _CLIENTE["instancia"]


def _limpiar_historial(historial):
    """Solo texto de usuario/asistente, recortado. El historial viene
    del navegador: no se confia en su contenido ni en su tamano."""

    limpio = []

    for mensaje in (historial or [])[-MAX_MENSAJES_HISTORIAL:]:

        if not isinstance(mensaje, dict):
            continue

        rol = mensaje.get("rol")
        texto = str(mensaje.get("texto", "")).strip()

        if rol in ("user", "assistant") and texto:
            limpio.append({
                "role": rol,
                "content": texto[:MAX_CARACTERES_MENSAJE],
            })

    return limpio


def responder(asistente, usuario, mensaje, historial, instrucciones,
              herramientas):
    """
    Ejecuta el agente y devuelve {respuesta, costo_usd, pasos,
    herramientas, restantes_hoy}.

    herramientas: {nombre: (definicion, funcion)}; cada funcion
    recibe (usuario, **argumentos) y devuelve datos serializables.
    """

    mensaje = str(mensaje or "").strip()[:MAX_CARACTERES_MENSAJE]

    if not mensaje:
        raise ValueError("Escribe un mensaje.")

    estado = disponibilidad(usuario["id"], asistente)

    if not estado["activo"]:
        raise LimiteAlcanzado(estado["motivo"])

    config = configuracion()
    modelo = config["modelo"]

    entrada = _limpiar_historial(historial)
    entrada.append({"role": "user", "content": mensaje})

    definiciones = [definicion for definicion, _ in herramientas.values()]

    uso = {"entrada": 0, "cache": 0, "salida": 0, "razonamiento": 0}
    usadas = []
    pasos = 0
    inicio = time.monotonic()
    respuesta = None

    try:

        for paso in range(config["max_pasos"]):

            ultimo_paso = paso == config["max_pasos"] - 1

            respuesta = _cliente_openai().responses.create(
                model=modelo,
                instructions=instrucciones,
                input=entrada,
                tools=definiciones,
                # En el ultimo paso se obliga a responder con lo que
                # ya tiene, para no encadenar llamadas sin fin.
                tool_choice="none" if ultimo_paso else "auto",
                parallel_tool_calls=True,
                max_output_tokens=config["max_tokens_salida"],
                reasoning={"effort": "minimal"},
                text={"verbosity": "low"},
                # Sin guardar conversaciones en OpenAI; el
                # razonamiento viaja cifrado entre pasos.
                store=False,
                include=["reasoning.encrypted_content"],
                # Agrupa las peticiones de cada asistente para que
                # OpenAI reutilice el prefijo en cache.
                prompt_cache_key=f"kimbos-{asistente.lower()}",
                safety_identifier=f"kimbos-{usuario['id']}",
            )

            pasos += 1

            if respuesta.usage:
                detalles_entrada = respuesta.usage.input_tokens_details
                detalles_salida = respuesta.usage.output_tokens_details

                uso["entrada"] += respuesta.usage.input_tokens
                uso["salida"] += respuesta.usage.output_tokens
                uso["cache"] += (
                    detalles_entrada.cached_tokens or 0
                    if detalles_entrada else 0
                )
                uso["razonamiento"] += (
                    detalles_salida.reasoning_tokens or 0
                    if detalles_salida else 0
                )

            llamadas = [
                item for item in respuesta.output
                if item.type == "function_call"
            ]

            if not llamadas:
                break

            entrada += [
                item.model_dump(exclude_none=True)
                for item in respuesta.output
            ]

            for llamada in llamadas:

                usadas.append(llamada.name)

                entrada.append({
                    "type": "function_call_output",
                    "call_id": llamada.call_id,
                    "output": _ejecutar_herramienta(
                        herramientas, usuario, llamada
                    ),
                })

        texto = (respuesta.output_text or "").strip() if respuesta else ""

        if not texto:
            texto = (
                "No pude completar la respuesta. "
                "Intenta con una pregunta mas concreta."
            )

    except Exception as error:

        registrar_uso(
            usuario["id"], asistente, modelo, uso, pasos, usadas,
            int((time.monotonic() - inicio) * 1000),
            ok=False, error=f"{type(error).__name__}: {error}",
        )

        raise

    costo = registrar_uso(
        usuario["id"], asistente, modelo, uso, pasos, usadas,
        int((time.monotonic() - inicio) * 1000),
    )

    return {
        "respuesta": texto,
        "costo_usd": costo,
        "pasos": pasos,
        "herramientas": usadas,
        "restantes_hoy": max(estado["restantes_hoy"] - 1, 0),
    }


def _ejecutar_herramienta(herramientas, usuario, llamada):

    if llamada.name not in herramientas:
        return json.dumps({"error": "Herramienta no disponible"})

    _, funcion = herramientas[llamada.name]

    try:
        argumentos = json.loads(llamada.arguments or "{}")
        resultado = funcion(usuario, **argumentos)
    except Exception as error:
        print(f"[LLM] Herramienta {llamada.name}: {error}", flush=True)

        from requests import RequestException

        resultado = {
            "error": (
                "El servicio de Machine Learning no responde"
                if isinstance(error, RequestException)
                else "No se pudo obtener la informacion"
            )
        }

    return json.dumps(resultado, ensure_ascii=False, default=str)


# =========================================================
# RESUMEN DE CONSUMO (panel del admin)
# =========================================================

def resumen_consumo():

    asegurar_tabla()
    config = configuracion()

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    asistente,
                    COUNT(*),
                    COALESCE(SUM(costo_usd), 0),
                    COALESCE(SUM(tokens_entrada), 0),
                    COALESCE(SUM(tokens_cache), 0),
                    COALESCE(SUM(tokens_salida), 0),
                    COUNT(*) FILTER (WHERE NOT ok)
                FROM llm_uso
                WHERE fecha >= date_trunc('month', NOW())
                GROUP BY asistente;
            """)

            por_asistente = {
                fila[0]: {
                    "mensajes": fila[1],
                    "costo_usd": round(float(fila[2]), 4),
                    "tokens_entrada": int(fila[3]),
                    "tokens_cache": int(fila[4]),
                    "tokens_salida": int(fila[5]),
                    "errores": fila[6],
                }
                for fila in cur.fetchall()
            }

            cur.execute("""
                SELECT
                    TO_CHAR(fecha AT TIME ZONE 'America/Lima', 'YYYY-MM-DD'),
                    COUNT(*),
                    COALESCE(SUM(costo_usd), 0)
                FROM llm_uso
                WHERE fecha >= NOW() - INTERVAL '14 days'
                GROUP BY 1
                ORDER BY 1;
            """)

            por_dia = [
                {
                    "dia": fila[0],
                    "mensajes": fila[1],
                    "costo_usd": round(float(fila[2]), 4),
                }
                for fila in cur.fetchall()
            ]

            cur.execute("""
                SELECT
                    TO_CHAR(u.fecha AT TIME ZONE 'America/Lima', 'DD/MM HH24:MI'),
                    u.asistente,
                    COALESCE(us.nombre_completo, '-'),
                    u.modelo,
                    u.tokens_entrada,
                    u.tokens_cache,
                    u.tokens_salida,
                    u.pasos,
                    u.herramientas,
                    u.costo_usd,
                    u.duracion_ms,
                    u.ok
                FROM llm_uso u
                LEFT JOIN usuarios us
                    ON us.id = u.usuario_id
                ORDER BY u.id DESC
                LIMIT 15;
            """)

            ultimos = [
                {
                    "fecha": fila[0],
                    "asistente": fila[1],
                    "usuario": fila[2],
                    "modelo": fila[3],
                    "tokens_entrada": fila[4],
                    "tokens_cache": fila[5],
                    "tokens_salida": fila[6],
                    "pasos": fila[7],
                    "herramientas": fila[8],
                    "costo_usd": float(fila[9]),
                    "duracion_ms": fila[10],
                    "ok": fila[11],
                }
                for fila in cur.fetchall()
            ]

    gasto = round(sum(a["costo_usd"] for a in por_asistente.values()), 4)
    mensajes = sum(a["mensajes"] for a in por_asistente.values())

    return {
        "configurado": llm_configurado(),
        "modelo": config["modelo"],
        "precios_usd_millon": dict(zip(
            ("entrada", "cache", "salida"),
            PRECIOS.get(config["modelo"], PRECIOS[MODELO_POR_DEFECTO]),
        )),
        "gasto_mes_usd": gasto,
        "presupuesto_usd": config["presupuesto_usd"],
        "corte_admin_usd": config["corte_admin_usd"],
        "corte_cliente_usd": config["corte_cliente_usd"],
        "admin_activo": gasto < config["corte_admin_usd"],
        "cliente_activo": gasto < config["corte_cliente_usd"],
        "mensajes_mes": mensajes,
        "costo_promedio_usd": round(gasto / mensajes, 6) if mensajes else 0,
        "limites_diarios": config["mensajes_diarios"],
        "max_pasos": config["max_pasos"],
        "max_tokens_salida": config["max_tokens_salida"],
        "por_asistente": por_asistente,
        "por_dia": por_dia,
        "ultimos": ultimos,
    }
