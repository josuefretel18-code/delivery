-- =========================================================
-- Registro de consumo del asistente con LLM (OpenAI)
--
-- Una fila por mensaje respondido (suma de todos los pasos
-- del agente). Sirve para el panel "Consumo del LLM", el
-- corte por presupuesto mensual y el limite diario por usuario.
--
-- El backend tambien la crea si no existe (backend/llm_agente.py).
-- =========================================================

CREATE TABLE IF NOT EXISTS llm_uso (
    id BIGSERIAL PRIMARY KEY,

    fecha TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    usuario_id BIGINT
        REFERENCES usuarios(id)
        ON DELETE SET NULL,

    -- CLIENTE / ADMIN: asistentes del chat.
    -- ALERTA / REPORTE: agentes automaticos.
    asistente VARCHAR(10) NOT NULL,

    modelo VARCHAR(40) NOT NULL,

    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_cache INTEGER NOT NULL DEFAULT 0,
    tokens_salida INTEGER NOT NULL DEFAULT 0,
    tokens_razonamiento INTEGER NOT NULL DEFAULT 0,

    pasos SMALLINT NOT NULL DEFAULT 0,
    herramientas VARCHAR(200),

    costo_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
    duracion_ms INTEGER,

    ok BOOLEAN NOT NULL DEFAULT TRUE,
    error VARCHAR(300)
);

CREATE INDEX IF NOT EXISTS idx_llm_uso_fecha
    ON llm_uso (fecha);

CREATE INDEX IF NOT EXISTS idx_llm_uso_usuario_fecha
    ON llm_uso (usuario_id, fecha);

-- Valores permitidos (se reemplaza para admitir los agentes automaticos)
ALTER TABLE llm_uso
    DROP CONSTRAINT IF EXISTS llm_uso_asistente_check;

ALTER TABLE llm_uso
    ADD CONSTRAINT llm_uso_asistente_check
    CHECK (asistente IN ('CLIENTE', 'ADMIN', 'ALERTA', 'REPORTE'));
