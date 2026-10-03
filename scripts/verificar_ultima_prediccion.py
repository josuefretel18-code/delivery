from db import get_connection


conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT
        p.id,
        p.codigo,
        p.fuente_datos,
        p.pedidos_activos_momento,

        pm.modelo_version,
        pm.clase_predicha,
        pm.probabilidad_retraso,

        pm.distancia_km,
        pm.duracion_estimada_min,
        pm.tiempo_preparacion_estimado_min,
        pm.cantidad_items,

        pm.hora_pedido,
        pm.dia_semana,
        pm.hora_pico,
        pm.fin_semana,
        pm.pedidos_activos,

        pm.fecha_prediccion

    FROM pedidos p

    JOIN predicciones_ml pm
        ON pm.pedido_id = p.id

    WHERE p.fuente_datos = 'REAL'

    ORDER BY pm.id DESC

    LIMIT 1;
""")

fila = cur.fetchone()

if fila is None:

    print("\nNo se encontro ninguna prediccion ML para pedidos REAL.")

else:

    print("\n========================================")
    print("ULTIMA PREDICCION ML")
    print("========================================")

    print("Pedido ID:", fila[0])
    print("Codigo:", fila[1])
    print("Fuente:", fila[2])
    print("Pedidos activos momento:", fila[3])

    print("\n=== MODELO ===")

    print("Version:", fila[4])
    print("Prediccion:", fila[5])

    if fila[6] is not None:
        print(
            "Probabilidad retraso:",
            f"{float(fila[6]) * 100:.2f}%"
        )

    print("\n=== VARIABLES ===")

    print("Distancia:", fila[7], "km")
    print("Ruta estimada:", fila[8], "min")
    print("Preparacion:", fila[9], "min")
    print("Items:", fila[10])
    print("Hora:", fila[11])
    print("Dia semana:", fila[12])
    print("Hora pico:", fila[13])
    print("Fin semana:", fila[14])
    print("Pedidos activos:", fila[15])

    print("\nFecha prediccion:", fila[16])

    print("========================================")

cur.close()
conn.close()