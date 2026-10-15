import os
import threading
from contextlib import contextmanager

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
        # Si la BD estuvo caida (por ejemplo, Aiven gratis apagado), el
        # pool sigue intentando reconectar en lugar de rendirse.
        reconnect_timeout=24 * 3600,
        # Antes de entregar una conexion se comprueba que siga viva (la
        # BD puede cerrar las inactivas); si no, se reemplaza por otra.
        check=ConnectionPool.check_connection,
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


# Pool OCUPADO (mucho trafico): se espera en fila; como cada peticion
# usa una sola conexion, se liberan en milisegundos.
# Pool ROTO (sin ninguna conexion viva, por ejemplo tras una caida de
# la BD): conexion directa al instante y reparacion en segundo plano.
ESPERA_POOL_SEGUNDOS = 15

_REPARANDO = {"activo": False}

# Conexion en uso por el hilo actual (cada peticion corre en su hilo)
_LOCAL = threading.local()


def _reparar_pool(pool):
    """En segundo plano: revisa las conexiones del pool y repone las
    que falten (por ejemplo, despues de que la BD estuvo apagada)."""

    if _REPARANDO["activo"]:
        return

    _REPARANDO["activo"] = True

    def tarea():
        try:
            pool.check()
        except Exception as error:
            print(f"[BD] No se pudo reparar el pool: {error}", flush=True)
        finally:
            _REPARANDO["activo"] = False

    threading.Thread(target=tarea, daemon=True).start()


def _conexion_directa():

    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=10
    )


@contextmanager
def get_connection():
    """Usar siempre como `with get_connection() as conn:`. Al salir del
    bloque se confirma la transaccion (o se revierte si hubo error) y la
    conexion vuelve al pool o se cierra.

    UNA CONEXION POR PETICION: si dentro de un bloque se vuelve a pedir
    una conexion (por ejemplo, crear un pedido consulta los repartidores
    en turno), se reutiliza la misma en vez de pedir otra al pool. Asi una
    peticion nunca espera una segunda conexion y el pool no puede quedar
    bloqueado. La parte interna va en un punto de guardado (SAVEPOINT):
    si falla, se deshace solo esa parte y la operacion principal sigue.

    Si el pool no entrega una conexion (BD caida), se usa una conexion
    directa y el pool se repara en segundo plano."""

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no está configurada en el archivo .env"
        )

    # Uso anidado: misma conexion, protegida con un punto de guardado
    actual = getattr(_LOCAL, "conn", None)

    if actual is not None and not actual.closed:
        with actual.transaction():
            yield actual
        return

    pool = _POOL["instancia"]
    conn = None
    del_pool = False

    if pool is not None:

        from psycopg_pool import PoolTimeout

        if pool.get_stats().get("pool_size", 0) == 0:
            # Sin conexiones vivas: no esperar, conexion directa
            print("[BD] Pool sin conexiones: se usa una conexión directa", flush=True)
            _reparar_pool(pool)

        else:
            try:
                conn = pool.getconn(timeout=ESPERA_POOL_SEGUNDOS)
                del_pool = True
            except PoolTimeout:
                print("[BD] El pool no respondió: se usa una conexión directa", flush=True)
                _reparar_pool(pool)

    if conn is None:
        conn = _conexion_directa()

    _LOCAL.conn = conn

    try:
        yield conn
        conn.commit()

    except BaseException:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

    finally:
        _LOCAL.conn = None

        if del_pool:
            pool.putconn(conn)
        else:
            conn.close()


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
