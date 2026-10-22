-- =========================================================
-- Consultas a los agentes (sistema multiagente a pedido)
--
-- El administrador hace una pregunta ("¿como nos fue esta semana?") y
-- trabajan 5 agentes: Orquestador (entiende la pregunta, elige el
-- periodo y reparte encargos) -> Datos (SQL) -> Analista -> Estratega
-- -> Redactor (responde la pregunta) -> Evaluador.
-- Misma forma que reportes_diarios, para mostrarlas igual en el panel.
--
-- El backend la crea si no existe (backend/agente_consultas.py).
-- =========================================================

CREATE TABLE IF NOT EXISTS consultas_agentes (
    id BIGSERIAL PRIMARY KEY,

    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_generacion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    pregunta VARCHAR(300) NOT NULL,

    -- PROCESANDO / LISTO / SIN_DATOS / FUERA_DE_ALCANCE / ERROR
    estado VARCHAR(20) NOT NULL DEFAULT 'PROCESANDO',
    -- Ultimo paso terminado (0 orquestador .. 5 evaluador)
    etapa SMALLINT,

    -- Periodo que eligio el Orquestador
    desde DATE,
    hasta DATE,

    metricas TEXT,
    hallazgos TEXT,
    recomendaciones TEXT,
    repartidores_sugeridos INTEGER,
    franja_refuerzo VARCHAR(60),
    titulo VARCHAR(200),
    calificacion VARCHAR(10),
    resumen TEXT,
    conclusion TEXT,
    puntos TEXT,
    orquestacion TEXT,
    evaluacion TEXT,
    nota_final NUMERIC(4,1),

    costo_usd NUMERIC(10,6),
    duracion_ms INTEGER,
    error VARCHAR(300)
);

CREATE INDEX IF NOT EXISTS idx_consultas_agentes_fecha
ON consultas_agentes(fecha_creacion DESC);
