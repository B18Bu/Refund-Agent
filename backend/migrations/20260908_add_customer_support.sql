CREATE TABLE IF NOT EXISTS customer_support_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
    title VARCHAR(128),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_customer_support_conversations_user_id
    ON customer_support_conversations (user_id);
CREATE INDEX IF NOT EXISTS ix_customer_support_conversations_status
    ON customer_support_conversations (status);

CREATE TABLE IF NOT EXISTS customer_support_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES customer_support_conversations(id),
    sender VARCHAR(16) NOT NULL,
    content_masked TEXT NOT NULL,
    intent VARCHAR(32),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_customer_support_messages_conversation_id
    ON customer_support_messages (conversation_id, id);

CREATE TABLE IF NOT EXISTS customer_support_cases (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL UNIQUE REFERENCES customer_support_conversations(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
    trigger_reason VARCHAR(32) NOT NULL,
    summary_masked TEXT,
    assigned_to INTEGER REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_customer_support_cases_user_id ON customer_support_cases (user_id);
CREATE INDEX IF NOT EXISTS ix_customer_support_cases_status ON customer_support_cases (status);
CREATE INDEX IF NOT EXISTS ix_customer_support_cases_assigned_to ON customer_support_cases (assigned_to);
