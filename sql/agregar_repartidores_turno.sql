-- =========================================================
-- Repartidores: turno
--
-- La tabla repartidores ya existe (schema.sql). Se agrega si el
-- repartidor esta en turno: los repartidores en turno se usan para
-- sugerir la asignacion y para calcular la carga del modelo ML
-- (carga_repartidor = pedidos activos / repartidores en turno).
--
-- El backend tambien aplica este cambio si falta (backend/repartidores.py).
-- =========================================================

ALTER TABLE repartidores
    ADD COLUMN IF NOT EXISTS en_turno BOOLEAN NOT NULL DEFAULT FALSE;
