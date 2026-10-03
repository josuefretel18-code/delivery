-- Variables del modelo v2.0 (entrenado con DoorDash):
-- carga = pedidos activos / repartidores disponibles.

ALTER TABLE predicciones_ml
ADD COLUMN IF NOT EXISTS repartidores_disponibles INTEGER;

ALTER TABLE predicciones_ml
ADD COLUMN IF NOT EXISTS carga_repartidor NUMERIC(8, 4);

-- En schema.sql existia como INTEGER (sin uso, sin datos);
-- la carga es decimal (ej. 0.5 pedidos por repartidor).
ALTER TABLE predicciones_ml
ALTER COLUMN carga_repartidor TYPE NUMERIC(8, 4);
