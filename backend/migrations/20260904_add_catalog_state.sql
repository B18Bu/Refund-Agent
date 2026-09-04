-- 商品目录发布状态；抓取未满足完整门槛时保持 NOT_READY。
CREATE TABLE IF NOT EXISTS catalog_state (
    id INTEGER PRIMARY KEY,
    status VARCHAR(32) NOT NULL DEFAULT 'NOT_READY',
    last_success_at TIMESTAMP WITHOUT TIME ZONE,
    last_error_code VARCHAR(64)
);
INSERT INTO catalog_state (id, status) VALUES (1, 'NOT_READY')
ON CONFLICT (id) DO NOTHING;
