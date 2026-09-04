-- 为既有 users.role PostgreSQL 枚举增加消费者角色；可重复执行。
-- SQLAlchemy Enum(Role) 使用 role 类型且枚举标签为成员名（CUSTOMER/CS/SV）。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'role') THEN
        ALTER TYPE role ADD VALUE IF NOT EXISTS 'CUSTOMER';
    END IF;
    -- 兼容早期显式迁移采用 user_role 类型的数据库。
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'CUSTOMER';
    END IF;
END $$;
