from getpass import getpass

from werkzeug.security import generate_password_hash

from db import get_connection


nombre = input(
    "Nombre del administrador: "
).strip()

correo = input(
    "Correo: "
).strip().lower()

password = getpass(
    "Contraseña: "
)

if len(password) < 8:
    raise ValueError(
        "La contraseña debe tener al menos 8 caracteres"
    )

password_hash = generate_password_hash(password)


with get_connection() as conn:
    with conn.cursor() as cur:

        cur.execute("""
            INSERT INTO usuarios (
                nombre_completo,
                correo,
                password_hash,
                rol
            )
            VALUES (%s, %s, %s, 'ADMIN')
            RETURNING id;
        """, (
            nombre,
            correo,
            password_hash
        ))

        usuario_id = cur.fetchone()[0]

    conn.commit()


print(
    f"Administrador creado correctamente. ID: {usuario_id}"
)