-- =====================================================
-- ADAPTACIÓN DE PEDIDOS PARA MACHINE LEARNING
-- KIMBOS DELIVERY
-- =====================================================

ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS fuente_datos VARCHAR(20)
NOT NULL DEFAULT 'REAL';


ALTER TABLE pedidos
ADD COLUMN IF NOT EXISTS pedidos_activos_momento INTEGER
NOT NULL DEFAULT 0;


CREATE INDEX IF NOT EXISTS idx_pedidos_fuente_datos
ON pedidos(fuente_datos);


CREATE INDEX IF NOT EXISTS idx_pedidos_fecha_pedido
ON pedidos(fecha_pedido);