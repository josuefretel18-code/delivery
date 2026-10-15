"""
Horario de atencion de la tienda (hora de Lima).

Por defecto 11:00 a 22:00. Se cambia con TIENDA_APERTURA y
TIENDA_CIERRE (formato HH:MM). Fuera de horario no se aceptan pedidos.
"""

import os
from datetime import datetime, time
from zoneinfo import ZoneInfo


ZONA = ZoneInfo("America/Lima")


def _hora(variable, defecto):

    texto = os.getenv(variable, defecto).strip()

    try:
        horas, minutos = texto.split(":")
        return time(int(horas), int(minutos))
    except ValueError:
        horas, minutos = defecto.split(":")
        return time(int(horas), int(minutos))


def apertura():
    return _hora("TIENDA_APERTURA", "11:00")


def cierre():
    return _hora("TIENDA_CIERRE", "22:00")


def formato_12h(hora):
    """11:00 -> '11:00 a. m.', 22:00 -> '10:00 p. m.'"""

    sufijo = "a. m." if hora.hour < 12 else "p. m."
    hora12 = hora.hour % 12 or 12

    return f"{hora12}:{hora.minute:02d} {sufijo}"


def texto_horario():
    return f"{formato_12h(apertura())} – {formato_12h(cierre())}"


def tienda_abierta(momento=None):

    ahora = (momento or datetime.now(ZONA)).astimezone(ZONA).time()
    abre, cierra = apertura(), cierre()

    # Horario que cruza la medianoche (por ejemplo 18:00 a 02:00)
    if cierra <= abre:
        return ahora >= abre or ahora < cierra

    return abre <= ahora < cierra


def estado_horario():

    abierta = tienda_abierta()

    return {
        "abierto": abierta,
        "apertura": formato_12h(apertura()),
        "cierre": formato_12h(cierre()),
        "texto": texto_horario(),
        "mensaje": (
            f"Abierto ahora · cerramos a las {formato_12h(cierre())}"
            if abierta
            else f"Cerrado ahora · abrimos a las {formato_12h(apertura())}"
        ),
    }


def mensaje_cerrado():

    return (
        "Kimbos está cerrado en este momento. Atendemos de "
        f"{texto_horario()}. Puedes revisar el menú y pedir cuando abramos."
    )
