-- ==============================================================================
-- INICIALIZACIÓN DE POSTGRESQL + APACHE AGE (RESTAURANTE RYU)
-- Base de datos de Grafos para KAG, Ontología de Alimentos y Almacenamiento Protobuf
-- ==============================================================================

-- 1. Cargar extensión Apache AGE
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
ALTER DATABASE ryu_db SET search_path = ag_catalog, public;


-- 2. Inicializar el Grafo de Conocimiento de Ryu
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_graph WHERE name = 'ryu_knowledge_graph') THEN
        PERFORM create_graph('ryu_knowledge_graph');
        RAISE NOTICE 'Grafo ryu_knowledge_graph creado exitosamente.';
    ELSE
        RAISE NOTICE 'Grafo ryu_knowledge_graph ya existía.';
    END IF;
END $$;

-- 3. Tabla Relacional de Clientes (Perfiles y Preferencias)
CREATE TABLE IF NOT EXISTS customers (
    phone VARCHAR(30) PRIMARY KEY,
    name VARCHAR(100),
    default_address TEXT,
    default_zone VARCHAR(100),
    notes TEXT,
    total_orders INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabla de Comandas / Órdenes (con almacenamiento binario Protobuf BYTEA)
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(100),
    customer_phone VARCHAR(30),
    customer_name VARCHAR(100),
    total_amount NUMERIC(10,2) NOT NULL,
    shipping_fee NUMERIC(10,2) DEFAULT 0.00,
    status VARCHAR(50) DEFAULT 'PENDIENTE_PREPARACION',
    is_future BOOLEAN DEFAULT FALSE,
    scheduled_time TEXT,
    delivery_type VARCHAR(30),
    address TEXT,
    payment_method VARCHAR(30),
    proto_payload BYTEA NOT NULL,
    audit_hash VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tabla de Telemetría y Registro de Llamadas (Protobuf BYTEA)
CREATE TABLE IF NOT EXISTS call_logs (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    caller_phone VARCHAR(30),
    caller_name VARCHAR(100),
    duration_sec NUMERIC(8,2) DEFAULT 0.00,
    order_id VARCHAR(64),
    turn_count INT DEFAULT 0,
    proto_payload BYTEA,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Tabla de Eventos de Autoaprendizaje KAG (Feedback de clientes y alias nuevos)
CREATE TABLE IF NOT EXISTS learning_events (
    event_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(100),
    customer_phone VARCHAR(30),
    original_text TEXT,
    corrected_intent TEXT,
    learned_alias VARCHAR(150),
    target_entity VARCHAR(150),
    entity_type VARCHAR(50),
    applied_to_graph BOOLEAN DEFAULT TRUE,
    proto_payload BYTEA,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices de alto rendimiento
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_phone);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_learning_alias ON learning_events(learned_alias);
