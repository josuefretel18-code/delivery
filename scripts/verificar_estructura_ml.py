from db import get_connection


conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT
        table_name,
        column_name,
        data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN (
          'pedidos',
          'predicciones_ml'
      )
    ORDER BY
        table_name,
        ordinal_position;
""")

filas = cur.fetchall()

for tabla, columna, tipo in filas:
    print(
        f"{tabla:18} | "
        f"{columna:40} | "
        f"{tipo}"
    )

cur.close()
conn.close()