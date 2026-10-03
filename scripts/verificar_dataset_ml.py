from db import get_connection


conn = get_connection()
cur = conn.cursor()


print("\n=== RESUMEN DATASET ML ===")

cur.execute("""
    SELECT COUNT(*)
    FROM pedidos
    WHERE fuente_datos = 'SINTETICO_ML';
""")

historicos = cur.fetchone()[0]

print("Pedidos historicos:", historicos)


cur.execute("""
    SELECT
        retraso,
        COUNT(*)
    FROM pedidos
    WHERE fuente_datos = 'SINTETICO_ML'
    GROUP BY retraso
    ORDER BY retraso;
""")

print("\n=== CLASES ===")

for retraso, cantidad in cur.fetchall():

    texto = (
        "RETRASADO"
        if retraso
        else "A TIEMPO"
    )

    print(
        f"{texto}: {cantidad}"
    )


cur.execute("""
    SELECT
        MIN(fecha_pedido),
        MAX(fecha_pedido)
    FROM pedidos
    WHERE fuente_datos = 'SINTETICO_ML';
""")

fecha_min, fecha_max = cur.fetchone()

print("\n=== PERIODO ===")
print("Primer pedido:", fecha_min)
print("Ultimo pedido:", fecha_max)


cur.execute("""
    SELECT COUNT(*)
    FROM detalle_pedido d
    JOIN pedidos p
        ON p.id = d.pedido_id
    WHERE p.fuente_datos = 'SINTETICO_ML';
""")

detalles = cur.fetchone()[0]

print("\nDetalles de pedido:", detalles)


cur.execute("""
    SELECT COUNT(*)
    FROM historial_pedido h
    JOIN pedidos p
        ON p.id = h.pedido_id
    WHERE p.fuente_datos = 'SINTETICO_ML';
""")

historiales = cur.fetchone()[0]

print(
    "Registros de historial:",
    historiales
)


cur.execute("""
    SELECT
        ROUND(AVG(distancia_km), 2),
        ROUND(AVG(duracion_estimada_min), 2),
        ROUND(AVG(duracion_real_min), 2),
        ROUND(AVG(cantidad_items), 2),
        ROUND(AVG(pedidos_activos_momento), 2)
    FROM pedidos
    WHERE fuente_datos = 'SINTETICO_ML';
""")

promedios = cur.fetchone()

print("\n=== PROMEDIOS ===")

print(
    "Distancia promedio:",
    promedios[0],
    "km"
)

print(
    "Ruta estimada promedio:",
    promedios[1],
    "min"
)

print(
    "Duracion real promedio:",
    promedios[2],
    "min"
)

print(
    "Items promedio:",
    promedios[3]
)

print(
    "Pedidos activos promedio:",
    promedios[4]
)


cur.close()
conn.close()