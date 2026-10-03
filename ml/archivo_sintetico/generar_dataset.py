import math
import random
import heapq
import sys

from pathlib import Path
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from werkzeug.security import generate_password_hash


# =========================================================
# PERMITIR IMPORTAR ARCHIVOS DEL PROYECTO
# =========================================================

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent

if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))


from db import get_connection

# =========================================================
# CONFIGURACIÓN
# =========================================================

CANTIDAD_PEDIDOS = 1000
TAMANO_LOTE = 20

FECHA_INICIO = date(2026, 9, 8)
FECHA_FIN = date(2026, 9, 27)

TZ = ZoneInfo("America/Lima")

RANDOM_SEED = 20260927

random.seed(RANDOM_SEED)


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

def limitar(valor, minimo, maximo):
    return max(minimo, min(valor, maximo))


def sigmoide(x):
    return 1 / (1 + math.exp(-x))


def obtener_fechas():
    fechas = []

    actual = FECHA_INICIO

    while actual <= FECHA_FIN:
        fechas.append(actual)
        actual += timedelta(days=1)

    return fechas


def peso_dia(fecha):
    """
    Python:
    lunes = 0
    ...
    domingo = 6
    """

    dia = fecha.weekday()

    if dia <= 3:
        return 1.00

    if dia == 4:
        return 1.25

    if dia == 5:
        return 1.60

    return 1.40


def generar_hora():
    """
    Distribución aproximada:

    11:00 - 14:59 → almuerzo
    15:00 - 17:59 → menor movimiento
    18:00 - 22:29 → cena / hora punta
    """

    r = random.random()

    if r < 0.35:

        hora = random.randint(11, 14)
        minuto = random.randint(0, 59)

    elif r < 0.48:

        hora = random.randint(15, 17)
        minuto = random.randint(0, 59)

    else:

        hora = random.randint(18, 22)

        if hora == 22:
            minuto = random.randint(0, 29)
        else:
            minuto = random.randint(0, 59)

    return time(
        hour=hora,
        minute=minuto,
        second=random.randint(0, 59)
    )


def generar_coordenadas(
    lat_origen,
    lon_origen,
    distancia_km
):
    """
    Genera un punto aproximado alrededor de la sede.
    Solo se utiliza para datos históricos sintéticos.
    """

    angulo = random.uniform(
        0,
        2 * math.pi
    )

    distancia_grados_lat = (
        distancia_km / 111.0
    )

    cos_lat = math.cos(
        math.radians(lat_origen)
    )

    distancia_grados_lon = (
        distancia_km
        / (111.0 * cos_lat)
    )

    latitud = (
        lat_origen
        + distancia_grados_lat
        * math.cos(angulo)
    )

    longitud = (
        lon_origen
        + distancia_grados_lon
        * math.sin(angulo)
    )

    return (
        round(latitud, 7),
        round(longitud, 7)
    )


def calcular_duracion_ruta(distancia_km):
    """
    Aproximación para históricos sintéticos.
    Los pedidos nuevos reales seguirán usando Google Maps.
    """

    base = 4.5 + distancia_km * 2.35

    ruido = random.uniform(
        -2.0,
        3.0
    )

    return max(
        5,
        round(base + ruido)
    )


def zona_por_distancia(distancia_km):

    if distancia_km <= 2.5:
        return "CERCANA"

    if distancia_km <= 5.0:
        return "MEDIA"

    return "LEJANA"


# =========================================================
# CONEXIÓN
# =========================================================

conn = get_connection()

