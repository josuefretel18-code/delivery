-- =========================================================
-- Orquestador y Evaluador del sistema multiagente de alertas
--
--   Orquestador -> Analista -> Operaciones -> Comunicador
--               -> Evaluador -> Orquestador (decide)
--
-- prioridad:        la asigna el Orquestador al planificar.
-- orquestacion:     JSON con el plan, la decision final y el flujo
--                   (cada paso con su agente y duracion).
-- evaluacion:       JSON con las calificaciones del Evaluador.
-- nota_final:       promedio de las notas de los 3 agentes (1 a 10).
-- publicar_cliente: el Orquestador decide si el aviso llega al cliente.
--
-- Se aplica al arrancar la app (backend/agentes_automaticos.py).
-- =========================================================

ALTER TABLE alertas_pedido ADD COLUMN IF NOT EXISTS prioridad VARCHAR(10);
ALTER TABLE alertas_pedido ADD COLUMN IF NOT EXISTS orquestacion TEXT;
ALTER TABLE alertas_pedido ADD COLUMN IF NOT EXISTS evaluacion TEXT;
ALTER TABLE alertas_pedido ADD COLUMN IF NOT EXISTS nota_final NUMERIC(4,1);
ALTER TABLE alertas_pedido ADD COLUMN IF NOT EXISTS publicar_cliente BOOLEAN NOT NULL DEFAULT TRUE;
