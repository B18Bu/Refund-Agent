-- 兼容策略：显式 ALTER TABLE，幂等（IF NOT EXISTS），不重建表、不触碰既有数据。
-- 新增三维判断（价格/订单/商品）审计结果与管理建议，供详情页与观测展示。
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS decision_reasons JSON;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS evidence_audit JSON;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS management_suggestion TEXT;
