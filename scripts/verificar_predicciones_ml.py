from db import get_connection


conn = get_connection()
cur = conn.cursor()

print("\n=== PREDICCIONES_ML ===")

cur.execute("""
    SELECT
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'predicciones_ml'
    ORDER BY ordinal_position;
""")

for columna, tipo, nullable, default in cur.fetchall():

    print(
        f"{columna:32} | "
        f"{tipo:24} | "
        f"NULL={nullable:3} | "
        f"default={default}"
    )

cur.close()
conn.close()