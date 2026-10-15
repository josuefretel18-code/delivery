import os

import psycopg
from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Pool de conexiones (solo la app web lo activa con usar_pool()).
# Abrir una conexion nueva a la BD tarda ~1 s (TLS); con el pool las
# conexiones se reutilizan entre peticiones. Los scripts de ML y el job
# de Google Cloud siguen abriendo conexiones directas.
_POOL = {"instancia": None}


def usar_pool(minimo=1, maximo=6):

    if _POOL["instancia"] is not None or not DATABASE_URL:
        return

    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        DATABASE_URL,
        min_size=minimo,
        max_size=maximo,
        # Se cierran antes de que el servidor corte las inactivas
        max_idle=180,
        max_lifetime=900,
        timeout=20,
        kwargs={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
        open=False,
    )

    # Sin esperar: la app arranca aunque la BD tarde en responder.
    pool.open(wait=False)

    _POOL["instancia"] = pool


def get_connection():
    """Usar siempre como `with get_connection() as conn:`. Al salir del
    bloque se confirma la transaccion (o se revierte si hubo error) y la
    conexion vuelve al pool o se cierra."""

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no está configurada en el archivo .env"
        )

    if _POOL["instancia"] is not None:
        return _POOL["instancia"].connection()

    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=10
    )


def probar_conexion():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    NOW();
                """
            )

            resultado = cur.fetchone()

            return {
                "database": resultado[0],
                "usuario": resultado[1],
                "fecha_servidor": resultado[2].isoformat()
            }
