-- =========================================================
-- ESTADOS INICIALES DEL SISTEMA
-- =========================================================

INSERT INTO estados_pedido
(
    codigo,
    nombre,
    orden_flujo,
    es_final
)
VALUES

(
    'REGISTRADO',
    'Registrado',
    1,
    FALSE
),

(
    'CONFIRMADO',
    'Confirmado',
    2,
    FALSE
),

(
    'ASIGNADO',
    'Asignado a repartidor',
    3,
    FALSE
),

(
    'RECOGIDO',
    'Pedido recogido',
    4,
    FALSE
),

(
    'EN_RUTA',
    'En ruta',
    5,
    FALSE
),

(
    'ENTREGADO',
    'Entregado',
    6,
    TRUE
),

(
    'CANCELADO',
    'Cancelado',
    7,
    TRUE
),

(
    'INCIDENCIA',
    'Con incidencia',
    8,
    FALSE
)

ON CONFLICT (codigo)
DO NOTHING;