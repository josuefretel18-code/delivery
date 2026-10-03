ALTER TABLE predicciones_ml
ADD COLUMN IF NOT EXISTS tiempo_preparacion_estimado_min INTEGER;

ALTER TABLE predicciones_ml
ADD COLUMN IF NOT EXISTS cantidad_items INTEGER;

ALTER TABLE predicciones_ml
ADD COLUMN IF NOT EXISTS hora_pico INTEGER;

ALTER TABLE predicciones_ml
ADD COLUMN IF NOT EXISTS fin_semana INTEGER;