from db import get_connection


conn = get_connection()
cur = conn.cursor()


cur.execute("""
    UPDATE pedidos

    SET
        duracion_real_min =
            CEIL(
                EXTRACT(
                    EPOCH FROM (
                        fecha_entrega
                        - fecha_pedido
                    )
                ) / 60.0
            )::integer,

        retraso = (
            EXTRACT(
                EPOCH FROM (
                    fecha_entrega
                    - fecha_pedido
                )
            ) / 60.0
            >
            (
                COALESCE(
                    tiempo_estimado_total_min,
                    duracion_estimada_min,
                    0
                )
                + 5
            )
        )

    WHERE fuente_datos = 'REAL'
      AND fecha_entrega IS NOT NULL
      AND (
          duracion_real_min IS NULL
          OR retraso IS NULL
      );
""")


actualizados = cur.rowcount

conn.commit()


print(
    "Pedidos reales actualizados:",
    actualizados
)


cur.execute("""
    SELECT
        codigo,
        tiempo_estimado_total_min,
        duracion_real_min,
        retraso

    FROM pedidos

    WHERE fuente_datos = 'REAL'
      AND fecha_entrega IS NOT NULL

    ORDER BY fecha_entrega DESC;
""")


print("\n=== RESULTADOS REALES ===")

for fila in cur.fetchall():

    print(
        fila[0],
        "| Estimado:",
        fila[1],
        "min",
        "| Real:",
        fila[2],
        "min",
        "| Resultado:",
        "RETRASADO"
        if fila[3]
        else "A_TIEMPO"
    )


cur.close()
conn.close()