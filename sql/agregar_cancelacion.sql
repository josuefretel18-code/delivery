-- =========================================================
-- Cancelacion de pedidos
--
-- El cliente puede cancelar mientras el pedido esta "Recibido";
-- el admin u operador, antes de enviarlo (con un motivo).
-- La fecha va en pedidos.fecha_cancelacion (ya existe).
--
-- El backend aplica este cambio al arrancar si falta.
-- =========================================================

ALTER TABLE pedidos
    ADD COLUMN IF NOT EXISTS motivo_cancelacion VARCHAR(200);

ALTER TABLE pedidos
    ADD COLUMN IF NOT EXISTS cancelado_por VARCHAR(20);
