import os

import psycopg
from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no está configurada en el archivo .env"
        )

    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=10
    )


def probar_conexion():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    NOW();
                """
            )

            resultado = cursor.fetchone()

            return {
                "database": resultado[0],
                "usuario": resultado[1],
                "fecha_servidor": resultado[2].isoformat()
            }