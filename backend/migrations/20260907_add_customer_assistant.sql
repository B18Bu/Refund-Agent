-- 订单状态为 VARCHAR；COMPLETED 无需变更列类型。此索引显式支持消费者偏好
-- 仅查询近 180 天已完成订单的确定性筛选，不能依赖 ORM create_all 修改生产库。
CREATE INDEX IF NOT EXISTS ix_orders_user_status_created_at
    ON orders (user_id, status, created_at);
