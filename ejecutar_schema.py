from pathlib import Path

from db import get_connection


RUTA_SCHEMA = Path("sql/schema.sql")
RUTA_DATOS = Path("sql/datos_iniciales.sql")


def ejecutar_archivo_sql(ruta):
    contenido = ruta.read_text(encoding="utf-8")

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(contenido)

        conn.commit()


if __name__ == "__main__":

    print("Creando tablas...")
    ejecutar_archivo_sql(RUTA_SCHEMA)

    print("Insertando datos iniciales...")
    ejecutar_archivo_sql(RUTA_DATOS)

    print("Base de datos preparada correctamente.")