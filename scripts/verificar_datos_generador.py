from db import get_connection


conn = get_connection()
cur = conn.cursor()


# =========================================================
# ESTADOS
# =========================================================

print("\n=== ESTADOS DE PEDIDO ===")

cur.execute("""
    SELECT id, codigo, nombre
    FROM estados_pedido
    ORDER BY id;
""")

for fila in cur.fetchall():
    print(fila)


# =========================================================
# SEDES - ESTRUCTURA REAL
# =========================================================

print("\n=== COLUMNAS DE SEDES ===")

cur.execute("""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'sedes'
    ORDER BY ordinal_position;
""")

columnas_sedes = [
    fila[0]
    for fila in cur.fetchall()
]

print(columnas_sedes)


print("\n=== DATOS DE SEDES ===")

cur.execute("""
    SELECT *
    FROM sedes
    ORDER BY id;
""")

for fila in cur.fetchall():

    datos = dict(
        zip(
            columnas_sedes,
            fila
        )
    )

    print(datos)


# =========================================================
# PRODUCTOS
# =========================================================

print("\n=== PRODUCTOS ACTIVOS ===")

cur.execute("""
    SELECT
        p.id,
        p.nombre,
        p.precio,
        p.tiempo_preparacion_min,
        p.disponible,
        c.nombre AS categoria
    FROM productos p
    JOIN categorias_producto c
        ON c.id = p.categoria_id
    WHERE p.activo = TRUE
    ORDER BY c.nombre, p.nombre;
""")

productos = cur.fetchall()

for fila in productos:
    print(fila)

print(
    "\nTotal productos activos:",
    len(productos)
)


# =========================================================
# COLUMNAS OBLIGATORIAS
# =========================================================

for tabla in [
    "pedidos",
    "detalle_pedido",
    "historial_pedido"
]:

    print(
        f"\n=== COLUMNAS OBLIGATORIAS: "
        f"{tabla.upper()} ==="
    )

    cur.execute("""
        SELECT
            column_name,
            data_type,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND is_nullable = 'NO'
        ORDER BY ordinal_position;
    """, (tabla,))

    for columna, tipo, default in cur.fetchall():

        print(
            f"{columna:38} | "
            f"{tipo:28} | "
            f"default={default}"
        )


cur.close()
conn.close()