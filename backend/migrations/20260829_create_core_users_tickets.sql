-- 空 PostgreSQL 首次部署的核心前置表。后续迁移和 RAG 审计日志均引用 users/tickets。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'role') THEN
        CREATE TYPE role AS ENUM ('CUSTOMER', 'CS', 'SV');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ticketstatus') THEN
        CREATE TYPE ticketstatus AS ENUM ('RUNNING', 'SUSPENDED', 'COMPLETED');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'decision') THEN
        CREATE TYPE decision AS ENUM ('PENDING', 'AUTO_REFUNDED', 'APPROVED', 'REJECTED', 'FAILED');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    role role NOT NULL DEFAULT 'CS',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    ticket_no VARCHAR(64) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users (id),
    trace_id VARCHAR(128),
    amount NUMERIC(12, 2) NOT NULL,
    image_paths JSON NOT NULL DEFAULT '[]',
    description TEXT,
    ocr_text TEXT,
    ocr_confidence NUMERIC(5, 4),
    fraud_score INTEGER,
    sentiment VARCHAR(16),
    decision_reasons JSON,
    evidence_audit JSON,
    management_suggestion TEXT,
    status ticketstatus NOT NULL DEFAULT 'RUNNING',
    decision decision NOT NULL DEFAULT 'PENDING',
    error_code VARCHAR(64),
    error_message TEXT,
    thread_id VARCHAR(64),
    idempotency_key VARCHAR(128),
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_tickets_trace_id ON tickets (trace_id);
CREATE INDEX IF NOT EXISTS ix_tickets_thread_id ON tickets (thread_id);
