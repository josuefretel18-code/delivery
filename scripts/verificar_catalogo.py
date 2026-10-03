from db import get_connection


with get_connection() as conn:
    with conn.cursor() as cur:

        cur.execute("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename IN (
                'categorias_producto',
                'productos',
                'detalle_pedido'
            )
            ORDER BY tablename;
        """)

        print("\nTABLAS DEL CATÁLOGO:")

        for tabla in cur.fetchall():
            print("-", tabla[0])

        cur.execute("""
            SELECT
                codigo,
                nombre,
                orden_flujo
            FROM estados_pedido
            ORDER BY orden_flujo;
        """)

        print("\nFLUJO DE PEDIDOS:")

        for codigo, nombre, orden in cur.fetchall():
            print(
                f"{orden}. {codigo} - {nombre}"
            )