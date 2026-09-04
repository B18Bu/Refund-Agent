-- 电商领域表。所有语句可重复执行，不修改既有表结构。
-- 退单说明独立保存，避免被 OCR Worker 覆盖；兼容已有 tickets 表。
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS description TEXT;

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    brand VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    model VARCHAR(128),
    description TEXT,
    source_url VARCHAR(1024),
    source_site VARCHAR(64),
    image_url VARCHAR(1024),
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    last_synced_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_products_brand ON products (brand);

CREATE TABLE IF NOT EXISTS product_variants (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products (id),
    sku VARCHAR(128) NOT NULL UNIQUE,
    variant_name VARCHAR(255) NOT NULL,
    spec_json JSON NOT NULL DEFAULT '{}',
    price NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'CNY',
    available BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_product_variants_product_id ON product_variants (product_id);
CREATE INDEX IF NOT EXISTS ix_product_variants_sku ON product_variants (sku);

CREATE TABLE IF NOT EXISTS product_sources (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products (id),
    source_site VARCHAR(64) NOT NULL,
    source_url VARCHAR(1024) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    raw_hash VARCHAR(128),
    last_seen_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT uq_product_sources_site_external UNIQUE (source_site, external_id)
);

CREATE INDEX IF NOT EXISTS ix_product_sources_product_id ON product_sources (product_id);

CREATE TABLE IF NOT EXISTS addresses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    recipient_name VARCHAR(64) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    province VARCHAR(64) NOT NULL,
    city VARCHAR(64) NOT NULL,
    district VARCHAR(64) NOT NULL,
    detail VARCHAR(255) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_addresses_user_id ON addresses (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_addresses_user_default ON addresses (user_id) WHERE is_default = TRUE;

CREATE TABLE IF NOT EXISTS cart_items (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    variant_id INTEGER NOT NULL REFERENCES product_variants (id),
    quantity INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_cart_items_user_variant UNIQUE (user_id, variant_id)
);

CREATE INDEX IF NOT EXISTS ix_cart_items_user_id ON cart_items (user_id);
CREATE INDEX IF NOT EXISTS ix_cart_items_variant_id ON cart_items (variant_id);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_no VARCHAR(64) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users (id),
    address_snapshot_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'CREATED',
    total_amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'CNY',
    idempotency_key VARCHAR(128),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_orders_user_idempotency_key UNIQUE (user_id, idempotency_key)
);

-- 订单幂等键按用户隔离；兼容早期仅按 key 唯一的版本。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_orders_idempotency_key') THEN
        ALTER TABLE orders DROP CONSTRAINT uq_orders_idempotency_key;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_orders_user_idempotency_key') THEN
        ALTER TABLE orders ADD CONSTRAINT uq_orders_user_idempotency_key UNIQUE (user_id, idempotency_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_orders_order_no ON orders (order_no);
CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders (id),
    product_id INTEGER NOT NULL REFERENCES products (id),
    variant_id INTEGER NOT NULL REFERENCES product_variants (id),
    product_snapshot_json JSON NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'NORMAL'
);

CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON order_items (order_id);

CREATE TABLE IF NOT EXISTS return_requests (
    id SERIAL PRIMARY KEY,
    return_no VARCHAR(64) NOT NULL UNIQUE,
    order_id INTEGER NOT NULL REFERENCES orders (id),
    order_item_id INTEGER NOT NULL REFERENCES order_items (id),
    user_id INTEGER NOT NULL REFERENCES users (id),
    reason VARCHAR(128) NOT NULL,
    description TEXT,
    evidence_paths JSON NOT NULL DEFAULT '[]',
    status VARCHAR(32) NOT NULL DEFAULT 'SUBMITTED',
    ticket_id INTEGER REFERENCES tickets (id),
    idempotency_key VARCHAR(128),
    error_code VARCHAR(64),
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_return_requests_ticket_id UNIQUE (ticket_id),
    CONSTRAINT uq_return_requests_user_idempotency_key UNIQUE (user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_return_requests_return_no ON return_requests (return_no);
CREATE INDEX IF NOT EXISTS ix_return_requests_order_id ON return_requests (order_id);
CREATE INDEX IF NOT EXISTS ix_return_requests_order_item_id ON return_requests (order_item_id);
CREATE INDEX IF NOT EXISTS ix_return_requests_user_id ON return_requests (user_id);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id SERIAL PRIMARY KEY,
    source_site VARCHAR(64) NOT NULL,
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(16) NOT NULL DEFAULT 'RUNNING',
    items_seen INTEGER NOT NULL DEFAULT 0,
    items_upserted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS ix_scrape_runs_source_site ON scrape_runs (source_site);
