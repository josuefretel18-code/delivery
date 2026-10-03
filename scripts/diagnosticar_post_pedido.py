from db import get_connection


conn = get_connection()
cur = conn.cursor()

cur.execute("""
    SELECT
        pid,
        state,
        wait_event_type,
        wait_event,
        query_start,
        LEFT(query, 500)

    FROM pg_stat_activity

    WHERE datname = current_database()
      AND pid <> pg_backend_pid()
      AND state <> 'idle'

    ORDER BY query_start;
""")

filas = cur.fetchall()

print("\n========================================")
print("ACTIVIDAD POSTGRESQL")
print("========================================")

if not filas:

    print("No hay consultas activas.")

else:

    for fila in filas:

        print("\nPID:", fila[0])
        print("Estado:", fila[1])
        print("Wait type:", fila[2])
        print("Wait event:", fila[3])
        print("Inicio:", fila[4])
        print("Consulta:")
        print(fila[5])

        print("----------------------------------------")

cur.close()
conn.close()