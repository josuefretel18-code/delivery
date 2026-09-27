-- =========================================================
-- DELIVERY KIMBOS
-- CATÁLOGO DE PRODUCTOS Y DETALLE DE PEDIDOS
-- =========================================================


-- =========================================================
-- 1. CATEGORÍAS DE PRODUCTOS
-- =========================================================

CREATE TABLE IF NOT EXISTS categorias_producto (
    id BIGSERIAL PRIMARY KEY,

    nombre VARCHAR(100) NOT NULL UNIQUE,

    descripcion VARCHAR(250),

    orden INTEGER NOT NULL DEFAULT 0,

    activa BOOLEAN NOT NULL DEFAULT TRUE,

    fecha_creacion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 2. PRODUCTOS
-- =========================================================

CREATE TABLE IF NOT EXISTS productos (
    id BIGSERIAL PRIMARY KEY,

    categoria_id BIGINT NOT NULL,

    nombre VARCHAR(120) NOT NULL,

    descripcion VARCHAR(300),

    precio DECIMAL(10,2) NOT NULL
        CHECK (precio >= 0),

    tiempo_preparacion_min INTEGER NOT NULL DEFAULT 10
        CHECK (tiempo_preparacion_min >= 0),

    imagen_url VARCHAR(500),

    disponible BOOLEAN NOT NULL DEFAULT TRUE,

    activo BOOLEAN NOT NULL DEFAULT TRUE,

    fecha_creacion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    fecha_actualizacion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_producto_categoria
        FOREIGN KEY (categoria_id)
        REFERENCES categorias_producto(id)
        ON DELETE RESTRICT
);


-- =========================================================
-- 3. DETALLE DEL PEDIDO
-- =========================================================

CREATE TABLE IF NOT EXISTS detalle_pedido (
    id BIGSERIAL PRIMARY KEY,

    pedido_id BIGINT NOT NULL,

    producto_id BIGINT,

    -- Snapshot del producto en el momento de comprar
    nombre_producto VARCHAR(120) NOT NULL,

    precio_unitario DECIMAL(10,2) NOT NULL,

    cantidad INTEGER NOT NULL
        CHECK (cantidad > 0),

    subtotal DECIMAL(10,2) NOT NULL,

    observacion VARCHAR(250),

    CONSTRAINT fk_detalle_pedido
        FOREIGN KEY (pedido_id)
        REFERENCES pedidos(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_detalle_producto
        FOREIGN KEY (producto_id)
        REFERENCES productos(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 4. NUEVOS DATOS DEL PEDIDO
-- =========================================================

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS subtotal DECIMAL(10,2);

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS costo_delivery DECIMAL(10,2);

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS total DECIMAL(10,2);

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS cantidad_items INTEGER;

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS tiempo_preparacion_estimado_min INTEGER;

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS tiempo_estimado_total_min INTEGER;

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS metodo_pago VARCHAR(30);

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS indicaciones_entrega VARCHAR(300);


-- =========================================================
-- 5. ESTADOS ADICIONALES PARA RESTAURANTE
-- =========================================================

INSERT INTO estados_pedido (
    codigo,
    nombre,
    orden_flujo,
    es_final
)
VALUES
(
    'PREPARANDO',
    'Preparando pedido',
    3,
    FALSE
),
(
    'LISTO_RECOJO',
    'Listo para recojo',
    4,
    FALSE
)
ON CONFLICT (codigo)
DO NOTHING;


-- Reordenamos el flujo
UPDATE estados_pedido
SET orden_flujo = 1
WHERE codigo = 'REGISTRADO';

UPDATE estados_pedido
SET orden_flujo = 2
WHERE codigo = 'CONFIRMADO';

UPDATE estados_pedido
SET orden_flujo = 3
WHERE codigo = 'PREPARANDO';

UPDATE estados_pedido
SET orden_flujo = 4
WHERE codigo = 'LISTO_RECOJO';

UPDATE estados_pedido
SET orden_flujo = 5
WHERE codigo = 'ASIGNADO';

UPDATE estados_pedido
SET orden_flujo = 6
WHERE codigo = 'RECOGIDO';

UPDATE estados_pedido
SET orden_flujo = 7
WHERE codigo = 'EN_RUTA';

UPDATE estados_pedido
SET orden_flujo = 8
WHERE codigo = 'ENTREGADO';

UPDATE estados_pedido
SET orden_flujo = 9
WHERE codigo = 'CANCELADO';

UPDATE estados_pedido
SET orden_flujo = 10
WHERE codigo = 'INCIDENCIA';


-- =========================================================
-- 6. ÍNDICES
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_productos_categoria
ON productos(categoria_id);

CREATE INDEX IF NOT EXISTS idx_productos_disponible
ON productos(disponible);

CREATE INDEX IF NOT EXISTS idx_productos_activo
ON productos(activo);

CREATE INDEX IF NOT EXISTS idx_detalle_pedido_pedido
ON detalle_pedido(pedido_id);