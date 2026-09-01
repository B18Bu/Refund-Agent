-- 兼容策略：显式 ALTER TABLE，幂等（IF NOT EXISTS），不重建表、不触碰既有数据。
-- 新库由 models.py 的 create_all 直接建列；存量库执行本迁移补齐。
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS trace_id VARCHAR(128);

CREATE INDEX IF NOT EXISTS ix_tickets_trace_id ON tickets (trace_id);
