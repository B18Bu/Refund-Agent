-- 订单状态为 VARCHAR；COMPLETED 无需变更列类型。此索引显式支持消费者偏好
-- 仅查询近 180 天已完成订单的确定性筛选，不能依赖 ORM create_all 修改生产库。
CREATE INDEX IF NOT EXISTS ix_orders_user_status_created_at
    ON orders (user_id, status, created_at);

CREATE TABLE IF NOT EXISTS customer_privacy_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    preference_key VARCHAR(64) NOT NULL,
    automatic_value JSONB,
    manual_value JSONB,
    source_order_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence NUMERIC(5, 4),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_preferences_user_key UNIQUE (user_id, preference_key)
);
CREATE INDEX IF NOT EXISTS ix_customer_preferences_user_id ON customer_preferences (user_id);

CREATE TABLE IF NOT EXISTS customer_preference_ignores (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    preference_key VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_preference_ignores_user_key UNIQUE (user_id, preference_key)
);
CREATE INDEX IF NOT EXISTS ix_customer_preference_ignores_user_id ON customer_preference_ignores (user_id);

CREATE TABLE IF NOT EXISTS customer_preference_audits (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    action VARCHAR(32) NOT NULL,
    preference_key VARCHAR(64),
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_customer_preference_audits_user_id ON customer_preference_audits (user_id);
