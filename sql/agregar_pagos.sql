-- =========================================================
-- Estado del pago
--
-- EFECTIVO: se cobra al entregar (pasa a PAGADO al entregar).
-- YAPE / PLIN: el cliente indica el numero de operacion y el
-- admin confirma el pago al verlo en su aplicacion.
--
-- El backend aplica este cambio al arrancar si falta.
-- =========================================================

ALTER TABLE pedidos
    ADD COLUMN IF NOT EXISTS pago_estado VARCHAR(12) NOT NULL DEFAULT 'PENDIENTE';

ALTER TABLE pedidos
    ADD COLUMN IF NOT EXISTS pago_operacion VARCHAR(30);

ALTER TABLE pedidos
    ADD COLUMN IF NOT EXISTS pago_confirmado_por BIGINT;

ALTER TABLE pedidos
    ADD COLUMN IF NOT EXISTS fecha_pago TIMESTAMPTZ;

-- Pedidos ya entregados antes de este cambio: se consideran pagados
UPDATE pedidos p
SET pago_estado = 'PAGADO'
FROM estados_pedido e
WHERE e.id = p.estado_id
  AND e.codigo = 'ENTREGADO'
  AND p.pago_estado = 'PENDIENTE';