try:

    cur = conn.cursor()

    # =====================================================
    # EVITAR DUPLICADOS
    # =====================================================

    cur.execute("""
        SELECT COUNT(*)
        FROM pedidos
        WHERE fuente_datos = 'SINTETICO_ML';
    """)

    existentes = cur.fetchone()[0]

    if existentes > 0:

        print(
            f"Se encontraron {existentes} pedidos "
            f"historicos ya guardados."
        )

        print(
            "El generador continuara sin duplicarlos."
        )

    # =====================================================
    # SEDE
    # =====================================================

    cur.execute("""
        SELECT
            id,
            nombre,
            direccion,
            latitud,
            longitud,
            negocio_nombre
        FROM sedes
        WHERE activa = TRUE
        ORDER BY id
        LIMIT 1;
    """)

    sede = cur.fetchone()

    if sede is None:
        raise RuntimeError(
            "No existe una sede activa."
        )

    (
        sede_id,
        sede_nombre,
        sede_direccion,
        sede_latitud,
        sede_longitud,
        negocio_nombre
    ) = sede

    lat_origen = float(
        sede_latitud
    )

    lon_origen = float(
        sede_longitud
    )

    # =====================================================
    # ESTADOS
    # =====================================================

    cur.execute("""
        SELECT codigo, id
        FROM estados_pedido
        WHERE codigo IN (
            'REGISTRADO',
            'PREPARANDO',
            'EN_RUTA',
            'ENTREGADO'
        );
    """)

    estados = {
        codigo: estado_id
        for codigo, estado_id
        in cur.fetchall()
    }

    necesarios = {
        "REGISTRADO",
        "PREPARANDO",
        "EN_RUTA",
        "ENTREGADO"
    }

    if set(estados.keys()) != necesarios:

        raise RuntimeError(
            "Faltan estados requeridos "
            "para generar el historial."
        )

    # =====================================================
    # PRODUCTOS
    # =====================================================

    cur.execute("""
        SELECT
            id,
            nombre,
            precio,
            tiempo_preparacion_min
        FROM productos
        WHERE activo = TRUE
          AND disponible = TRUE
        ORDER BY id;
    """)

    productos = cur.fetchall()

    if not productos:

        raise RuntimeError(
            "No existen productos disponibles."
        )

    # =====================================================
    # CLIENTES HISTÓRICOS
    # =====================================================

    password_hash = generate_password_hash(
        "Historico-No-Login-2026"
    )

    clientes_ids = []
    cur.execute("""
        SELECT codigo
        FROM pedidos
        WHERE fuente_datos = 'SINTETICO_ML';
    """)

    codigos_existentes = {
        fila[0]
        for fila in cur.fetchall()
    }

    for numero in range(1, 81):

        correo = (
            f"cliente{numero:03d}"
            f"@kimbos.local"
        )

        nombre = (
            f"Cliente {numero:03d}"
        )

        telefono = (
            "9"
            + "".join(
                str(
                    random.randint(0, 9)
                )
                for _ in range(8)
            )
        )

        cur.execute("""
            SELECT id
            FROM usuarios
            WHERE correo = %s;
        """, (correo,))

        existente = cur.fetchone()

        if existente:

            cliente_id = existente[0]

        else:

            cur.execute("""
                INSERT INTO usuarios (
                    nombre_completo,
                    correo,
                    password_hash,
                    telefono,
                    rol,
                    activo,
                    fecha_creacion
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    'CLIENTE',
                    FALSE,
                    %s
                )
                RETURNING id;
            """, (
                nombre,
                correo,
                password_hash,
                telefono,
                datetime(
                    2026,
                    9,
                    1,
                    12,
                    0,
                    tzinfo=TZ
                )
            ))

            cliente_id = (
                cur.fetchone()[0]
            )

        clientes_ids.append(
            cliente_id
        )

    # =====================================================
    # DISTRIBUIR LOS 1000 PEDIDOS ENTRE LAS FECHAS
    # =====================================================

    fechas = obtener_fechas()

    pesos = [
        peso_dia(fecha)
        for fecha in fechas
    ]

    suma_pesos = sum(pesos)

    cantidades = []

    acumulado = 0

    for indice, peso in enumerate(pesos):

        if indice == len(fechas) - 1:

            cantidad = (
                CANTIDAD_PEDIDOS
                - acumulado
            )

        else:

            cantidad = round(
                CANTIDAD_PEDIDOS
                * peso
                / suma_pesos
            )

            acumulado += cantidad

        cantidades.append(
            cantidad
        )

    fechas_pedidos = []

    for fecha, cantidad in zip(
        fechas,
        cantidades
    ):

        for _ in range(cantidad):

            fecha_hora = datetime.combine(
                fecha,
                generar_hora(),
                tzinfo=TZ
            )

            fechas_pedidos.append(
                fecha_hora
            )

    # Ajuste por redondeos
    while len(fechas_pedidos) > CANTIDAD_PEDIDOS:
        fechas_pedidos.pop()

    while len(fechas_pedidos) < CANTIDAD_PEDIDOS:

        fecha = random.choice(
            fechas
        )

        fechas_pedidos.append(
            datetime.combine(
                fecha,
                generar_hora(),
                tzinfo=TZ
            )
        )

    fechas_pedidos.sort()

    # =====================================================
    # COLA DE PEDIDOS ACTIVOS
    # =====================================================

    entregas_pendientes = []

    generados = 0
    retrasados = 0
    a_tiempo = 0

    # =====================================================
    # GENERACIÓN
    # =====================================================

    for numero, fecha_pedido in enumerate(
        fechas_pedidos,
        start=1
    ):

        # Eliminar de la cola pedidos ya entregados
        while (
            entregas_pendientes
            and entregas_pendientes[0]
            <= fecha_pedido
        ):
            heapq.heappop(
                entregas_pendientes
            )

        pedidos_activos = len(
            entregas_pendientes
        )

        # ---------------------------------------------
        # CLIENTE
        # ---------------------------------------------

        cliente_id = random.choice(
            clientes_ids
        )

        cur.execute("""
            SELECT
                nombre_completo,
                telefono
            FROM usuarios
            WHERE id = %s;
        """, (cliente_id,))

        cliente_nombre, cliente_telefono = (
            cur.fetchone()
        )

        # ---------------------------------------------
        # ITEMS
        # ---------------------------------------------

        numero_productos_distintos = (
            random.choices(
                [1, 2, 3, 4],
                weights=[
                    40,
                    35,
                    18,
                    7
                ],
                k=1
            )[0]
        )

        numero_productos_distintos = min(
            numero_productos_distintos,
            len(productos)
        )

        seleccionados = random.sample(
            productos,
            numero_productos_distintos
        )

        items = []

        subtotal = Decimal("0.00")
        cantidad_items = 0
        tiempos_preparacion = []

        for producto in seleccionados:

            (
                producto_id,
                nombre_producto,
                precio,
                tiempo_preparacion
            ) = producto

            cantidad = random.choices(
                [1, 2, 3],
                weights=[
                    75,
                    20,
                    5
                ],
                k=1
            )[0]

            subtotal_item = (
                precio
                * cantidad
            )

            subtotal += subtotal_item

            cantidad_items += cantidad

            tiempos_preparacion.append(
                tiempo_preparacion
            )

            items.append({
                "producto_id": producto_id,
                "nombre": nombre_producto,
                "precio": precio,
                "cantidad": cantidad,
                "subtotal": subtotal_item
            })

        tiempo_preparacion = max(
            tiempos_preparacion
        )

        # Pedidos grandes requieren algo más de tiempo
        if cantidad_items >= 5:

            tiempo_preparacion += random.randint(
                2,
                5
            )

        # ---------------------------------------------
        # DISTANCIA Y RUTA
        # ---------------------------------------------

        distancia_km = round(
            limitar(
                random.gammavariate(
                    2.2,
                    1.45
                ),
                0.6,
                8.5
            ),
            2
        )

        duracion_ruta = (
            calcular_duracion_ruta(
                distancia_km
            )
        )

        tiempo_estimado_total = (
            tiempo_preparacion
            + duracion_ruta
        )

        # ---------------------------------------------
        # FACTORES PARA RETRASO
        # ---------------------------------------------

        hora = fecha_pedido.hour

        hora_pico = (
            12 <= hora <= 14
            or 19 <= hora <= 21
        )

        fin_semana = (
            fecha_pedido.weekday()
            in (4, 5, 6)
        )

        score = -2.15

        score += (
            0.13
            * max(
                pedidos_activos - 4,
                0
            )
        )

        score += (
            0.18
            * max(
                distancia_km - 4.0,
                0
            )
        )

        score += (
            0.10
            * max(
                cantidad_items - 2,
                0
            )
        )

        if tiempo_preparacion >= 15:
            score += 0.35

        if hora_pico:
            score += 0.55

        if fin_semana:
            score += 0.30

        # Ruido para evitar reglas perfectas
        score += random.normalvariate(
            0,
            0.65
        )

        probabilidad_retraso = sigmoide(
            score
        )

        tiene_retraso = (
            random.random()
            < probabilidad_retraso
        )

        if tiene_retraso:

            minutos_extra = random.randint(
                6,
                24
            )

            duracion_real = (
                tiempo_estimado_total
                + minutos_extra
            )

        else:

            variacion = random.randint(
                -5,
                5
            )

            duracion_real = max(
                8,
                tiempo_estimado_total
                + variacion
            )

        retraso = (
            duracion_real
            > tiempo_estimado_total + 5
        )

        if retraso:
            retrasados += 1
        else:
            a_tiempo += 1

        # ---------------------------------------------
        # COORDENADAS
        # ---------------------------------------------

        (
            lat_destino,
            lon_destino
        ) = generar_coordenadas(
            lat_origen,
            lon_origen,
            distancia_km
        )

        zona_destino = zona_por_distancia(
            distancia_km
        )

        direccion_destino = (
            f"Ubicación de entrega "
            f"({lat_destino:.6f}, "
            f"{lon_destino:.6f})"
        )

        # ---------------------------------------------
        # FECHAS DEL FLUJO
        # ---------------------------------------------

        fecha_confirmacion = (
            fecha_pedido
            + timedelta(
                minutes=random.randint(
                    1,
                    3
                )
            )
        )

        fecha_preparando = (
            fecha_confirmacion
            + timedelta(
                minutes=random.randint(
                    0,
                    2
                )
            )
        )

        inicio_ruta_min = max(
            4,
            tiempo_preparacion
            + random.randint(
                -2,
                3
            )
        )

        fecha_en_ruta = (
            fecha_pedido
            + timedelta(
                minutes=inicio_ruta_min
            )
        )

        fecha_entrega = (
            fecha_pedido
            + timedelta(
                minutes=duracion_real
            )
        )

        if fecha_en_ruta >= fecha_entrega:

            fecha_en_ruta = (
                fecha_entrega
                - timedelta(
                    minutes=max(
                        2,
                        duracion_ruta
                    )
                )
            )

        fecha_asignacion = (
            fecha_preparando
        )

        fecha_recojo = (
            fecha_en_ruta
        )

        heapq.heappush(
            entregas_pendientes,
            fecha_entrega
        )

        # ---------------------------------------------
        # PRECIOS
        # ---------------------------------------------

        costo_delivery = (
            Decimal("3.00")
            + Decimal("1.20")
            * Decimal(
                str(distancia_km)
            )
        ).quantize(
            Decimal("0.01")
        )

        total = (
            subtotal
            + costo_delivery
        ).quantize(
            Decimal("0.01")
        )

        metodo_pago = random.choices(
            [
                "EFECTIVO",
                "YAPE"
            ],
            weights=[
                45,
                55
            ],
            k=1
        )[0]

        # ---------------------------------------------
        # PEDIDO
        # ---------------------------------------------

        codigo = (
            f"PED-HIST-"
            f"{numero:06d}"
        )
        if codigo in codigos_existentes:
            continue

        cur.execute("""
            INSERT INTO pedidos (
                codigo,
                cliente_id,
                estado_id,

                remitente_nombre,

                destinatario_nombre,
                destinatario_telefono,

                descripcion_paquete,

                direccion_origen,
                latitud_origen,
                longitud_origen,
                zona_origen,

                direccion_destino,
                latitud_destino,
                longitud_destino,
                zona_destino,

                distancia_km,
                duracion_estimada_min,
                duracion_real_min,
                retraso,

                fecha_pedido,
                fecha_confirmacion,
                fecha_asignacion,
                fecha_recojo,
                fecha_entrega,

                sede_id,

                subtotal,
                costo_delivery,
                total,

                cantidad_items,

                tiempo_preparacion_estimado_min,
                tiempo_estimado_total_min,

                metodo_pago,

                fuente_datos,
                pedidos_activos_momento
            )
            VALUES (
                %s, %s, %s,
                %s,
                %s, %s,
                %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s,
                %s, %s, %s,
                %s,
                %s, %s,
                %s,
                'SINTETICO_ML',
                %s
            )
            RETURNING id;
        """, (
            codigo,
            cliente_id,
            estados["ENTREGADO"],

            negocio_nombre,

            cliente_nombre,
            cliente_telefono,

            "Pedido delivery Kimbos",

            sede_direccion,
            sede_latitud,
            sede_longitud,
            sede_nombre,

            direccion_destino,
            lat_destino,
            lon_destino,
            zona_destino,

            distancia_km,
            duracion_ruta,
            duracion_real,
            retraso,

            fecha_pedido,
            fecha_confirmacion,
            fecha_asignacion,
            fecha_recojo,
            fecha_entrega,

            sede_id,

            subtotal,
            costo_delivery,
            total,

            cantidad_items,

            tiempo_preparacion,
            tiempo_estimado_total,

            metodo_pago,

            pedidos_activos
        ))

        pedido_id = cur.fetchone()[0]

        # ---------------------------------------------
        # DETALLE DEL PEDIDO
        # ---------------------------------------------

        for item in items:

            cur.execute("""
                INSERT INTO detalle_pedido (
                    pedido_id,
                    producto_id,
                    nombre_producto,
                    precio_unitario,
                    cantidad,
                    subtotal
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                );
            """, (
                pedido_id,
                item["producto_id"],
                item["nombre"],
                item["precio"],
                item["cantidad"],
                item["subtotal"]
            ))

        # ---------------------------------------------
        # HISTORIAL
        # ---------------------------------------------

        historial = [
            (
                estados["REGISTRADO"],
                fecha_pedido
            ),
            (
                estados["PREPARANDO"],
                fecha_preparando
            ),
            (
                estados["EN_RUTA"],
                fecha_en_ruta
            ),
            (
                estados["ENTREGADO"],
                fecha_entrega
            )
        ]

        for estado_id, fecha_estado in historial:

            cur.execute("""
                INSERT INTO historial_pedido (
                    pedido_id,
                    estado_id,
                    fecha
                )
                VALUES (
                    %s,
                    %s,
                    %s
                );
            """, (
                pedido_id,
                estado_id,
                fecha_estado
            ))

        generados += 1

        if generados % TAMANO_LOTE == 0:

            conn.commit()

            print(
                f"{generados} pedidos nuevos "
                f"guardados correctamente..."
            )

    # =====================================================
    # CONFIRMAR TRANSACCIÓN
    # =====================================================

    conn.commit()

    print("\n========================================")
    print("GENERACIÓN COMPLETADA")
    print("========================================")
    print(
        f"Pedidos generados: {generados}"
    )
    print(
        f"A tiempo: {a_tiempo}"
    )
    print(
        f"Retrasados: {retrasados}"
    )
    print(
        f"Periodo: "
        f"{FECHA_INICIO.strftime('%d/%m/%Y')} "
        f"- "
        f"{FECHA_FIN.strftime('%d/%m/%Y')}"
    )
    print(
        "Fuente: SINTETICO_ML"
    )
    print("========================================")

except Exception as error:

    print("\nERROR DURANTE LA GENERACION:")
    print(error)

    try:
        conn.rollback()
    except Exception:
        print(
            "La conexion con PostgreSQL ya estaba cerrada."
        )

    raise

finally:

    conn.close()