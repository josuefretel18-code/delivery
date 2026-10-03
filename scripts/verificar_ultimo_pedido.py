from db import get_connection


with get_connection() as conn:
    with conn.cursor() as cur:

        # ==========================================
        # ÚLTIMO PEDIDO
        # ==========================================

        cur.execute("""
            SELECT
                p.id,
                p.codigo,
                e.codigo,
                e.nombre,

                p.destinatario_nombre,
                p.destinatario_telefono,
                p.direccion_destino,

                p.distancia_km,
                p.duracion_estimada_min,

                p.cantidad_items,
                p.tiempo_preparacion_estimado_min,
                p.tiempo_estimado_total_min,

                p.subtotal,
                p.costo_delivery,
                p.total,

                p.metodo_pago,
                p.fecha_pedido

            FROM pedidos p

            JOIN estados_pedido e
                ON e.id = p.estado_id

            ORDER BY p.id DESC

            LIMIT 1;
        """)

        pedido = cur.fetchone()


        if not pedido:

            print("\nNo existen pedidos registrados.")
            raise SystemExit


        pedido_id = pedido[0]


        print("\n========================================")
        print("ÚLTIMO PEDIDO REGISTRADO")
        print("========================================")

        print(f"ID: {pedido[0]}")
        print(f"Código: {pedido[1]}")
        print(f"Estado: {pedido[2]} - {pedido[3]}")

        print("\nDESTINO")
        print(f"Destinatario: {pedido[4]}")
        print(f"Teléfono: {pedido[5]}")
        print(f"Dirección: {pedido[6]}")

        print("\nRUTA")
        print(f"Distancia: {pedido[7]} km")
        print(f"Duración de ruta: {pedido[8]} min")

        print("\nTIEMPOS")
        print(f"Cantidad de productos: {pedido[9]}")
        print(f"Preparación: {pedido[10]} min")
        print(f"Tiempo estimado total: {pedido[11]} min")

        print("\nPAGO")
        print(f"Subtotal: S/ {pedido[12]}")
        print(f"Delivery: S/ {pedido[13]}")
        print(f"Total: S/ {pedido[14]}")
        print(f"Método: {pedido[15]}")

        print(f"\nFecha: {pedido[16]}")


        # ==========================================
        # PRODUCTOS DEL PEDIDO
        # ==========================================

        cur.execute("""
            SELECT
                nombre_producto,
                precio_unitario,
                cantidad,
                subtotal

            FROM detalle_pedido

            WHERE pedido_id = %s

            ORDER BY id;
        """, (
            pedido_id,
        ))

        productos = cur.fetchall()


        print("\n========================================")
        print("PRODUCTOS")
        print("========================================")

        if not productos:

            print("No existen productos asociados.")

        else:

            for producto in productos:

                print(
                    f"{producto[2]} x "
                    f"{producto[0]} | "
                    f"S/ {producto[1]} c/u | "
                    f"Subtotal: S/ {producto[3]}"
                )


        # ==========================================
        # HISTORIAL
        # ==========================================

        cur.execute("""
            SELECT
                e.codigo,
                e.nombre,
                h.observacion,
                h.fecha

            FROM historial_pedido h

            JOIN estados_pedido e
                ON e.id = h.estado_id

            WHERE h.pedido_id = %s

            ORDER BY h.fecha;
        """, (
            pedido_id,
        ))

        historial = cur.fetchall()


        print("\n========================================")
        print("HISTORIAL")
        print("========================================")

        for estado in historial:

            print(
                f"{estado[3]} | "
                f"{estado[0]} | "
                f"{estado[1]} | "
                f"{estado[2]}"
            )


        print("\n========================================")
        print("VERIFICACIÓN FINALIZADA")
        print("========================================")