-- =========================================================
-- DELIVERY PREDICTIVO
-- Esquema principal PostgreSQL
-- =========================================================


-- =========================================================
-- 1. USUARIOS
-- =========================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,

    nombre_completo VARCHAR(120) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    telefono VARCHAR(20),

    rol VARCHAR(20) NOT NULL
        CHECK (rol IN (
            'CLIENTE',
            'REPARTIDOR',
            'OPERADOR',
            'ADMIN'
        )),

    activo BOOLEAN NOT NULL DEFAULT TRUE,

    fecha_creacion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 2. REPARTIDORES
-- =========================================================

CREATE TABLE IF NOT EXISTS repartidores (
    id BIGSERIAL PRIMARY KEY,

    usuario_id BIGINT NOT NULL UNIQUE,

    codigo VARCHAR(20) NOT NULL UNIQUE,

    tipo_vehiculo VARCHAR(30) NOT NULL
        CHECK (tipo_vehiculo IN (
            'MOTO',
            'BICICLETA',
            'AUTO',
            'CAMIONETA',
            'OTRO'
        )),

    placa VARCHAR(20),

    activo BOOLEAN NOT NULL DEFAULT TRUE,

    fecha_registro TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_repartidor_usuario
        FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id)
        ON DELETE RESTRICT
);


-- =========================================================
-- 3. ESTADOS DEL PEDIDO
-- =========================================================

CREATE TABLE IF NOT EXISTS estados_pedido (
    id SERIAL PRIMARY KEY,

    codigo VARCHAR(30) NOT NULL UNIQUE,

    nombre VARCHAR(80) NOT NULL,

    orden_flujo INTEGER NOT NULL,

    es_final BOOLEAN NOT NULL DEFAULT FALSE
);


-- =========================================================
-- 4. PEDIDOS
-- =========================================================

