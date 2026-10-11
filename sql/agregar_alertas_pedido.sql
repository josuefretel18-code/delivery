-- =========================================================
-- Alertas de pedidos en riesgo (sistema multiagente)
--
-- Cuando el modelo ML predice que un pedido puede retrasarse,
-- tres agentes (Analista -> Operaciones -> Comunicador) analizan
-- la causa, recomiendan una accion y redactan el aviso al cliente.
-- Una fila por pedido (la ultima ejecucion).
--
-- El backend tambien la crea si no existe (backend/agentes_automaticos.py).
-- =========================================================

CREATE TABLE IF NOT EXISTS alertas_pedido (
    id BIGSERIAL PRIMARY KEY,

    pedido_id BIGINT NOT NULL UNIQUE
        REFERENCES pedidos(id)
        ON DELETE CASCADE,

    fecha TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    -- AUTOMATICA: al crear el pedido. MANUAL: boton del panel admin.
    origen VARCHAR(12) NOT NULL DEFAULT 'AUTOMATICA',

    -- PROCESANDO / LISTA / ERROR
    estado VARCHAR(12) NOT NULL DEFAULT 'PROCESANDO',

    probabilidad_retraso NUMERIC(6,4),

    -- Agente 1: Analista
    nivel VARCHAR(10),
    causa VARCHAR(300),
    factores TEXT,

    -- Agente 2: Operaciones
    accion VARCHAR(40),
    minutos_extra INTEGER,
    justificacion VARCHAR(400),

    -- Agente 3: Comunicador
    mensaje_cliente VARCHAR(400),
    resumen_admin VARCHAR(400),

    costo_usd NUMERIC(10,6),
    duracion_ms INTEGER,
    error VARCHAR(300)
);
