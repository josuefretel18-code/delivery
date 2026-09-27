from db import get_connection


def mostrar_tablas():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename;
            """)

            tablas = cur.fetchall()

            print("\nTABLAS CREADAS:")
            for tabla in tablas:
                print("-", tabla[0])


def mostrar_estados():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT codigo, nombre
                FROM estados_pedido
                ORDER BY orden_flujo;
            """)

            estados = cur.fetchall()

            print("\nESTADOS DEL PEDIDO:")
            for codigo, nombre in estados:
                print(f"- {codigo}: {nombre}")


if __name__ == "__main__":
    mostrar_tablas()
    mostrar_estados()