CREATE TABLE IF NOT EXISTS pedidos (
    id BIGSERIAL PRIMARY KEY,

    codigo VARCHAR(30) NOT NULL UNIQUE,

    cliente_id BIGINT NOT NULL,

    repartidor_id BIGINT,

    estado_id INTEGER NOT NULL,

    -- Datos del remitente
    remitente_nombre VARCHAR(120) NOT NULL,
    remitente_telefono VARCHAR(20),

    -- Datos del destinatario
    destinatario_nombre VARCHAR(120) NOT NULL,
    destinatario_telefono VARCHAR(20),

    -- Información del paquete
    descripcion_paquete VARCHAR(250),
    peso_kg DECIMAL(8,2),

    -- Origen
    direccion_origen VARCHAR(250) NOT NULL,
    latitud_origen DECIMAL(10,7) NOT NULL,
    longitud_origen DECIMAL(10,7) NOT NULL,
    zona_origen VARCHAR(80),

    -- Destino
    direccion_destino VARCHAR(250) NOT NULL,
    latitud_destino DECIMAL(10,7) NOT NULL,
    longitud_destino DECIMAL(10,7) NOT NULL,
    zona_destino VARCHAR(80),

    -- Datos obtenidos de Google Maps
    distancia_km DECIMAL(10,2),
    duracion_estimada_min INTEGER,

    -- Datos reales del proceso
    duracion_real_min INTEGER,

    -- Variable objetivo del ML
    retraso BOOLEAN,

    -- Fechas principales
    fecha_pedido TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    fecha_confirmacion TIMESTAMPTZ,

    fecha_asignacion TIMESTAMPTZ,

    fecha_recojo TIMESTAMPTZ,

    fecha_entrega TIMESTAMPTZ,

    fecha_cancelacion TIMESTAMPTZ,

    observaciones TEXT,

    CONSTRAINT fk_pedido_cliente
        FOREIGN KEY (cliente_id)
        REFERENCES usuarios(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_pedido_repartidor
        FOREIGN KEY (repartidor_id)
        REFERENCES repartidores(id)
        ON DELETE SET NULL,

    CONSTRAINT fk_pedido_estado
        FOREIGN KEY (estado_id)
        REFERENCES estados_pedido(id)
        ON DELETE RESTRICT
);


-- =========================================================
-- 5. HISTORIAL DEL PEDIDO
-- =========================================================

CREATE TABLE IF NOT EXISTS historial_pedido (
    id BIGSERIAL PRIMARY KEY,

    pedido_id BIGINT NOT NULL,

    estado_id INTEGER NOT NULL,

    observacion VARCHAR(300),

    usuario_id BIGINT,

    fecha TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_historial_pedido
        FOREIGN KEY (pedido_id)
        REFERENCES pedidos(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_historial_estado
        FOREIGN KEY (estado_id)
        REFERENCES estados_pedido(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_historial_usuario
        FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 6. CLIMA DEL PEDIDO
-- Snapshot usado para ML
-- =========================================================

CREATE TABLE IF NOT EXISTS clima_pedido (
    id BIGSERIAL PRIMARY KEY,

    pedido_id BIGINT NOT NULL UNIQUE,

    temperatura DECIMAL(5,2),

    precipitacion_mm DECIMAL(8,2),

    velocidad_viento_kmh DECIMAL(8,2),

    codigo_clima INTEGER,

    descripcion_clima VARCHAR(120),

    fecha_consulta TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_clima_pedido
        FOREIGN KEY (pedido_id)
        REFERENCES pedidos(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 7. PREDICCIONES MACHINE LEARNING
-- =========================================================

CREATE TABLE IF NOT EXISTS predicciones_ml (
    id BIGSERIAL PRIMARY KEY,

    pedido_id BIGINT NOT NULL,

    modelo_version VARCHAR(50) NOT NULL,

    -- Resultado
    clase_predicha VARCHAR(20) NOT NULL
        CHECK (clase_predicha IN (
            'A_TIEMPO',
            'RETRASADO'
        )),

    probabilidad_retraso DECIMAL(6,5),

    -- Snapshot exacto de variables utilizadas por el modelo
    distancia_km DECIMAL(10,2),

    duracion_estimada_min INTEGER,

    hora_pedido INTEGER,

    dia_semana INTEGER,

    pedidos_activos INTEGER,

    carga_repartidor NUMERIC(8, 4),

    temperatura DECIMAL(5,2),

    precipitacion_mm DECIMAL(8,2),

    velocidad_viento_kmh DECIMAL(8,2),

    zona_origen VARCHAR(80),

    zona_destino VARCHAR(80),

    fecha_prediccion TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_prediccion_pedido
        FOREIGN KEY (pedido_id)
        REFERENCES pedidos(id)
        ON DELETE CASCADE
);


-- =========================================================
-- 8. AUDITORÍA
-- =========================================================

CREATE TABLE IF NOT EXISTS auditoria (
    id BIGSERIAL PRIMARY KEY,

    usuario_id BIGINT,

    accion VARCHAR(100) NOT NULL,

    entidad VARCHAR(80),

    entidad_id BIGINT,

    detalle TEXT,

    fecha TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_auditoria_usuario
        FOREIGN KEY (usuario_id)
        REFERENCES usuarios(id)
        ON DELETE SET NULL
);


-- =========================================================
-- 9. ÍNDICES
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_pedidos_codigo
ON pedidos(codigo);

CREATE INDEX IF NOT EXISTS idx_pedidos_cliente
ON pedidos(cliente_id);

CREATE INDEX IF NOT EXISTS idx_pedidos_repartidor
ON pedidos(repartidor_id);

CREATE INDEX IF NOT EXISTS idx_pedidos_estado
ON pedidos(estado_id);

CREATE INDEX IF NOT EXISTS idx_pedidos_fecha
ON pedidos(fecha_pedido);

CREATE INDEX IF NOT EXISTS idx_pedidos_retraso
ON pedidos(retraso);

CREATE INDEX IF NOT EXISTS idx_historial_pedido
ON historial_pedido(pedido_id);

CREATE INDEX IF NOT EXISTS idx_predicciones_pedido
ON predicciones_ml(pedido_id);

CREATE INDEX IF NOT EXISTS idx_auditoria_fecha
ON auditoria(fecha);