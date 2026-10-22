-- =========================================================
-- Reporte diario automatico (sistema multiagente)
--
-- Todos los dias Cloud Scheduler llama al backend y tres agentes
-- (Analista de datos -> Estratega -> Redactor) generan el reporte
-- del dia con los pedidos, ventas, retrasos y aciertos del modelo ML.
-- Una fila por dia (la ultima ejecucion).
--
-- El backend tambien la crea si no existe (backend/agentes_automaticos.py).
-- =========================================================

CREATE TABLE IF NOT EXISTS reportes_diarios (
    id BIGSERIAL PRIMARY KEY,

    fecha_reporte DATE NOT NULL UNIQUE,

    fecha_generacion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    -- PROGRAMADO: Cloud Scheduler. MANUAL: boton del panel admin.
    origen VARCHAR(12) NOT NULL DEFAULT 'PROGRAMADO',

    -- PROCESANDO / LISTO / SIN_DATOS / ERROR
    estado VARCHAR(12) NOT NULL DEFAULT 'PROCESANDO',

    -- Datos del dia calculados por el sistema (no por el LLM)
    metricas TEXT,

    -- Agente 1: Analista de datos
    hallazgos TEXT,

    -- Agente 2: Estratega
    recomendaciones TEXT,
    repartidores_sugeridos INTEGER,

    -- Agente 3: Redactor
    titulo VARCHAR(200),
    resumen TEXT,

    costo_usd NUMERIC(10,6),
    duracion_ms INTEGER,
    error VARCHAR(300)
);

-- Reporte mas especifico (version 2): calificacion del dia, conclusion
-- y franja horaria en la que conviene reforzar repartidores.
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS calificacion VARCHAR(10);
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS conclusion TEXT;
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS franja_refuerzo VARCHAR(60);

-- Flujo en pasos: ultimo paso terminado (0 datos, 1 analista,
-- 2 estratega, 3 redactor).
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS etapa SMALLINT;

-- Orquestador y Evaluador (5 agentes): plan, flujo y decision del
-- Orquestador, calificaciones del Evaluador y nota final (1 a 10).
-- etapa pasa a 0 datos .. 5 evaluador.
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS orquestacion TEXT;
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS evaluacion TEXT;
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS nota_final NUMERIC(4,1);

-- Informe del Redactor: "Lo que funciono" y "A vigilar" (JSON).
ALTER TABLE reportes_diarios ADD COLUMN IF NOT EXISTS puntos TEXT;
