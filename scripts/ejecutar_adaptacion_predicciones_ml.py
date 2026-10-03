from pathlib import Path

from db import get_connection


sql = Path(
    "sql/adaptar_predicciones_ml.sql"
).read_text(
    encoding="utf-8"
)


with get_connection() as conn:

    with conn.cursor() as cur:
        cur.execute(sql)

    conn.commit()


print(
    "Tabla predicciones_ml adaptada correctamente."
)