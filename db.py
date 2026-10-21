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
_POOL = {"instancia": None, "minimo": 1, "maximo": 6}


def _crear_pool(minimo, maximo):

    from psycopg_pool import ConnectionPool

    return ConnectionPool(
        DATABASE_URL,
        min_size=minimo,
        max_size=maximo,
        # Se cierran antes de que el servidor corte las inactivas
        max_idle=180,
        max_lifetime=900,
        timeout=20,
        # Reintentos de reconexion por poco tiempo: psycopg_pool espera
        # cada vez el doble entre intentos y, si la BD estuvo apagada
        # horas (Aiven gratis), el siguiente intento quedaba para dentro
        # de horas con el pool "trabado". Si no conecta, este modulo
        # crea un pool nuevo (ver _renovar_pool).
        reconnect_timeout=120,
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


def usar_pool(minimo=1, maximo=6):

    if _POOL["instancia"] is not None or not DATABASE_URL:
        return

    pool = _crear_pool(minimo, maximo)

    # Sin esperar: la app arranca aunque la BD tarde en responder.
    pool.open(wait=False)

    _POOL.update(instancia=pool, minimo=minimo, maximo=maximo)


# Cada peticion usa UNA conexion y el pool tiene mas conexiones (10)
# que hilos el servidor (8): un pool sano entrega al instante. Si no
# entrega en estos segundos esta trabado (la BD estuvo apagada): se usa
# una conexion directa y se crea un pool nuevo en segundo plano.
ESPERA_POOL_SEGUNDOS = 3

_REPARANDO = {"activo": False}

# Conexiones del pool entregadas y aun no devueltas. Si el pool no
# entrega una conexion y este numero es menor que el maximo, el pool
# esta trabado (no ocupado): solo entonces se renueva.
_EN_USO = {"cantidad": 0}
_CANDADO = threading.Lock()

# Conexion en uso por el hilo actual (cada peticion corre en su hilo)
_LOCAL = threading.local()


def _renovar_pool(pool_trabado):
    """En segundo plano: crea un pool nuevo y, cuando ya tiene una
    conexion lista, reemplaza al trabado (que se cierra). Mientras tanto
    las peticiones usan conexiones directas."""

    if _REPARANDO["activo"]:
        return

    _REPARANDO["activo"] = True

    def tarea():

        nuevo = None

        try:
            nuevo = _crear_pool(_POOL["minimo"], _POOL["maximo"])
            nuevo.open(wait=True, timeout=30)

            _POOL["instancia"] = nuevo
            print("[BD] Pool renovado: conexiones listas", flush=True)

            try:
                pool_trabado.close(timeout=2)
            except Exception:
                pass

        except Exception as error:
            print(f"[BD] No se pudo renovar el pool: {error}", flush=True)

            if nuevo is not None:
                try:
                    nuevo.close(timeout=1)
                except Exception:
                    pass

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

    Si el pool no entrega una conexion (BD caida o pool trabado), se usa
    una conexion directa y se crea un pool nuevo en segundo plano."""

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
            _renovar_pool(pool)

        else:
            try:
                conn = pool.getconn(timeout=ESPERA_POOL_SEGUNDOS)
                del_pool = True

                with _CANDADO:
                    _EN_USO["cantidad"] += 1

            except PoolTimeout:

                with _CANDADO:
                    ocupado = _EN_USO["cantidad"] >= _POOL["maximo"]

                if ocupado:
                    # Mucho trafico: todas las conexiones estan en uso
                    print("[BD] Pool ocupado: se usa una conexión directa", flush=True)
                else:
                    print("[BD] El pool no respondió: se usa una conexión directa", flush=True)
                    _renovar_pool(pool)

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

            with _CANDADO:
                _EN_USO["cantidad"] -= 1

            try:
                pool.putconn(conn)
            except Exception:
                # El pool se renovo mientras se usaba: se cierra suelta
                conn.close()
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
