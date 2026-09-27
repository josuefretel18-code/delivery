from decimal import Decimal, InvalidOperation

from db import get_connection


print("\n=== REGISTRO DE TIENDA Y SEDE ===\n")

negocio = input(
    "Nombre de la tienda/restaurante: "
).strip()

sede = input(
    "Nombre de la sede: "
).strip()

direccion = input(
    "Dirección de la sede: "
).strip()

latitud_texto = input(
    "Latitud: "
).strip()

longitud_texto = input(
    "Longitud: "
).strip()

telefono = input(
    "Teléfono (opcional): "
).strip()


if not negocio:
    raise ValueError(
        "El nombre de la tienda es obligatorio."
    )

if not sede:
    raise ValueError(
        "El nombre de la sede es obligatorio."
    )

if not direccion:
    raise ValueError(
        "La dirección es obligatoria."
    )


try:
    latitud = Decimal(latitud_texto)
    longitud = Decimal(longitud_texto)

except InvalidOperation:
    raise ValueError(
        "La latitud o longitud no tiene un formato válido."
    )


if not (-90 <= latitud <= 90):
    raise ValueError(
        "La latitud debe estar entre -90 y 90."
    )

if not (-180 <= longitud <= 180):
    raise ValueError(
        "La longitud debe estar entre -180 y 180."
    )


with get_connection() as conn:
    with conn.cursor() as cur:

        cur.execute("""
            UPDATE sedes
            SET activa = FALSE
            WHERE activa = TRUE;
        """)

        cur.execute("""
            INSERT INTO sedes (
                negocio_nombre,
                nombre,
                direccion,
                latitud,
                longitud,
                telefono,
                activa
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                TRUE
            )
            RETURNING id;
        """, (
            negocio,
            sede,
            direccion,
            latitud,
            longitud,
            telefono or None
        ))

        sede_id = cur.fetchone()[0]

    conn.commit()


print("\nSede registrada correctamente.")
print(f"ID: {sede_id}")
print(f"Negocio: {negocio}")
print(f"Sede: {sede}")
print(f"Dirección: {direccion}")