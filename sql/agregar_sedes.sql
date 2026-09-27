-- =========================================================
-- SEDES DEL NEGOCIO
-- =========================================================

CREATE TABLE IF NOT EXISTS sedes (
    id BIGSERIAL PRIMARY KEY,

    nombre VARCHAR(120) NOT NULL,

    direccion VARCHAR(250) NOT NULL,

    latitud DECIMAL(10,7) NOT NULL,

    longitud DECIMAL(10,7) NOT NULL,

    telefono VARCHAR(20),

    activa BOOLEAN NOT NULL DEFAULT TRUE,

    fecha_creacion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- RELACIONAR PEDIDOS CON UNA SEDE
-- =========================================================

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS sede_id BIGINT;


ALTER TABLE pedidos
DROP CONSTRAINT IF EXISTS fk_pedido_sede;


ALTER TABLE pedidos
ADD CONSTRAINT fk_pedido_sede
FOREIGN KEY (sede_id)
REFERENCES sedes(id)
ON DELETE RESTRICT;


CREATE INDEX IF NOT EXISTS idx_pedidos_sede
ON pedidos(sede_id);