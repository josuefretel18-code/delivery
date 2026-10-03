from db import get_connection


conn = get_connection()
cur = conn.cursor()

print("\n=== ESTRUCTURA DE USUARIOS ===")

cur.execute("""
    SELECT
        column_name,
        data_type,
        is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'usuarios'
    ORDER BY ordinal_position;
""")

for fila in cur.fetchall():
    print(fila)

print("\n=== USUARIOS EXISTENTES ===")

cur.execute("""
    SELECT *
    FROM usuarios
    ORDER BY id;
""")

columnas = [
    desc.name
    for desc in cur.description
]

for fila in cur.fetchall():

    datos = dict(zip(columnas, fila))

    # No mostramos información sensible.
    for campo in list(datos.keys()):
        if "password" in campo.lower() or "clave" in campo.lower():
            datos[campo] = "***OCULTO***"

    print(datos)

cur.close()
conn.close()